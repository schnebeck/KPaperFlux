
from typing import List, Optional
from core.database import DatabaseManager
from core.document import Document
from core.models.canonical_entity import CanonicalEntity, DocType
from core.models.virtual import VirtualDocument, SourceReference
from core.ai_analyzer import AIAnalyzer
from core.visual_auditor import VisualAuditor
from core.config import AppConfig
from core.models.identity import IdentityProfile
from core.repositories.physical_repo import PhysicalRepository
from core.repositories.logical_repo import LogicalRepository
from core.rules_engine import RulesEngine
import uuid
import json
from datetime import datetime

class CanonizerService:
    """
    Phase 2 Canonizer:
    Scans 'semantic_entities' (Logical Entities) with status='NEW'.
    Resolves text via VirtualDocument -> PhysicalFile.
    Handles Splitting (1 Logical -> N Logical).
    """
    
    def __init__(self, db: DatabaseManager, analyzer: Optional[AIAnalyzer] = None, 
                 physical_repo: Optional[PhysicalRepository] = None,
                 logical_repo: Optional[LogicalRepository] = None,
                 filter_tree: Optional['FilterTree'] = None):
        self.db = db
        self.config = AppConfig()
        self.filter_tree = filter_tree
        
        # Repositories (Lazy init or passed)
        self.physical_repo = physical_repo if physical_repo else PhysicalRepository(db)
        self.logical_repo = logical_repo if logical_repo else LogicalRepository(db)
        
        # Core Components
        if analyzer:
            self.analyzer = analyzer
        else:
            self.analyzer = AIAnalyzer(self.config.get_api_key(), self.config.get_gemini_model())
            
        self.visual_auditor = VisualAuditor(self.analyzer)
        self.rules_engine = RulesEngine(db, filter_tree) if filter_tree else None

    def process_pending_documents(self, limit: int = 10):
        """
        Scan for Logical Entities with status='NEW'.
        """
        if not self.analyzer:
            print("[Canonizer] No AI Analyzer available.")
            return

        cursor = self.db.connection.cursor()
        # Fetch NEW entities
        query = """
            SELECT uuid 
            FROM virtual_documents 
            WHERE status IN ('NEW', 'READY_FOR_PIPELINE') AND deleted = 0
            LIMIT ?
        """
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        
        processed_count = 0
        for row in rows:
            uuid = row[0]
            v_doc = self.logical_repo.get_by_uuid(uuid)
            if v_doc:
                self.process_virtual_document(v_doc)
                processed_count += 1
        return processed_count
            
    def process_virtual_document(self, v_doc: VirtualDocument):
        """
        Process a specific VirtualDocument.
        """
        if not self.analyzer: return
        print(f"[STAGE 1] Processing Logical Entity {v_doc.uuid}...")
        
        # Capture original tags to detect manual intervention
        original_tags = getattr(v_doc, "type_tags", [])
        is_manual = "MANUAL_EDIT" in original_tags
        
        # 1. Resolve Text Content (Lazy Load)
        # Helper callback to fetch physical data
        def loader(fid):
            return self.physical_repo.get_by_uuid(fid)
            
        # 1. Phase A: physical OCR (The Seeing)
        # resolve_content handles extraction from source_mapping
        full_text = v_doc.resolve_content(loader)
        if not full_text:
            print(f"[Canonizer] No text content resolved for {v_doc.uuid}. Skipping.")
            return

        # Save to cached_full_text for FTS and Phase B
        v_doc.cached_full_text = full_text
        print(f"[STAGE 1] Phase A: Resolved Full Text ({len(full_text)} chars)")

        # 2. AI Analysis (Stage 1: Structure/Split)
        
        # Load Profiles
        priv_json = self.config.get_private_profile_json()
        bus_json = self.config.get_business_profile_json()
        priv_id = IdentityProfile.model_validate_json(priv_json) if priv_json else None
        bus_id = IdentityProfile.model_validate_json(bus_json) if bus_json else None
        
        # Split Pages logic (Naive \f check or rely on page markers from resolve_content?)
        # v_doc.resolve_content returns joined text. 
        # Ideally we want pages separate for classify_structure.
        # Let's reconstruct page list from source_mapping + physical repo directly?
        # Or better: v_doc gives us a way to get text per page? 
        # resolve_content is flat.
        # Let's rebuild pages list here manually for accurate classification.
        
        pages_text = []
        for src in v_doc.source_mapping:
            pf = self.physical_repo.get_by_uuid(src.file_uuid)
            if pf and pf.raw_ocr_data:
                # Determine how raw_ocr_data is stored (String/JSON or Dict)
                # PhysicalRepo returns object. 
                raw = pf.raw_ocr_data
                if isinstance(raw, str):
                    try: raw = json.loads(raw)
                    except: raw = {}
                
                if isinstance(raw, dict):
                    for p in src.pages:
                        pages_text.append(raw.get(str(p), ""))
        
        if not pages_text:
             # Fallback
             pages_text = [full_text]
             
        # [STAGE 1.1] Classification & Context (Adaptive Routing)
        struct_res = self.analyzer.run_stage_1_adaptive(pages_text, priv_id, bus_id)
        detected_entities = struct_res.get("detected_entities", [])
        is_hybrid = struct_res.get("source_file_summary", {}).get("is_hybrid_document", False)
        
        if not detected_entities:
            print(f"[Canonizer] Stage 1.1: No entities detected for {v_doc.uuid}.")
            # Fallback for Stage 1 if AI fails: mark processed anyway to avoid loops
            v_doc.status = "PROCESSED"
            v_doc.last_processed_at = datetime.now().isoformat()
            self.logical_repo.save(v_doc)
            return

        # [STAGE 1.1] Extract Classification & Type Tags
        # Use full list of types detected across all entities for high-level tags
        all_tags = []
        for ent in detected_entities:
            types = ent.get("doc_types", [])
            for t in types:
                if t and t not in all_tags:
                    all_tags.append(t)
        
        v_doc.type_tags = all_tags
        # Note: We don't mark as PROCESSED yet, as splitting might replace this document

        # --- Stage 1.2: Structural Splitting & Segmentation ---
        # Skip if MANUAL_EDIT is present (User already structured it)
        if is_manual:
             print(f"[Canonizer] Manually edited doc {v_doc.uuid} detected. Skipping auto-split.")
             return

        # If Stage 1.1 identified clear boundaries (page_indices), we use them.
        # Otherwise, fall back to Stage 1.2 identify_entities call.
        
        has_clear_boundaries = all(ent.get("page_indices") for ent in detected_entities)
        
        if is_hybrid and not has_clear_boundaries:
            # High complexity splitting required
            print(f"[Canonizer] Stage 1.1 found hybrid but no clear boundaries. Triggering Stage 1.2.")
            split_candidates = self.analyzer.identify_entities(full_text, detected_entities=detected_entities)
        else:
            # Use Stage 1.1 results directly (Single or clearly segmented Hybrid)
            split_candidates = []
            for ent in detected_entities:
                split_candidates.append({
                    "types": ent.get("doc_types", ["OTHER"]),
                    "pages": ent.get("page_indices", list(range(1, len(pages_text) + 1))),
                    "confidence": ent.get("confidence", 1.0),
                    "direction": ent.get("direction"),
                    "tenant_context": ent.get("tenant_context")
                })
            
            if not is_hybrid:
                print(f"[STAGE 1.1] Single document identified. Skipping Stage 1.2 AI call.")
            else:
                print(f"[STAGE 1.1] Hybrid document segmented via Stage 1.1. Skipping Stage 1.2.")
             
        # 4. Apply Splits to VirtualDocuments
        # We iterate the candidates.
        # 1st candidate -> Updates current v_doc.
        # 2nd+ -> Creates NEW v_doc.
        
        original_source_map = v_doc.source_mapping # Keep reference
        # We need to check if source_mapping maps to ONE physical file for simplicity of splitting logic?
        # source_mapping is List[SourceReference]. 
        # If we have multiple sources, splitting by "page index 1..N" is tricky across files.
        # Assumption: Phase 2.0 Ingest creates 1 v_doc per 1 physical file (1 SourceRef).
        # So "Page 1" of v_doc corresponds to "Page 1" of that SourceRef.
        
        if not original_source_map: return
        
        base_ref = original_source_map[0] # Assuming single source for now
        
        for idx, candidate in enumerate(split_candidates):
            # Determine primary type for audit logic
            c_types = candidate.get("types", ["OTHER"])
            c_type = c_types[0] if c_types else "OTHER"
            c_pages = candidate.get("pages", []) # 1-based indices relative to logic doc
            
            # Map Logical Pages -> Physical Pages
            # base_ref.pages is [1, 2, 3...] usually.
            # If logic page is 1, it maps to base_ref.pages[0].
            
            new_source_pages = []
            for lp in c_pages:
                if 0 <= lp-1 < len(base_ref.pages):
                    new_source_pages.append(base_ref.pages[lp-1])
            
            if not new_source_pages: continue
            
            # Target Document
            target_doc = None
            is_new_entity = False
            
            if idx == 0:
                target_doc = v_doc # Reuse existing
            else:
                # Create NEW Split Entity
                target_doc = VirtualDocument(
                    uuid=str(uuid.uuid4()),
                    status="NEW",
                    created_at=v_doc.created_at
                )
                is_new_entity = True
            
            # [STAGE 1.1] Logic Correction & Tag Finalization
            # Follow user requested production logic: Traue nie der AI, berechne is_hybrid selbst.
            candidate_types = candidate.get("types", [])
            is_hybrid_entity = len(candidate_types) > 1
            
            # Start with doc_types
            final_tags = list(candidate_types)
            
            # Add direction as searchable tag
            direction = candidate.get("direction", "UNKNOWN")
            if direction != "UNKNOWN" and direction not in final_tags:
                final_tags.append(direction)
                
            # Add context as searchable tag (prefixed with CTX_ as requested)
            context = candidate.get("tenant_context", "UNKNOWN")
            if context != "UNKNOWN" and f"CTX_{context}" not in final_tags:
                final_tags.append(f"CTX_{context}")

            # Update Document Properties
            target_doc.status = "PROCESSED" # Mark processed so we don't loop forever
            target_doc.last_processed_at = datetime.now().isoformat()
            target_doc.type_tags = final_tags
            
            # Update Source Mapping
            target_doc.source_mapping = [SourceReference(
                file_uuid=base_ref.file_uuid,
                pages=new_source_pages,
                rotation=base_ref.rotation
            )]
            
            # [STAGE 1.1] Persist Classification Results to Semantic Data
            # This ensures direction, context and reasoning are preserved for manual inspection.
            if idx < len(detected_entities):
                 # Find matching entity from Stage 1.1 based on doc_types overlap or sequence
                 # For now, simplest is sequence as Stage 1.2 split_candidates 
                 # usually follow Stage 1.1 detected_entities order.
                 target_doc.semantic_data = detected_entities[idx]
            
            # Stage 2: Extraction (Metadata) - DISABLED per User Request
            # Extract text for specific pages
            entity_text = self._extract_range_text(pages_text, c_pages) 
            
            # Skip automated CDM extraction for now
            # cdm_data = self.analyzer.extract_canonical_data(c_type, entity_text)
            # target_doc.semantic_data = cdm_data
            
            # [STAGE 1.5] Visual Audit (Stamps, Handwritings, Signatures)
            # The Auditor decides based on DocType if a visual scan is needed.
            pf = self.physical_repo.get_by_uuid(base_ref.file_uuid)
            if pf:
                audit_res = self.visual_auditor.run_stage_1_5(
                    pdf_path=pf.file_path,
                    doc_uuid=target_doc.uuid,
                    stage_1_result={"detected_entities": [{"doc_type": c_type}]},
                    text_content=entity_text,
                    target_pages=new_source_pages
                )
                print(f"[DEBUG] Stage 1.5 Result for {target_doc.uuid[:8]}: {json.dumps(audit_res, indent=2) if audit_res else 'EMPTY'}")
                if audit_res:
                    # Persist Audit in Semantic Data
                    if target_doc.semantic_data is None:
                         target_doc.semantic_data = {}
                    target_doc.semantic_data["visual_audit"] = audit_res
                    
                    # --- THE ARBITER LOGIC ---
                    # 1. Type Integrity Check
                    integrity = audit_res.get("integrity", {})
                    if integrity.get("is_type_match") is False:
                        new_types = integrity.get("suggested_types", [])
                        if new_types:
                            print(f"[ARBITER] !!! TYPE MISMATCH !!! for {target_doc.uuid[:8]}")
                            print(f"  Expected: {c_type} | Suggested: {new_types}")
                            print(f"  Reason: {integrity.get('reasoning')}")
                            # Update local classification for this entity
                            c_type = new_types[0] if new_types else c_type
                            # Update the document's type tags
                            target_doc.type_tags = list(set(new_types + target_doc.type_tags))
                            if "direction" in target_doc.type_tags: 
                                # preserve direction if it was there, target_doc.type_tags might contain more info
                                pass

                    # 2. OCR Quality Recommendation
                    decision = audit_res.get("arbiter_decision", {})
                    print(f"[ARBITER] OCR Score: {decision.get('raw_ocr_quality_score')} | AI Score: {decision.get('ai_vision_quality_score')}")
                    print(f"[ARBITER] Recommended Source: {decision.get('primary_source_recommendation')}")
                    
                    if decision.get("primary_source_recommendation") == "AI_VISION":
                        cleaned_text = audit_res.get("layer_document", {}).get("clean_text")
                        if cleaned_text:
                            print(f"[ARBITER] Swapping OCR text with AI-repaired text (Reason: {decision.get('reasoning')})")
                            entity_text = cleaned_text
            
            target_doc.cached_full_text = entity_text
            
            # Determine export filename hint
            if c_type != "OTHER":
                 target_doc.export_filename = f"{c_type}_{target_doc.uuid[:8]}"
            
            # Save
            self.logical_repo.save(target_doc)
            print(f"[Canonizer] Saved Stage 1.1/1.2 Entity {target_doc.uuid} ({candidate.get('types')})")

            # [STAGE 1.6] Auto-Tagging
            if self.rules_engine and self.rules_engine.apply_rules_to_entity(target_doc, only_auto=True):
                 print(f"[Canonizer] Rule-based tags automatically applied to {target_doc.uuid}")
                 self.logical_repo.save(target_doc) # Persist tags
        
        print(f"[Canonizer] Stage 1 Analysis Complete for {v_doc.uuid}.")

    def _extract_range_text(self, pages_text: List[str], target_indices: List[int]) -> str:
        """Helper to join specific pages (simple join)."""
        out = []
        for i in target_indices:
            if 0 <= i-1 < len(pages_text):
                out.append(pages_text[i-1])
        return "\n\n".join(out)

    def split_entity(self, entity_uuid: str, split_after_page_index: int) -> tuple[str, str]:
        """
        Splits a Logical Entity into two parts at the specified logical page index.
        :param split_after_page_index: 0-based index of the page AFTER which to split.
                                     (e.g. 0 means split after Page 1).
        :return: (uuid_part_a, uuid_part_b)
        """
        # 1. Fetch Original
        doc = self.logical_repo.get_by_uuid(entity_uuid)
        if not doc:
             raise ValueError(f"Entity {entity_uuid} not found")
             
        # 2. Flatten Pages logic
        # List of (file_uuid, page_num, rotation)
        flat_pages = []
        if doc.source_mapping:
            for src in doc.source_mapping:
                for p in src.pages:
                    flat_pages.append({
                        "file_uuid": src.file_uuid, 
                        "page": p, 
                        "rotation": src.rotation
                    })
                    
        total_pages = len(flat_pages)
        if split_after_page_index < 0 or split_after_page_index >= total_pages - 1:
            raise ValueError(f"Invalid split index {split_after_page_index}. Total pages: {total_pages}")
            
        # 3. Slice
        # Part A: index 0 to split_after_page_index (inclusive)
        # Part B: split_after_page_index + 1 to end
        pages_a = flat_pages[:split_after_page_index+1]
        pages_b = flat_pages[split_after_page_index+1:]
        
        # 4. Helper to reconstruct SourceMappings from flat pages
        def regroup(pages_list) -> List[SourceReference]:
            mappings = []
            if not pages_list: return mappings
            
            current_uuid = pages_list[0]["file_uuid"]
            current_rot = pages_list[0]["rotation"]
            current_batch = [pages_list[0]["page"]]
            
            for item in pages_list[1:]:
                # If same file and rotation, merge?? 
                # Ideally yes. Even if pages are non-contiguous (e.g. 1,3) logic works.
                # But simple continuity check is safer for "page ranges" if UI expects ranges.
                # SourceReference.pages is `List[int]`, so [1,3] is valid.
                if item["file_uuid"] == current_uuid and item["rotation"] == current_rot:
                    current_batch.append(item["page"])
                else:
                    # Flush
                    mappings.append(SourceReference(
                        file_uuid=current_uuid,
                        pages=current_batch,
                        rotation=current_rot
                    ))
                    # Reset
                    current_uuid = item["file_uuid"]
                    current_rot = item["rotation"]
                    current_batch = [item["page"]]
            
            # Flush last
            if current_batch:
                mappings.append(SourceReference(
                    file_uuid=current_uuid,
                    pages=current_batch,
                    rotation=current_rot
                ))
            return mappings

        # 5. Update Entity A (The Original) -> Represents Top part
        doc.source_mapping = regroup(pages_a)
        doc.doc_type = json.dumps(["UNKNOWN"]) # Reset Type (Strict)
        doc.semantic_data = {}   # Reset Semantics
        doc.status = "NEW"       # Queue for Re-analysis
        self.logical_repo.save(doc)
        
        # 6. Create Entity B (The New Part) -> Represents Bottom part
        new_doc = VirtualDocument(
            entity_uuid=str(uuid.uuid4()),
            created_at=doc.created_at, # Inherit creation time
            status="NEW",
            doc_type=json.dumps(["UNKNOWN"]), # Reset Type (Strict)
            type_tags=["SPLIT_RESULT"]
        )
        new_doc.source_mapping = regroup(pages_b)
        self.logical_repo.save(new_doc)
        
        print(f"[Canonizer] Split {entity_uuid} at idx {split_after_page_index}. New parts: {doc.entity_uuid}, {new_doc.entity_uuid}")
        return (doc.entity_uuid, new_doc.entity_uuid)
        
    # Legacy wrapper if needed, or remove old methods...
    # Keeping old save_entity/process_document removed/replaced.

    def restructure_file_entities(self, file_uuid: str, new_mappings: List[List[dict]]) -> List[str]:
        """
        Phase 8.2: Atomic Restructure / Manual Transaction.
        Deletes ALL existing logical entities for this file.
        Creates NEW logical entities based on the provided page groupings.
        
        :param file_uuid: The physical file UUID (Source).
        :param new_mappings: List of List of dicts. 
                             Outer list = New Entities.
                             Inner List = Pages for that entity.
                             Example: [ [{"page": 1, "rotation":0}, {"page": 2}], [{"page": 3}] ]
        :return: List of new Entity UUIDs.
        """
        # 1. Fetch current entities (The "Old" Context)
        existing_docs = self.logical_repo.get_by_source_file(file_uuid)
        
        if not existing_docs:
            print(f"[Canonizer] Warning: No existing entities found for file {file_uuid}. Treating as fresh split.")
            # This is acceptable (maybe freshly imported and not yet canonized?)
        
        # 2. Transaction Scope
        # We simulate a transaction by deleting then creating.
        # Ideally using db.transaction if exposed, but for now we assume repo operations are safe enough.
        # If we crash between delete and create, we have data loss (but file remains in Vault).
        # Risk accepted for Phase 8.
        
        print(f"[Canonizer] RESTRUCTURE TRANSACTION: Deleting {len(existing_docs)} old entities for {file_uuid}...")
        
        # DELETE OLD
        for old_doc in existing_docs:
            self.logical_repo.delete_by_uuid(old_doc.entity_uuid)
            
        # CREATE NEW
        new_uuids = []
        created_at_ts = None
        if existing_docs:
            created_at_ts = existing_docs[0].created_at # Inherit timestamp
            
        for group in new_mappings:
            # Construct SourceMapping
            # group is list of dicts: {'page': 1, 'rotation': 0}
            # We need to form a SourceReference(file_uuid, [pages], rotation)
            # Assuming homogeneous rotation for simplicity or splitting references.
            
            # Simple Grouper by rotation
            current_rot = 0
            current_pages = []
            refs = []
            
            # Sort by page to be safe?
            # group.sort(key=lambda x: x['page'])
            
            for item in group:
                p = item['page']
                r = item.get('rotation', 0)
                
                # If rotation changes, we MUST split the reference? 
                # (SourceReference has one rotation).
                # Simpler: Just make one SourceReference per page if they differ, 
                # or group properly.
                # For Phase 8 MVP: We assume one SourceReference per contiguous block or just list of pages.
                
                if not current_pages:
                    current_rot = r
                    current_pages = [p]
                else:
                    if r == current_rot:
                        current_pages.append(p)
                    else:
                        # Flush
                        refs.append(SourceReference(file_uuid, current_pages, current_rot))
                        current_rot = r
                        current_pages = [p]
                        
            if current_pages:
                 refs.append(SourceReference(file_uuid, current_pages, current_rot))
                 
            # Create Entity
            new_id = str(uuid.uuid4())
            new_doc = VirtualDocument(
                entity_uuid=new_id,
                source_mapping=refs,
                # STRICT RESET
                doc_type=json.dumps(["UNKNOWN"]),
                semantic_data={}, 
                status="READY_FOR_PIPELINE", # Commit -> Ready for Stage 1
                created_at=created_at_ts,
                type_tags=["MANUAL_STRUCTURE"]
            )
            self.logical_repo.save(new_doc)
            new_uuids.append(new_id)
            
        print(f"[Canonizer] RESTRUCTURE COMMIT: Created {len(new_uuids)} new entities.")
        return new_uuids
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
                 
    def _save_entity(self, entity: CanonicalEntity):
        """
        Phase 102: Save Canonical Result to Stage 0/1.
        """
        import uuid
        from core.models.virtual import VirtualDocument, SourceReference
        
        new_uuid = str(uuid.uuid4())
        
        # Build source mapping
        # Assumption: entity.source_doc_uuid is the physical file UUID
        source_mapping = [SourceReference(
            file_uuid=entity.source_doc_uuid,
            pages=entity.page_range or []
        )]
        
        v_doc = VirtualDocument(
            uuid=new_uuid,
            status="NEW",
            source_mapping=source_mapping,
            semantic_data=entity.model_dump(),
            created_at=datetime.now().isoformat()
        )
        
        # Export filename hint
        v_doc.export_filename = f"{entity.doc_type.value}_{new_uuid[:8]}"
        
        try:
            self.logical_repo.save(v_doc)
            print(f"[Canonizer] Saved Stage 0 Entity {new_uuid} from AI result ({entity.doc_type.value})")
        except Exception as e:
            print(f"[Canonizer] Error saving AI entity: {e}")
        
    def _fuzzy_identity_match(self, party_name: str, party_address: str, profile: IdentityProfile) -> bool:
        """
        Robust identity check inspired by user scenario.
        Tolerates OCR noise via scoring and PLZ-first strategy.
        """
        if not party_name and not party_address:
            return False
            
        text_lower = f"{party_name or ''} {party_address or ''}".lower()
        
        # 1. HARTER CHECK: Postleitzahlen (PLZ)
        for kw in profile.address_keywords:
            if kw.isdigit() and len(kw) == 5:
                if kw in text_lower:
                    return True

        # 2. WEICHER CHECK: Scoring
        score = 0.0
        threshold = 0.8
        
        search_terms = []
        if profile.name: search_terms.append(profile.name)
        if profile.company_name: search_terms.append(profile.company_name)
        search_terms += profile.aliases
        search_terms += profile.company_aliases
        search_terms += [k for k in profile.address_keywords if not k.isdigit()]

        for term in set(search_terms):
            if not term or len(term) < 3: continue
            clean_term = term.lower()
            if clean_term in text_lower:
                score += 1.0
            elif len(clean_term) >= 5:
                prefix = clean_term[:5]
                if prefix in text_lower:
                    score += 0.5
                parts = clean_term.split()
                for part in parts:
                    if len(part) > 3 and part in text_lower:
                        score += 0.3
                        
        return score >= threshold

    def _classify_direction(self, entity: CanonicalEntity):
        """
        Phase 101: Semantic Direction Classification.
        Uses robust fuzzy matching for IdentityProfiles.
        """
        # Load Structured Profiles
        priv_json = self.config.get_private_profile_json()
        bus_json = self.config.get_business_profile_json()
        
        identities = []
        try:
            if priv_json: identities.append(IdentityProfile.model_validate_json(priv_json))
            if bus_json: identities.append(IdentityProfile.model_validate_json(bus_json))
        except Exception as e:
            print(f"[Canonizer] Profile Load Error: {e}")

        # Check Sender
        sender_name = entity.parties.sender.name
        sender_addr = entity.parties.sender.address
        for prof in identities:
            if self._fuzzy_identity_match(sender_name, sender_addr, prof):
                entity.direction = "OUTGOING"
                return

        # Check Recipient
        recipient_name = entity.parties.recipient.name
        recipient_addr = entity.parties.recipient.address
        for prof in identities:
            if self._fuzzy_identity_match(recipient_name, recipient_addr, prof):
                entity.direction = "INCOMING"
                return
