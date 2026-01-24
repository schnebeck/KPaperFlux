import sqlite3
import json
import uuid
from typing import Optional, List, Any
from decimal import Decimal
from datetime import datetime
from core.document import Document

class DatabaseManager:
    """
    Manages SQLite database connections and schema.
    """
    
    def __init__(self, db_path: str = "kpaperflux.db"):
        self.db_path = db_path
        self.connection = None
        self._connect()

    def _connect(self):
        """Establish connection to the database."""
        # check_same_thread=False allows using the connection across threads (Worker support)
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        # Enable foreign keys
        self.connection.execute("PRAGMA foreign_keys = ON")
        # Enable WAL mode for better concurrency
        self.connection.execute("PRAGMA journal_mode = WAL")

    def init_db(self):
        """Initialize the database schema."""
        
        # Phase 6: Removed Legacy Table Migration
        # self._migrate_to_view()

        # REMOVED: documents_legacy table
        
        # Overlays: Currently tied to Legacy ID. Disabling for now as part of legacy removal.
        # create_overlays_table = ... 
        
        create_physical_files_table = """
        CREATE TABLE IF NOT EXISTS physical_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_uuid TEXT UNIQUE NOT NULL,
            original_filename TEXT,
            file_path TEXT,
            phash TEXT,
            file_size INTEGER,
            page_count INTEGER,
            raw_ocr_data TEXT, -- JSON page map
            ref_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_semantic_entities_table = """
        CREATE TABLE IF NOT EXISTS semantic_entities (
            entity_uuid TEXT PRIMARY KEY,
            source_doc_uuid TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            
            -- Core CDM (Fast Access)
            doc_date DATE,
            sender_name TEXT,
            
            -- Full Canonical JSON
            canonical_data TEXT, 
            
            -- Meta
            page_ranges TEXT,
            status TEXT DEFAULT 'NEW',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            -- New Logical Fields (Phase 2.0)
            source_mapping TEXT, -- JSON List of {file_uuid, pages, rotation}
            type_tags TEXT,      -- JSON List of strings
            deleted INTEGER DEFAULT 0
            
            -- Removed FK to documents table
        );
        """
        
        create_documents_view = """
        CREATE VIEW IF NOT EXISTS documents AS
        SELECT 
            s.entity_uuid as uuid, 
            p.original_filename as original_filename, 
            p.phash as phash, 
            s.canonical_data as text_content, 
            COALESCE(p.page_count, 1) as page_count,
            p.file_size as file_size, 
            s.canonical_data as semantic_data,
            '{"source_mapping": ' || IFNULL(s.source_mapping, '[]') || '}' as extra_data,
            0 as locked,
            s.deleted,
            s.created_at,
            NULL as last_processed_at,
            p.ref_count as ref_count,
            NULL as visual_audit_json,
            NULL as ai_ocr_text_page_1,
            NULL as preferred_ocr_source,
            NULL as audit_meta_json
        FROM semantic_entities s
        LEFT JOIN physical_files p ON s.source_doc_uuid = p.file_uuid;
        """
        
        with self.connection:
            # self.connection.execute(create_documents_legacy_table)
            # self.connection.execute(create_overlays_table)
            self.connection.execute(create_physical_files_table)
            self.connection.execute(create_semantic_entities_table)
            self.connection.execute("DROP VIEW IF EXISTS documents") # Recreate view to be sure
            self.connection.execute(create_documents_view)
            
            # Schema Migration: Add new columns if valid
            # We check columns dynamically
            cursor = self.connection.cursor()
            
        cursor = self.connection.cursor()
        
        # 1. Physical Files Columns
        cursor.execute("PRAGMA table_info(physical_files)")
        existing_phys_cols = {row[1] for row in cursor.fetchall()}
        
        if "ref_count" not in existing_phys_cols:
            self.connection.execute("ALTER TABLE physical_files ADD COLUMN ref_count INTEGER DEFAULT 0")
            
        if "raw_ocr_data" not in existing_phys_cols:
            self.connection.execute("ALTER TABLE physical_files ADD COLUMN raw_ocr_data TEXT")

        self.connection.commit()

    # _migrate_to_view removed (Legacy Architecture Cleanup)


    def save_audit_result(self, doc_uuid: str, clean_text: Optional[str], preferred_source: Optional[str], full_json: str):
        """
        Updates the 3 audit columns transactionally.
        """
        # Ensure columns exist in semantic_entities (Added in Phase 6 Schema)
        query = """
            UPDATE semantic_entities 
            SET canonical_data = json_set(IFNULL(canonical_data, '{}'), '$.audit.ai_ocr_text', ?),
                canonical_data = json_set(canonical_data, '$.audit.preferred_source', ?),
                canonical_data = json_set(canonical_data, '$.audit.full_json', ?)
            WHERE entity_uuid = ?
        """
        # Improved: Store in JSON inside canonical_data instead of creating 3 new columns.
        # This keeps the schema clean.
        with self.connection:
             # We might need to ensure canonical_data is not null first or use json_patch
             # SQLite json_set helps.
             # Note: logic requires doc_uuid to be entity_uuid.
            self.connection.execute(query, (clean_text, preferred_source, full_json, doc_uuid))

    def update_document_column(self, doc_uuid: str, column: str, value: Any):
        """
        Generic helper to update a single column for a document.
        Redirects to semantic_entities.
        """
        # Whitelist allowed columns to prevent injection
        allowed_columns = ["visual_audit_json", "extra_data", "semantic_data", "locked", "deleted"]
        
        if column == "semantic_data":
            # Direct update to canonical_data
            query = "UPDATE semantic_entities SET canonical_data = ? WHERE entity_uuid = ?"
            if isinstance(value, dict): value = json.dumps(value)
            
        elif column == "deleted":
             query = "UPDATE semantic_entities SET deleted = ? WHERE entity_uuid = ?"
             
        elif column == "locked":
             # We don't have locked in semantic_entities yet. Add to canonical or ignored.
             # Ignoring for now or adding to tags.
             return
             
        elif column == "visual_audit_json":
             # Store in canonical_data.audit.visual
             query = "UPDATE semantic_entities SET canonical_data = json_set(IFNULL(canonical_data, '{}'), '$.audit.visual', ?) WHERE entity_uuid = ?"
             
        elif column == "extra_data":
             # We don't have extra_data column.
             return
             
        else:
            print(f"[Database] Column '{column}' not allowed for generic update.")
            return

        with self.connection:
            self.connection.execute(query, (value, doc_uuid))

    def update_document_status(self, entity_uuid: str, new_status: str):
        """
        Helper to update processing_status in semantic_entities.
        """
        sql = "UPDATE semantic_entities SET status = ? WHERE entity_uuid = ?"
        with self.connection:
            self.connection.execute(sql, (new_status, entity_uuid))



    # insert_document removed (Legacy Architecture Cleanup)


    def get_all_documents(self) -> List[Document]:
        """
        Retrieve all documents from the database (Active/Deleted=0), joined with Semantic Entity.
        Returns a list of Document objects.
        """
        # Re-use the JOIN logic from search_documents/get_document_by_uuid
        sql = """
            SELECT 
                d.uuid, d.original_filename, d.page_count, d.created_at, d.last_processed_at, 
                d.locked, d.deleted, d.text_content, d.phash, d.semantic_data, d.extra_data,
                s.sender_name, s.doc_date, s.canonical_data, s.doc_type
            FROM documents d
            LEFT JOIN semantic_entities s ON d.uuid = s.source_doc_uuid
            WHERE d.deleted = 0
            ORDER BY d.created_at DESC
        """
        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        results = []
        
        def parse_json(val):
            if val:
                try: return json.loads(val)
                except: pass
            return None
            
        for row in rows:
            # Indices match get_document_by_uuid/search_documents
            semantic_doc = parse_json(row[9])
            extra_doc = parse_json(row[10])
            canonical_ent = parse_json(row[13])
            
            sender_str = row[11]
            date_obj = row[12]
            
            amount_val = None
            if canonical_ent and 'summary' in canonical_ent:
                amount_val = canonical_ent['summary'].get('amount')
            if not sender_str and semantic_doc and 'summary' in semantic_doc:
                sender_str = semantic_doc['summary'].get('sender_name')

            doc = Document(
                uuid=row[0],
                doc_type=row[14],
                original_filename=row[1],
                export_filename=None,
                page_count=row[2],
                created_at=row[3],
                last_processed_at=row[4],
                locked=bool(row[5]),
                deleted=bool(row[6]),
                tags=None,
                text_content=row[7],
                phash=row[8],
                semantic_data=canonical_ent if canonical_ent else semantic_doc,
                extra_data=extra_doc,
                
                sender=sender_str,
                doc_date=date_obj,
                amount=amount_val
            )
            results.append(doc)
            
        return results

    def get_all_entities_view(self) -> List[Document]:
        """
        Fetch all entities for the Document List, joined with physical file info.
        Returns Document objects where 'uuid' is the ENTITY UUID.
        Legacy fields (sender, amount) are populated from the Entity data.
        """
        sql = """
        SELECT 
            s.entity_uuid,
            s.source_doc_uuid,
            s.doc_type,
            s.doc_date,
            s.sender_name,
            s.status,
            COALESCE(p.original_filename, 'Logical Document') as filename,
            COALESCE(p.page_count, 1) as page_count,
            s.created_at,
            json_extract(s.canonical_data, '$.tags_and_flags') as tags,
            json_extract(s.canonical_data, '$.specific_data.net_amount') as net_amount,
            json_extract(s.canonical_data, '$.specific_data.gross_amount') as gross_amount
        FROM semantic_entities s
        LEFT JOIN physical_files p ON s.source_doc_uuid = p.file_uuid
        WHERE s.deleted = 0
        ORDER BY s.doc_date DESC, s.created_at DESC
        """
        
        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            # We construct a Document-like object for compatibility with DocumentListWidget
            # UUID = Entity UUID
            # Sender = Entity Sender
            # Date = Entity Date
            
            doc = Document(
                uuid=row[0], # Entity UUID
                # Store Source UUID separately? Document class doesn't have it.
                # We can inject it dynamically or use extra_data?
                # Let's put it in extra_data for safety.
                extra_data={"source_uuid": row[1], "entity_status": row[5]},
                
                doc_type=row[2],
                tags=row[9],
                original_filename=row[6],
                page_count=row[7],
                created_at=row[8],
                
                # Mapped CDM Fields
                doc_date=row[3],
                sender=row[4],
                amount=self._parse_amount_safe(row[10]),
                gross_amount=self._parse_amount_safe(row[11]),
                
                # Defaults for others
                text_content="", 
                phash="",
                locked=False,
                deleted=False, 
                semantic_data=None 
            )
            results.append(doc)
            
        return results

    def get_source_uuid_from_entity(self, entity_uuid: str) -> Optional[str]:
        """Resolve Entity UUID to Source Document UUID."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT source_doc_uuid FROM semantic_entities WHERE entity_uuid = ?", (entity_uuid,))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_source_mapping_from_entity(self, entity_uuid: str) -> Optional[list]:
        """Resolve Entity UUID to Source Mapping JSON."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT source_mapping FROM semantic_entities WHERE entity_uuid = ?", (entity_uuid,))
        row = cursor.fetchone()
        if row and row[0]:
            try: return json.loads(row[0])
            except: pass
        return None


    def get_document_by_uuid(self, uuid: str) -> Optional[Document]:
        """
        Retrieve a single document by its UUID, joined with Semantic Entity data.
        """
        # Join documents (d) with semantic_entities (s)
        sql = """
            SELECT 
                d.uuid, d.original_filename, d.page_count, d.created_at, d.last_processed_at, 
                d.locked, d.deleted, d.text_content, d.phash, d.semantic_data, d.extra_data,
                s.sender_name, s.doc_date, s.canonical_data, s.doc_type
            FROM documents d
            LEFT JOIN semantic_entities s ON d.uuid = s.source_doc_uuid
            WHERE d.uuid = ?
        """
        cursor = self.connection.cursor()
        cursor.execute(sql, (uuid,))
        row = cursor.fetchone()
        
        if row:
            # Indices:
            # 0:uuid, 1:filename, 2:pages, 3:created, 4:last, 5:locked, 6:deleted, 7:text, 8:phash
            # 9:semantic_data(doc), 10:extra_data(doc)
            # 11:sender_name(ent), 12:doc_date(ent), 13:canonical_data(ent), 14:doc_type(ent)
            
            # Helper to parse JSON safely
            def parse_json(val):
                if val:
                    try: return json.loads(val)
                    except: pass
                return None

            semantic_doc = parse_json(row[9])
            extra_doc = parse_json(row[10])
            canonical_ent = parse_json(row[13])
            
            # Merge logic: Canonical Data (Entity) > Semantic Data (Doc)
            # In Phase 92, we prioritize Entity data for top-level fields
            
            sender_str = row[11] # From Entity Column
            date_obj = row[12]   # From Entity Column
            
            # Amount is tricky, it's inside JSON. try canonical first.
            amount_val = None
            if canonical_ent and 'summary' in canonical_ent:
                amount_val = canonical_ent['summary'].get('amount')
            
            # Fallback to legacy/doc semantic if entity is missing (e.g. not processed yet)
            if not sender_str and semantic_doc and 'summary' in semantic_doc:
                sender_str = semantic_doc['summary'].get('sender_name')
                
            return Document(
                uuid=row[0],
                doc_type=row[14], # From Entity
                original_filename=row[1],
                export_filename=None,
                page_count=row[2],
                created_at=row[3],
                last_processed_at=row[4],
                locked=bool(row[5]),
                deleted=bool(row[6]),
                tags=None, # Tags are complex, need separate query usually, or inside canonical
                text_content=row[7],
                phash=row[8],
                semantic_data=canonical_ent if canonical_ent else semantic_doc, # Prioritize Entity
                extra_data=extra_doc,
                
                # Hydrated Fields
                sender=sender_str,
                doc_date=date_obj,
                amount=amount_val
            )

        return None

    def update_document_metadata(self, uuid: str, updates: dict) -> bool:
        """
        Update specific fields of a document.
        Redirects to semantic_entities if the document is a Logical Entity.
        Redirects to documents_legacy if it's a Legacy Document.
        """
        if not updates: return False
        
        # 1. Determine Target
        is_semantic = self._is_semantic_entity(uuid)
        
        if is_semantic:
            # Map fields for Semantic Update
            # Supported: sender->sender_name, doc_date, doc_type, semantic_data
            mapped_updates = {}
            if "doc_type" in updates: mapped_updates["doc_type"] = updates["doc_type"]
            if "doc_date" in updates: mapped_updates["doc_date"] = updates["doc_date"]
            if "sender" in updates: mapped_updates["sender_name"] = updates["sender"]
            if "semantic_data" in updates: 
                mapped_updates["canonical_data"] = json.dumps(updates["semantic_data"]) if isinstance(updates["semantic_data"], dict) else updates["semantic_data"]
            
            # Special handling for deleted
            if "deleted" in updates: mapped_updates["deleted"] = updates["deleted"]
                
            if mapped_updates:
                self._update_table("semantic_entities", uuid, mapped_updates, pk_col="entity_uuid")
                
            # If updates contain fields not in semantic (e.g. 'tags' which are in canonical_data now?)
            # Ignored for now or handled by specialized methods.
            return True
            
        else:
            # Legacy Update
            allowed_columns = {
                "uuid", "original_filename", "tags",
                "doc_type", "phash", "text_content",
                "page_count", "created_at", "extra_data", "last_processed_at", "export_filename",
                "locked", "deleted", "semantic_data"
            }
            
            filtered = {k: v for k, v in updates.items() if k in allowed_columns}
            if "extra_data" in filtered and isinstance(filtered["extra_data"], dict):
                filtered["extra_data"] = json.dumps(filtered["extra_data"])
                
            self._update_table("documents_legacy", uuid, filtered)
            return True

    def search_documents(self, text_query: str = None, dynamic_filters: dict = None) -> List[Document]:
        """
        Search documents by text content/filename AND/OR dynamic JSON properties.
        
        :param text_query: Search string for text_content, original_filename, or tags (LIKE %query%).
        :param dynamic_filters: Dictionary of JSON paths to values.
               Example: {"stamps.cost_center": "100"}
               Logic: json_extract(extra_data, '$.stamps.cost_center') = '100'
        :return: List of matching Documents.
        """
        
        # Base query - MATCHES get_all_documents SCHEMA (34 columns + virtuals)
        where_clauses = ["d.deleted = 0"] # Default: only active docs
        values = []
        
        if text_query:
            # We use a simple OR logic for text fields
            # Tags are removed from Documents table, so we don't search them here anymore.
            # (Future: Search semantic_data or join?)
            where_clauses.append("(text_content LIKE ? OR original_filename LIKE ?)")
            wildcard = f"%{text_query}%"
            values.extend([wildcard, wildcard])
            
        # Dynamic JSON Filters
        if dynamic_filters:
            for key, value in dynamic_filters.items():
                json_path = f"$.{key}"
                where_clauses.append("json_extract(extra_data, ?) = ?")
                values.extend([json_path, str(value)])
        
        where_sql = " AND ".join(where_clauses)
        # Updated Schema: Removed export_filename, tags (8/9)
        # Old: uuid(0), origin(1), export(2), page(3), created(4), last(5), lock(6), del(7), tags(8), text(9), phash(10), sem(11), extra(12)
        # New: uuid(0), origin(1), page(2), created(3), last(4), lock(5), del(6), text(7), phash(8), sem(9), extra(10)
        
        where_sql = " AND ".join(where_clauses)
        
        # New: Join Semantic Entities to get sender/date/amount view
        sql = f"""
            SELECT 
                d.uuid, d.original_filename, d.page_count, d.created_at, d.last_processed_at, 
                d.locked, d.deleted, d.text_content, d.phash, d.semantic_data, d.extra_data,
                s.sender_name, s.doc_date, s.canonical_data, s.doc_type
            FROM documents d
            LEFT JOIN semantic_entities s ON d.uuid = s.source_doc_uuid
            WHERE {where_sql}
        """
        
        # Sort desc
        sql += " ORDER BY d.created_at DESC"
                
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, values)
            rows = cursor.fetchall()
            
            results = []
            
            # Helper to parse JSON safely (reused logic)
            def parse_json(val):
                if val:
                    try: return json.loads(val)
                    except: pass
                return None
                
            for row in rows:
                # Indices:
                # 0:uuid, 1:filename, 2:pages, 3:created, 4:last, 5:locked, 6:deleted, 7:text, 8:phash
                # 9:semantic_data(doc), 10:extra_data(doc)
                # 11:sender_name(ent), 12:doc_date(ent), 13:canonical_data(ent), 14:doc_type(ent)

                semantic_doc = parse_json(row[9])
                extra_doc = parse_json(row[10])
                canonical_ent = parse_json(row[13])
                
                # Merge Entity Data
                sender_str = row[11]
                date_obj = row[12]
                
                amount_val = None
                if canonical_ent and 'summary' in canonical_ent:
                    amount_val = canonical_ent['summary'].get('amount')
                
                # Fallback
                if not sender_str and semantic_doc and 'summary' in semantic_doc:
                    sender_str = semantic_doc['summary'].get('sender_name')

                doc = Document(
                    uuid=row[0],
                    doc_type=row[14], 
                    original_filename=row[1],
                    export_filename=None,
                    page_count=row[2],
                    created_at=row[3],
                    last_processed_at=row[4],
                    locked=bool(row[5]),
                    deleted=bool(row[6]),
                    tags=None,
                    text_content=row[7],
                    phash=row[8],
                    semantic_data=canonical_ent if canonical_ent else semantic_doc,
                    extra_data=extra_doc,
                    
                    sender=sender_str,
                    doc_date=date_obj,
                    amount=amount_val
                )
                results.append(doc)
                
            return results
        except sqlite3.Error as e:
            print(f"Search error: {e}")
            return []

    def get_deleted_documents(self) -> List[Document]:
        """
        Wrapper for UI: Trash Bin now shows Deleted Semantic Entities.
        The physical document is just a container.
        """
        return self.get_deleted_entities_view()

    def get_available_extra_keys(self) -> list[str]:
        """
        Scan all documents for unique keys in the 'extra_data' JSON.
        Returns flattened keys like 'stamps.cost_center'.
        """
        sql = "SELECT extra_data, semantic_data FROM documents WHERE extra_data IS NOT NULL OR semantic_data IS NOT NULL"
        cursor = self.connection.cursor()
        keys = set()
        
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            for row in rows:
                # 1. Extra Data (Legacy JSON) -> Prefix 'json:'
                if row[0]:
                    try:
                        data = json.loads(row[0])
                        if isinstance(data, dict):
                            self._extract_keys_recursive(data, keys, prefix="json:")
                    except json.JSONDecodeError:
                        pass
                
                # 2. Semantic Data (AI JSON) -> Prefix 'semantic:'
                if row[1]:
                    try:
                        data = json.loads(row[1])
                        if isinstance(data, dict):
                            self._extract_keys_recursive(data, keys, prefix="semantic:")
                    except json.JSONDecodeError:
                        pass
                        
            return sorted(list(keys))
            
        except sqlite3.Error as e:
            print(f"Key Discovery Error: {e}")
            return []

    def _extract_keys_recursive(self, obj, keys_set, prefix=""):
        """Helper to flatten JSON keys."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                # Avoid appending dot if prefix ends with colon (json:key instead of json:.key)
                sep = "." if prefix and not prefix.endswith(":") else ""
                new_prefix = f"{prefix}{sep}{k}"
                
                if isinstance(v, dict):
                     self._extract_keys_recursive(v, keys_set, new_prefix)
                elif isinstance(v, list):
                     keys_set.add(new_prefix) 
                     for item in v:
                         if isinstance(item, dict):
                             self._extract_keys_recursive(item, keys_set, new_prefix)
                else:
                     keys_set.add(new_prefix)
            

    def search_documents_advanced(self, query: dict) -> List[Document]:
        """
        Search Semantic Entities using a structured query.
        Joins semantic_entities (s) and documents (d).
        """
        # Fields matching get_all_entities_view
        sql = """
            SELECT 
                s.entity_uuid,       -- 0
                s.doc_type,          -- 1
                d.original_filename, -- 2
                d.page_count,        -- 3
                d.created_at,        -- 4 (Import Date)
                d.last_processed_at, -- 5
                d.locked,            -- 6
                s.deleted,           -- 7
                json_extract(s.canonical_data, '$.tags_and_flags') as tags, -- 8
                d.text_content,      -- 9
                d.phash,             -- 10
                s.canonical_data,    -- 11
                d.extra_data,        -- 12
                s.sender_name,       -- 13
                s.doc_date,          -- 14
                json_extract(s.canonical_data, '$.specific_data.net_amount') as amount, -- 15
                s.source_doc_uuid,   -- 16
                s.status             -- 17
            FROM semantic_entities s
            JOIN documents d ON s.source_doc_uuid = d.uuid
            WHERE s.deleted = 0
        """
        params = []
        
        if query:
            # We enforce s.deleted=0 above. If query wants to search Trash, 
            # it should be handled via get_deleted_entities_view or 
            # we need to remove the WHERE restriction if query specifies deleted explicitly.
            # But currently UI separates them. Search implies active.
            
            # Update query builder to use prefixes? 
            # _build_advanced_sql needs adaptation or we handle it here.
            # We'll rely on a slightly modified _build_advanced_sql logic or pass a mapping.
            # For now, let's assume _build_advanced_sql needs to handle ambiguity.
            
            where_clause = self._build_advanced_sql(query, params)
            if where_clause:
                sql += f" AND ({where_clause})"
                
        sql += " ORDER BY s.doc_date DESC, d.created_at DESC" # Match list sort
        
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                semantic = None
                if row[11]:
                    try: semantic = json.loads(row[11])
                    except: pass
                    
                extra = None
                if row[12]:
                    try: extra = json.loads(row[12])
                    except: pass
                    
                doc = Document(
                    uuid=row[0], # Entity UUID
                    doc_type=row[1],
                    original_filename=row[2],
                    export_filename=None, # Removed from DB
                    page_count=row[3],
                    created_at=row[4],
                    last_processed_at=row[5],
                    locked=bool(row[6]),
                    deleted=bool(row[7]),
                    tags=row[8],
                    text_content=row[9],
                    phash=row[10],
                    semantic_data=semantic,
                    extra_data=extra,
                    
                    sender=row[13],
                    doc_date=row[14],
                    amount=self._parse_amount_safe(row[15])
                )
                # Inject extra needed by UI
                if not doc.extra_data: doc.extra_data = {}
                doc.extra_data["source_uuid"] = row[16]
                doc.extra_data["entity_status"] = row[17]
                
                results.append(doc)
            return results
        except sqlite3.Error as e:
            print(f"Advanced Search Error: {e}")
            return []


    def _parse_amount_safe(self, val):
        """Helper to parse amount strings that might contain commas."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            # Replace German comma with dot
            clean_val = val.replace(",", ".")
            try:
                return float(clean_val)
            except ValueError:
                return None
        return None

    def _build_advanced_sql(self, node: dict, params: list) -> str:
        if not node:
            return ""
            
        # Recursive Group
        if "operator" in node and "conditions" in node:
            op = node["operator"].upper()
            if op not in ["AND", "OR"]:
                op = "AND"
            
            parts = []
            for child in node["conditions"]:
                child_sql = self._build_advanced_sql(child, params)
                if child_sql:
                    parts.append(child_sql)
            
            if not parts:
                return ""
            
            separator = f" {op} "
            joined = separator.join(parts)
            return f"({joined})" if len(parts) > 1 else parts[0]
            
        # Leaf Condition
        field = node.get("field")
        op = node.get("op", "equals")
        val = node.get("value")
        negate = node.get("negate", False)
        
        if not field:
            return ""
            
        # Map Field
        col_sql = ""
        is_json_field = False
        json_pattern = ""
        
        if field.startswith("json:"):
            is_json_field = True
            key = field[5:]
            # Target extra_data (Physical Meta)
            target_col = "d.extra_data"
            parts = key.split(".")
            json_pattern = "%" + "%".join(parts) + "%"
            
        elif field.startswith("semantic:"):
            is_json_field = True
            key = field[9:]
            # Target canonical_data (Logical Meta)
            target_col = "s.canonical_data"
            parts = key.split(".")
            json_pattern = "%" + "%".join(parts) + "%"
            
        else:
            # Prevent SQL Injection on column names via allowlist
            allowed_cols = [
                "doc_type", "original_filename", "export_filename", "page_count", "created_at",
                "last_processed_at", "locked", "deleted", "tags", "text_content", "phash", "uuid",
                "v_sender", "v_doc_date", "v_amount",
                "amount", "doc_date", "sender"
            ]
            
            if field in allowed_cols:
                # Map Aliases to Semantic/Physical Columns
                if field == "amount": 
                    # Extract from JSON or alias if virtual col existed? 
                    # Query uses extract alias 'amount'. But WHERE clause needs raw expression
                    col_sql = "json_extract(s.canonical_data, '$.specific_data.net_amount')"
                elif field == "v_amount": 
                    col_sql = "json_extract(s.canonical_data, '$.specific_data.net_amount')"
                    
                elif field == "doc_date": col_sql = "s.doc_date"
                elif field == "v_doc_date": col_sql = "s.doc_date"
                
                elif field == "sender": col_sql = "s.sender_name"
                elif field == "v_sender": col_sql = "s.sender_name"
                
                # Semantic Columns
                elif field == "doc_type": col_sql = "s.doc_type"
                elif field == "deleted": col_sql = "s.deleted"
                elif field == "uuid": col_sql = "s.entity_uuid"
                
                # Physical Columns
                elif field == "original_filename": col_sql = "d.original_filename"
                elif field == "export_filename": col_sql = "d.export_filename"
                elif field == "page_count": col_sql = "d.page_count"
                elif field == "created_at": col_sql = "d.created_at"
                elif field == "last_processed_at": col_sql = "d.last_processed_at"
                elif field == "locked": col_sql = "d.locked"
                elif field == "text_content": col_sql = "d.text_content"
                elif field == "phash": col_sql = "d.phash"
                
                elif field == "tags":
                     col_sql = "json_extract(s.canonical_data, '$.tags_and_flags')"
                     
                else: 
                     # Fallback for safe cols not manually mapped?
                     col_sql = f"d.{field}" 
                     
                # Standard Logic for ops
            else:
                return "" # Ignore unknown columns
                
        # Map Operator
        sql_op = "="
        if op == "contains":
            sql_op = "LIKE"
            val = f"%{val}%"
        elif op == "starts_with":
            sql_op = "LIKE"
            val = f"{val}%"
        elif op == "gt":
            sql_op = ">"
        elif op == "lt":
            sql_op = "<"
        elif op == "gte":
            sql_op = ">="
        elif op == "lte":
            sql_op = "<="
        
        # Handle special IS EMPTY / IS NOT EMPTY
        if op == "is_empty":
            if is_json_field:
                # Recursive NOT EXISTS
                # target_col already has table prefix
                return f"NOT EXISTS (SELECT 1 FROM json_tree({target_col}) WHERE fullkey LIKE ? AND value != '' AND value IS NOT NULL)"
            else:
                return f"({col_sql} IS NULL OR {col_sql} = '')"
        elif op == "is_not_empty":
            if is_json_field:
                return f"EXISTS (SELECT 1 FROM json_tree({target_col}) WHERE fullkey LIKE ? AND value != '' AND value IS NOT NULL)"
            else:
                return f"({col_sql} IS NOT NULL AND {col_sql} != '')"
        elif op in ["in", "is_in_list"]:
             # List Operator: val should be a list of strings/ints
             if not isinstance(val, list) or not val:
                 # Empty list -> Matches Nothing
                 return "1=0"
             
             if is_json_field:
                 # JSON Array containment or direct value?
                 # Assuming direct value check against list
                 # We construct multiple LIKE ? OR ... 
                 # OR better: EXISTS ... AND value IN (?,?,?)
                 # SQLite json_tree value is string/num.
                 placeholders = ",".join(["?"] * len(val))
                 params.append(json_pattern)
                 params.extend(val)
                 return f"EXISTS (SELECT 1 FROM json_tree({target_col}) WHERE fullkey LIKE ? AND value IN ({placeholders}))"
             else:
                 placeholders = ",".join(["?"] * len(val))
                 params.extend(val)
                 return f"{col_sql} IN ({placeholders})"
            
        sql = f"{col_sql} {sql_op} ?"
        if is_json_field:
             # Logic for JSON...
             if op in ["is_empty", "is_not_empty"]:
                  params.append(json_pattern)
             else:
                  params.append(json_pattern)
                  params.append(val)
                  sql = f"EXISTS (SELECT 1 FROM json_tree({target_col}) WHERE fullkey LIKE ? AND value {sql_op} ?)"

        else:
             params.append(val)

        if negate:
             return f"NOT ({sql})"
        return sql

    def delete_document(self, uuid: str) -> bool:
        """
        Delete a document by its UUID (Soft Delete).
        Applies to Semantic Entity.
        """
        sql_ent = "UPDATE semantic_entities SET deleted = 1 WHERE entity_uuid = ?"
        
        cursor = self.connection.cursor()
        with self.connection:
            cursor.execute(sql_ent, (uuid,))
            
        return cursor.rowcount > 0

    def purge_document(self, uuid: str) -> bool:
        """
        Permanently delete a document by its UUID (Hard Delete).
        """
        sql = "DELETE FROM semantic_entities WHERE entity_uuid = ?"
        with self.connection:
            self.connection.execute(sql, (uuid,))
            return self.connection.total_changes > 0

    def restore_document(self, uuid: str) -> bool:
        """
        Restore a soft-deleted document (Trash -> Normal).
        """
        sql_ent = "UPDATE semantic_entities SET deleted = 0 WHERE entity_uuid = ?"
        
        with self.connection:
            self.connection.execute(sql_ent, (uuid,))
            
        return self.connection.total_changes > 0

    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()

    # --- Phase 93: Tag Manager ---

    def get_semantic_entities(self, source_uuid: str) -> List[dict]:
        """
        Fetch all semantic entities linked to a source document.
        Returns list of dicts (Canonical JSON structure).
        """
        query = """
            SELECT entity_uuid, doc_type, canonical_data, page_ranges, status 
            FROM semantic_entities 
            WHERE source_doc_uuid = ?
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (source_uuid,))
        rows = cursor.fetchall()
        
        entities = []
        for row in rows:
            entity_uuid, doc_type, cdata_json, pages_json, status = row
            try:
                cdata = json.loads(cdata_json) if cdata_json else {}
                # Inject meta info back into the dict for UI convenience
                cdata['entity_uuid'] = entity_uuid
                cdata['doc_type'] = doc_type
                try:
                    cdata['page_range'] = json.loads(pages_json) if pages_json else []
                except:
                    cdata['page_range'] = []
                cdata['status'] = status
                entities.append(cdata)
            except Exception as e:
                print(f"Error parsing entity {entity_uuid}: {e}")
                
        return entities

    def get_all_tags_with_counts(self) -> dict[str, int]:
        """
        Aggregate all tags from semantic_entities and return a count for each.
        Tags are stored in canonical_data->tags_and_flags as a JSON list.
        Returns: {'tag_name': count, ...}
        """
        # Phase 99.2: Fetch from CDM
        sql = "SELECT json_extract(canonical_data, '$.tags_and_flags') FROM semantic_entities WHERE canonical_data IS NOT NULL"
        cursor = self.connection.cursor()
        
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            # Fallback if table doesn't exist yet
            return {}
        
        tag_counts = {}
        for (tags_json,) in rows:
            if not tags_json: continue
            try:
                # tags_json is a JSON string of a list: '["tag1", "tag2"]'
                tags_list = json.loads(tags_json)
                if isinstance(tags_list, list):
                    for t in tags_list:
                        if t and isinstance(t, str):
                            tag_counts[t] = tag_counts.get(t, 0) + 1
            except:
                pass
        
        return tag_counts

    def rename_tag(self, old_name: str, new_name: str) -> int:
        """
        Rename a tag across all documents.
        TODO: Implement for semantic_entities (requires complex JSON update).
        For now, this is a NO-OP to prevent crashes.
        """
        print(f"[WARN] Rename Tag '{old_name}' -> '{new_name}' not yet implemented for CDM.")
        return 0

    def delete_tag(self, tag_name: str) -> int:
        """
        Remove a tag from all documents.
        TODO: Implement for semantic_entities (requires complex JSON update).
        For now, this is a NO-OP to prevent crashes.
        """
        print(f"[WARN] Delete Tag '{tag_name}' not yet implemented for CDM.")
        return 0



    def count_documents(self, filters: dict) -> int:
        """
        Count documents matching the given filter criteria.
        Reuses _build_advanced_sql to ensure consistency with search.
        """
        # Build logical SQL fragment
        # Note: _build_advanced_sql returns a tuple (sql_str, params_list) OR just sql_str?
        # Let's check search_documents_advanced
        # It calls internal recursive function _build_advanced_sql(filters) -> (sql, params)
        
        # We need to access the private helper. 
        # But _build_advanced_sql is actually define inside the class (lines 536+).
        # Let's verify signature.
        
        params = []
        where_clause = self._build_advanced_sql(filters, params)
        
        sql = "SELECT COUNT(*) FROM documents"
        if where_clause:
            sql += f" WHERE {where_clause}"
            
            # Explicitly exclude deleted if not requested
            # search_documents_advanced adds "deleted = 0" if not specified. 
            # We should replicate that behavior or ensure filter includes it.
            # search_documents_advanced logic:
            # if "deleted" not in sql: sql += " AND deleted = 0"
            
            if "deleted" not in where_clause:
                 sql += " AND deleted = 0"
        else:
            sql += " WHERE deleted = 0"
            
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        return cursor.fetchone()[0]

    def count_entities(self, status: str = None) -> int:
        """
        Count entries in semantic_entities (Active only).
        :param status: Optional status filter (e.g. 'NEW', 'PROCESSED')
        :return: Count
        """
        sql = "SELECT COUNT(*) FROM semantic_entities WHERE deleted = 0"
        params = []
        if status:
             sql += " AND status = ?"
             params.append(status)
             
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        return cursor.fetchone()[0]
        
    def get_deleted_entities_view(self) -> list:
        """
        Fetch ALL 'soft-deleted' entities for Trash Bin view.
        Returns format compatible with get_all_entities_view (for UI List).
        """
        cursor = self.connection.cursor()
        # Same fields as get_all_entities_view
        sql = """
            SELECT 
                se.entity_uuid,
                p.file_uuid as source_uuid,
                se.doc_type,
                se.doc_date,
                se.sender_name,
                se.status,
                p.file_size,
                se.canonical_data,
                p.original_filename
            FROM semantic_entities se
            LEFT JOIN physical_files p ON se.source_doc_uuid = p.file_uuid
            WHERE se.deleted = 1
            ORDER BY se.created_at DESC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            # Helper to parse JSON tags
            tags = "[]"
            try:
                if row[7]:
                     cd = json.loads(row[7])
                     tags = json.dumps(cd.get("tags_and_flags", []))
            except:
                pass
                
            doc = Document(
                uuid=row[0], # Entity ID acts as UUID
                # source_uuid=row[1] # Not usually in Doc object, stored in extra data
                file_size=row[6],
                original_filename=row[8] if row[8] else "Unknown"
            )
            # Fill virtual fields
            doc.doc_type = row[2] or "OTHER"
            doc.doc_date = row[3] # Date Object?
            doc.sender = row[4]
            # doc.status/source_uuid not in model, stored in extra_data below
            doc.tags = None # Use extra data
            
            # Additional info used by ListWidget
            doc.extra_data = {
                "tags": tags,
                "entity_status": row[5],
                "source_uuid": row[1]
            }
            results.append(doc)
            
        return results

    def delete_entity(self, entity_uuid: str) -> bool:
        """
        Soft Delete a Semantic Entity (Move to Trash).
        Does NOT change reference counts yet.
        """
        cursor = self.connection.cursor()
        cursor.execute("UPDATE semantic_entities SET deleted = 1 WHERE entity_uuid = ?", (entity_uuid,))
        self.connection.commit()
        return cursor.rowcount > 0

    def restore_entity(self, entity_uuid: str) -> bool:
        """Restore a Soft Deleted Entity."""
        cursor = self.connection.cursor()
        cursor.execute("UPDATE semantic_entities SET deleted = 0 WHERE entity_uuid = ?", (entity_uuid,))
        self.connection.commit()
        return cursor.rowcount > 0

    def purge_entity(self, entity_uuid: str) -> bool:
        """
        Permanently Delete an Entity.
        Decrements Reference Count of Source Document.
        If RefCount == 0, Source Document is DELETED.
        """
        cursor = self.connection.cursor()
        
        # 1. Get Source UUID
        cursor.execute("SELECT source_doc_uuid FROM semantic_entities WHERE entity_uuid = ?", (entity_uuid,))
        row = cursor.fetchone()
        if not row:
            return False
            
        source_uuid = row[0]
        
        # 2. Delete Entity Row
        cursor.execute("DELETE FROM semantic_entities WHERE entity_uuid = ?", (entity_uuid,))
        
        # 3. Update Reference Count
        # 3. Update Reference Count
        # source_uuid is the physical file UUID (since entities point to it)
        cursor.execute("SELECT COUNT(*) FROM semantic_entities WHERE source_doc_uuid = ?", (source_uuid,))
        remaining = cursor.fetchone()[0]
        
        cursor.execute("UPDATE physical_files SET ref_count = ? WHERE file_uuid = ?", (remaining, source_uuid))
        
        # 4. Check for Zero References -> Delete Physical File Entry
        if remaining == 0:
            print(f"[RefCount] Physical File {source_uuid} has 0 references. Deleting DB Entry.")
            
            # Ideally we should also delete the file from disk here or mark for sweep.
            # But the caller (Vault) might handle it.
            # For now, just clean DB.
            cursor.execute("DELETE FROM physical_files WHERE file_uuid = ?", (source_uuid,))
            
    def purge_all_data(self, vault_path: str) -> bool:
        """
        DESTRUCTIVE: Deletes ALL data from database and vault.
        Used for development/testing reset.
        """
        import os
        import shutil
        
        try:
            cursor = self.connection.cursor()
            
            # 1. Drop Tables (Schema Reset)
            cursor.execute("DROP VIEW IF EXISTS documents")
            cursor.execute("DROP TABLE IF EXISTS overlays")
            cursor.execute("DROP TABLE IF EXISTS semantic_entities")
            cursor.execute("DROP TABLE IF EXISTS physical_files")
            cursor.execute("DROP TABLE IF EXISTS documents_legacy") # Cleanup legacy
            
            # 2. Reset Sequences
            try:
                cursor.execute("DELETE FROM sqlite_sequence")
            except:
                pass 
            
            self.connection.commit()
            
            # 3. Re-Initialize Database (Recreate empty tables)
            self.init_db()
            
            # 3. Clear Vault Directory
            if vault_path and os.path.exists(vault_path):
                for filename in os.listdir(vault_path):
                    file_path = os.path.join(vault_path, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        print(f"Failed to delete {file_path}. Reason: {e}")
                        return False
            
            return True
        except Exception as e:
            print(f"Purge failed: {e}")
            self.connection.rollback()
            return False

    def get_source_mapping_from_entity(self, entity_uuid: str) -> Optional[list]:
        """
        Get the 'source_mapping' JSON (list of SourceReferences) for an entity.
        Used by GUI to find the physical file for a Logical Entity (Shadow Document).
        """
        cursor = self.connection.cursor()
        cursor.execute("SELECT source_mapping FROM semantic_entities WHERE entity_uuid = ?", (entity_uuid,))
        row = cursor.fetchone()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except:
                pass
        return None

