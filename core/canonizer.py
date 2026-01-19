
import json
from typing import List, Optional
from core.database import DatabaseManager
from core.document import Document
from core.models.canonical_entity import CanonicalEntity, DocType
from core.ai_analyzer import AIAnalyzer
from core.config import AppConfig

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
        # Or add a flag 'canonization_status' to documents table?
        # For now, simplistic query: Get all docs, check if they have entities. 
        # Better: Query docs where id NOT IN (select source_doc_uuid from semantic_entities)
        
        cursor = self.db.connection.cursor()
        query = """
            SELECT d.uuid, d.text_content, d.semantic_data 
            FROM documents d
            WHERE d.uuid NOT IN (SELECT source_doc_uuid FROM semantic_entities)
            LIMIT ?
        """
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        
        for row in rows:
            uuid, text_content, semantic_data_json = row
            # Load Raw Semantics (if any)
            semantic_data = {}
            if semantic_data_json:
                try:
                    semantic_data = json.loads(semantic_data_json)
                except:
                    pass
            
            self.process_document(uuid, text_content, semantic_data)
            
    def process_document(self, uuid: str, text_content: str, semantic_data: dict = None):
        """
        Process a single document: Identify Entities and Persist.
        """
        if not self.analyzer:
            return

        print(f"[Canonizer] Processing {uuid}...")
        
        # 1. Identify Entities (AI Step 1)
        # Pass semantic_data (if any) to guide the splitter 
        entities_meta = self.analyzer.identify_entities(text_content, semantic_data)
        
        if not entities_meta:
            # Fallback: Assume whole file is 1 Unknown/Generic Entity
            entities_meta = [{"type": "OTHER", "pages": [], "confidence": 0.0}]
            
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
             
             # Create Entity Object
             try:
                 entity = CanonicalEntity(
                     source_doc_uuid=uuid,
                     doc_type=doc_type,
                     page_range=page_range,
                     **cdm_data
                 )
                 
                 # Validate & Save
                 self.save_entity(entity)
                 print(f"[Canonizer] Saved Entity {doc_type.name} (Pages {page_range})")
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
