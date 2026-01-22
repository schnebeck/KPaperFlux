
import json
from typing import List, Optional
from core.database import DatabaseManager
from core.document import Document
from core.models.canonical_entity import CanonicalEntity, DocType
from core.ai_analyzer import AIAnalyzer
from core.config import AppConfig
from core.models.identity import IdentityProfile
import json

class CanonizerService:
    """
    Scans 'documents' table for processed files that lack 'semantic_entities'.
    Uses AI to identify and extract Canonical Entities.
    """
    
    def __init__(self, db: DatabaseManager, analyzer: Optional[AIAnalyzer] = None):
        self.db = db
        self.config = AppConfig()
        if analyzer:
            self.analyzer = analyzer
        else:
            # Initialize Analyzer if not provided (key from config/env)
            api_key = self.config.get_api_key() 
            self.analyzer = AIAnalyzer(api_key, model_name="gemini-2.0-flash") if api_key else None

    def process_pending_documents(self, limit: int = 10):
        """
        Main loop: Find documents without entities, process them.
        """
        if not self.analyzer:
            print("[Canonizer] No AI Analyzer available.")
            return

        # 1. Find candidates (Naive check: Docs exists but no entities linked?)
        
        cursor = self.db.connection.cursor()
        query = """
            SELECT d.uuid, d.text_content, d.semantic_data, d.extra_data
            FROM documents d
            WHERE d.uuid NOT IN (SELECT source_doc_uuid FROM semantic_entities)
            LIMIT ?
        """
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        
        for row in rows:
            uuid, text_content, semantic_data_json, extra_data_json = row
            # Load Raw Semantics (if any)
            semantic_data = {}
            if semantic_data_json:
                try:
                    semantic_data = json.loads(semantic_data_json)
                except:
                    pass
            
            # Load Extra Data (Stamps)
            extra_data = {}
            if extra_data_json:
                try:
                    extra_data = json.loads(extra_data_json)
                except:
                    pass
            
            self.process_document(uuid, text_content, semantic_data, extra_data)
            
    def process_document(self, uuid: str, text_content: str, semantic_data: dict = None, extra_data: dict = None, file_path: Optional[str] = None):
        """
        Process a single document: Identify Entities and Persist.
        :param file_path: Required for Stage 1.5 (Visual Audit)
        """
        if not self.analyzer:
            return

        print(f"[Canonizer] Processing {uuid}...")
        
        # Load Identity Profiles
        priv_json = self.config.get_private_profile_json()
        bus_json = self.config.get_business_profile_json()
        
        priv_id = IdentityProfile.model_validate_json(priv_json) if priv_json else None
        bus_id = IdentityProfile.model_validate_json(bus_json) if bus_json else None

        # Split Pages (Assumption: Form Feed or just treat as list if unknown)
        # Using Form Feed \f is standard for pdftotext. If not present, check logic.
        # Fallback: Treat entire text as 1 page if no split found.
        pages = text_content.split('\f')
        if not pages: pages = [text_content]
        # Remove empty last page often caused by split
        if pages and not pages[-1].strip():
            pages.pop()
            
        # Phase 102: Master Classification (Multi-Doc)
        struct_res = self.analyzer.classify_structure(pages, priv_id, bus_id)
        
        detected_entities = struct_res.get("detected_entities", [])
        
        if not detected_entities:
            # Check if it returned the old single-object format (fallback)
            if "doc_type" in struct_res:
                 detected_entities = [struct_res]
            else:
                 # AI Failed or Returned Empty -> ABORT processing to preserve old data
                 print(f"[Canonizer] AI Analysis failed or empty for {uuid}. Preserving existing data.")
                 return

        # Phase 103: Visual Audit (Stage 1.5)
        # Check for Stamps and Signatures, save to DB
        if file_path:
            try:
                from core.visual_auditor import VisualAuditor
                auditor = VisualAuditor(self.analyzer)
                
                # Pass full structure so it can decide mode based on DocTypes
                # Also pass text_content so auditor doesn't need to re-extract (and fail on image-only PDFs)
                audit_res = auditor.run_stage_1_5(file_path, uuid, struct_res, text_content)
                
                if audit_res:
                    # Extract Expanded Columns
                    # 1. Clean Text
                    clean_text = audit_res.get("layer_document", {}).get("clean_text")
                    
                    # 2. Recommended Source
                    arbiter = audit_res.get("arbiter_decision", {})
                    pref_source = arbiter.get("primary_source_recommendation", "RAW_OCR")
                    
                    # 3. Full JSON
                    audit_json_str = json.dumps(audit_res)
                    
                    # Save to DB (Expanded)
                    self.db.save_audit_result(uuid, clean_text, pref_source, audit_json_str)
                    print(f"[Canonizer] Saved Expanded Visual Audit for {uuid} (Pref: {pref_source})")
            except Exception as e:
                print(f"[Canonizer] Stage 1.5 Failed: {e}")

        # Success! Now we can safely clean up the old data
        try:
            with self.db.connection:
                self.db.connection.execute("DELETE FROM semantic_entities WHERE source_doc_uuid = ?", (uuid,))
                # Reset ref_count?
                self.db.connection.execute("UPDATE documents SET ref_count = 0 WHERE uuid = ?", (uuid,))
            print(f"[Canonizer] Cleaned up existing analysis for {uuid} (Overwriting with new results)")
        except Exception as e:
            print(f"[Canonizer] Cleanup failed: {e}")
            # If cleanup fails, do we continue? Yes, but might duplicate. 
            # Ideally we should stop, but let's try to proceed.

        # Construct meta list for processing loop
        # Each detects logical entity shares the full page range (since split is not supported in this prompt)
        all_page_indices = list(range(1, len(pages) + 1)) 
        
        entities_meta = []
        for det in detected_entities:
            entities_meta.append({
                "type": det.get("doc_type", "OTHER"),
                "pages": all_page_indices,
                "direction": det.get("direction"),
                "context": det.get("tenant_context"),
                "reasoning": det.get("reasoning")
            })

        # 2. Extract & Persist
        for meta in entities_meta:
             doc_type_str = meta.get("type", "OTHER")
             page_range = meta.get("pages", [])
             
             # Map string to Enum (robust mapping)
             try:
                 # Normalize: Remove "DocType." prefix if AI hallucinated it
                 clean_type = doc_type_str.replace("DocType.", "").upper()
                 doc_type = DocType[clean_type]
             except:
                 try:
                     doc_type = DocType(doc_type_str)
                 except:
                     doc_type = DocType.OTHER
             
             # Extract Text specific to these pages (Critical for accurate extraction)
             entity_text = self._get_text_for_pages(text_content, page_range, semantic_data)
             
             # AI Step 2: Full Extraction for this Type
             # We extract specific CDM fields
             cdm_data = self.analyzer.extract_canonical_data(doc_type, entity_text)
             
             # Remove redundant 'doc_type' from cdm_data if present
             cdm_data.pop('doc_type', None)
             
             # Phase 98: Stamp Integration
             # Filter stamps relevant to this entity's page range
             entity_stamps = []
             if extra_data and "stamps" in extra_data:
                 raw_stamps = extra_data["stamps"]
                 # Support dict or list format if migrated
                 if isinstance(raw_stamps, list):
                     for stamp in raw_stamps:
                         # Stamp page is usually 1-indexed
                         s_page = stamp.get("page", 0)
                         if s_page in page_range:
                             entity_stamps.append(stamp)
             
             # Create Entity Object
             try:
                 entity = CanonicalEntity(
                     source_doc_uuid=uuid,
                     doc_type=doc_type,
                     page_range=page_range,
                     stamps=entity_stamps,
                     **cdm_data
                 )
                 
                 # Apply Phase 102 Classification Results
                 ai_direction = meta.get("direction")
                 ai_context = meta.get("context")
                 
                 if ai_direction and ai_direction in ["INBOUND", "OUTBOUND", "INTERNAL"]:
                     # Map INBOUND/OUTBOUND to CDM (CDM uses INCOMING/OUTGOING typically? 
                     # User request says "INBOUND/OUTBOUND". Existing code uses "INCOMING/OUTGOING".
                     # Let's normalize.
                     mapping = {"INBOUND": "INCOMING", "OUTBOUND": "OUTGOING"}
                     entity.direction = mapping.get(ai_direction, ai_direction)
                 
                 if ai_context:
                     # Store context in tags for now
                     entity.tags_and_flags.append(f"Context:{ai_context}")
                 
                 # Fallback to Heuristic if AI was unsure or UNKNOWN
                 if not entity.direction or entity.direction == "UNKNOWN":
                     self._classify_direction(entity)
                 
                 # Validate & Save
                 self.save_entity(entity)
                 print(f"[Canonizer] Saved Entity {doc_type.name} (Pages {page_range}) - Dir: {entity.direction}")
             except Exception as e:
                 print(f"[Canonizer] Entity Creation Failed for {uuid}/{doc_type}: {e}")

    def _get_text_for_pages(self, full_text: str, pages: List[int], semantic_data: dict) -> str:
        """
        Extract text content only for the specified pages to reduce hallucination.
        First tries semantic_data structure, falls back to full text.
        """
        if not pages:
            return full_text
            
        target_pages = set(pages)
        extracted_text = []
        found_paged_data = False
        
        # Method A: Use Semantic Data structure (Most Accurate)
        if semantic_data and "pages" in semantic_data:
            for p_idx, p_data in enumerate(semantic_data["pages"]):
                # page_number usually 1-indexed in JSON, but check data
                p_num = p_data.get("page_number", p_idx + 1)
                
                if p_num in target_pages:
                    found_paged_data = True
                    # Reconstruct text from regions/blocks
                    page_txt = []
                    regions = p_data.get("regions", [])
                    for r in regions:
                        for b in r.get("blocks", []):
                            # Try 'raw_text' (Address) or 'content' (Text) or 'pairs' (KV)
                            if "raw_text" in b: page_txt.append(b["raw_text"])
                            elif "content" in b: page_txt.append(b["content"])
                            elif "pairs" in b:
                                for pair in b["pairs"]:
                                    page_txt.append(f"{pair.get('key','')}: {pair.get('value','')}")
                            elif "rows" in b: # Tables
                                for row in b["rows"]:
                                    page_txt.append(" | ".join(map(str, row)))
                    
                    if page_txt:
                        extracted_text.append(f"--- Page {p_num} ---\n" + "\n".join(page_txt))
        
        if found_paged_data and extracted_text:
            return "\n\n".join(extracted_text)
            
        # Method B: Naive Page Markers in Text (Fallback)
        # Not reliable if markers missing, so default to full text if A failed
        return full_text
                 
    def save_entity(self, entity: CanonicalEntity):
        """Persist Pydantic Entity to DB."""
        # Convert Pydantic to JSON/Dict
        data = entity.model_dump()
        
        # Extract core columns
        doc_date = entity.doc_date
        sender = None
        if entity.parties and entity.parties.sender:
            sender = entity.parties.sender.name
        
        # Specific & List Data kept as JSON
        cdata_json = entity.model_dump_json() # Store everything as blob for reconstruction
        
        # Generate ID if missing?
        import uuid
        entity_uuid = str(uuid.uuid4())
        
        insert_sql = """
            INSERT INTO semantic_entities (
                entity_uuid, source_doc_uuid, doc_type, doc_date, sender_name, canonical_data, page_ranges, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW')
        """
        
        vals = (
            entity_uuid,
            entity.source_doc_uuid,
            entity.doc_type.value,
            doc_date,
            sender,
            cdata_json,
            json.dumps(entity.page_range)
        )
        
        try:
            with self.db.connection:
                self.db.connection.execute(insert_sql, vals)
                # Increment Reference Count
                self.db.connection.execute(
                    "UPDATE documents SET ref_count = ref_count + 1 WHERE uuid = ?", 
                    (entity.source_doc_uuid,)
                )
            print(f"[Canonizer] Saved Entity {entity.doc_type.value} for {entity.source_doc_uuid}")
        except Exception as e:
            print(f"[Canonizer] DB Error: {e}")

    def _classify_direction(self, entity: CanonicalEntity):
        """
        Phase 101: Semantic Direction Classification.
        Uses both raw signatures and structured IdentityProfiles (if available).
        """
        # Load Raw Signatures
        private_sig = self.config.get_private_signature().strip()
        business_sig = self.config.get_business_signature().strip()
        
        # Load Structured Profiles
        priv_json = self.config.get_private_profile_json()
        bus_json = self.config.get_business_profile_json()
        
        profiles = []
        try:
            if priv_json: profiles.append(IdentityProfile.model_validate_json(priv_json))
            if bus_json: profiles.append(IdentityProfile.model_validate_json(bus_json))
        except Exception as e:
            print(f"[Canonizer] Profile Load Error: {e}")

        # Helper to check if a Party matches Me
        def is_me(party_name: str, party_address: str) -> bool:
            if not party_name: return False
            norm_name = party_name.lower()
            norm_addr = party_address.lower() if party_address else ""
            
            # 1. Raw Signature Match (Heuristic: First line)
            for sig in [private_sig, business_sig]:
                if sig:
                    first_line = sig.split('\n')[0].strip().lower()
                    if first_line and first_line in norm_name:
                        return True
                        
            # 2. Structured Profile Match
            for prof in profiles:
                # Name (Person or Entity Main)
                if prof.name and prof.name.lower() in norm_name:
                    return True
                # Aliases
                for alias in prof.aliases:
                    if alias.lower() in norm_name:
                        return True
                
                # Company Name
                if prof.company_name and prof.company_name.lower() in norm_name:
                    return True
                # Company Aliases
                for ca in prof.company_aliases:
                    if ca.lower() in norm_name:
                        return True
                        
                # Address Keywords (Weak match, usually needs multiple? For now just checks presence in address field)
                # If Address is present, check keywords
                if norm_addr and prof.address_keywords:
                    # Require at least one significant keyword (e.g. Street or City) to match
                    for kw in prof.address_keywords:
                        if len(kw) > 3 and kw.lower() in norm_addr:
                             # Strengthen this? Maybe checking Zip is safest.
                             # For now, simplistic match.
                             return True
            return False

        sender_addr = entity.parties.sender.address
        recipient_addr = entity.parties.recipient.address

        # Sender = Me? -> OUTGOING
        if is_me(entity.parties.sender.name, sender_addr):
            entity.direction = "OUTGOING"
            return

        # Recipient = Me? -> INCOMING
        if is_me(entity.parties.recipient.name, recipient_addr):
            entity.direction = "INCOMING"
            return
