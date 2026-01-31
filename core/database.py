"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/database.py
Version:        1.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Gemini 3pro
Description:    Manages SQLite database connections and schema. Provides
                a high-level API for interacting with document metadata,
                physical files, and advanced filtering/search.
------------------------------------------------------------------------------
"""

import sqlite3
import json
import uuid
import traceback
from typing import Optional, List, Any, Dict, Tuple, Set
from decimal import Decimal
from datetime import datetime
from core.document import Document

class DatabaseManager:
    """
    Manages SQLite database connections and schema.
    """
    
    def __init__(self, db_path: str = "kpaperflux.db") -> None:
        """
        Initializes the DatabaseManager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None
        self._connect()

    def _connect(self) -> None:
        """
        Establishes a connection to the database and configures performance PRAGMAs.
        """
        # check_same_thread=False allows using the connection across threads (Worker support)
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        # Enable foreign keys
        self.connection.execute("PRAGMA foreign_keys = ON")
        # Enable WAL mode for better concurrency
        self.connection.execute("PRAGMA journal_mode = WAL")

    def init_db(self) -> None:
        """
        Initializes the database schema if it does not exist.
        Handles migrations for various project phases.
        """
        create_physical_files_table = """
        CREATE TABLE IF NOT EXISTS physical_files (
            uuid TEXT PRIMARY KEY,
            phash TEXT,
            file_path TEXT,
            original_filename TEXT,
            file_size INTEGER,
            raw_ocr_data TEXT, -- JSON page map (page_num -> text)
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            page_count_phys INTEGER,
            ref_count INTEGER DEFAULT 0
        );
        """

        create_virtual_documents_table = """
        CREATE TABLE IF NOT EXISTS virtual_documents (
            uuid TEXT PRIMARY KEY,
            source_mapping TEXT, -- JSON List of {file_uuid, pages, rotation}
            status TEXT DEFAULT 'NEW',
            export_filename TEXT,
            last_used DATETIME,
            last_processed_at DATETIME,
            is_immutable INTEGER DEFAULT 0,
            thumbnail_path TEXT,
            cached_full_text TEXT,
            semantic_data TEXT, -- JSON of Canonical Data
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            deleted INTEGER DEFAULT 0,
            
            -- Stage 0/1 Powerhouse: Generated Count
            page_count_virt INTEGER DEFAULT 0,
            type_tags TEXT, -- JSON List of strings
            
            -- Filter Columns (Phase 105)
            sender TEXT,
            doc_date TEXT,
            amount REAL,
            tags TEXT
        );
        """

        create_virtual_documents_fts = """
        CREATE VIRTUAL TABLE IF NOT EXISTS virtual_documents_fts USING fts5(
            uuid UNINDEXED,
            export_filename,
            type_tags,
            cached_full_text,
            content='virtual_documents',
            content_rowid='rowid'
        );
        """

        if not self.connection:
            return

        with self.connection:
            self.connection.execute(create_physical_files_table)
            self.connection.execute(create_virtual_documents_table)
            self.connection.execute(create_virtual_documents_fts)

            # Migration: Ensure type_tags exists if table was created earlier
            try:
                self.connection.execute("ALTER TABLE virtual_documents ADD COLUMN type_tags TEXT")
            except sqlite3.OperationalError:
                pass  # Already exists

            # Phase 105 Filter Column Migrations
            for col, col_type in [("sender", "TEXT"), ("doc_date", "TEXT"), ("amount", "REAL"), ("tags", "TEXT")]:
                try:
                    self.connection.execute(f"ALTER TABLE virtual_documents ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass

            # Phase 106: Auto-Tagging Rules migrated to FilterTree
            self.connection.execute("DROP TABLE IF EXISTS tagging_rules")

            # Ensure legacy view is gone
            self.connection.execute("DROP VIEW IF EXISTS documents")
            self._create_fts_triggers()

    def matches_condition(self, entity_uuid: str, query_dict: Dict[str, Any]) -> bool:
        """
        Phase 106: Check if a specific document matches a rule's filter conditions.
        Uses the existing SQL-based filter engine.

        Args:
            entity_uuid: The UUID of the virtual document to check.
            query_dict: A dictionary representing the search/filter criteria.

        Returns:
            True if the document matches the conditions, False otherwise.
        """
        if not self.connection:
            return False

        if not query_dict:
            return True

        where_clause, params = self._build_where_clause(query_dict)
        sql = f"SELECT 1 FROM virtual_documents WHERE uuid = ? AND ({where_clause})"

        try:
            cursor = self.connection.cursor()
            cursor.execute(sql, [entity_uuid] + params)
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            print(f"[DB] Error in matches_condition: {e}")
            traceback.print_exc()
            return False




    def update_document_metadata(self, uuid: str, updates: Dict[str, Any]) -> bool:
        """
        Updates specific fields of a virtual document in the database.

        Args:
            uuid: The UUID of the document to update.
            updates: A dictionary of fields and their new values.

        Returns:
            True if the update was successful, False otherwise.
        """
        if not self.connection or not updates:
            return False

        # Whitelist of allowed fields for Stage 0/1/2
        allowed = [
            "status", "export_filename", "deleted", "is_immutable", "locked",
            "type_tags", "cached_full_text", "last_used", "last_processed_at",
            "semantic_data", "sender", "amount", "doc_date", "tags"
        ]
        filtered = {k: v for k, v in updates.items() if k in allowed}

        if "locked" in filtered:
            filtered["is_immutable"] = int(filtered.pop("locked"))

        if "type_tags" in filtered and isinstance(filtered["type_tags"], list):
            filtered["type_tags"] = json.dumps(filtered["type_tags"])

        if "tags" in filtered and isinstance(filtered["tags"], list):
            filtered["tags"] = json.dumps(filtered["tags"])

        if "semantic_data" in filtered and isinstance(filtered["semantic_data"], dict):
            filtered["semantic_data"] = json.dumps(filtered["semantic_data"], ensure_ascii=False)

        if filtered:
            self._update_table("virtual_documents", uuid, filtered, pk_col="uuid")
            return True
        return False

    def touch_last_used(self, uuid: str):
        """Update last_used timestamp to current local time."""
        from datetime import datetime
        now = datetime.now().isoformat()
        self.update_document_metadata(uuid, {"last_used": now})

    def update_document_status(self, uuid: str, new_status: str):
        """Helper to update status in virtual_documents."""
        sql = "UPDATE virtual_documents SET status = ? WHERE uuid = ?"
        with self.connection:
            self.connection.execute(sql, (new_status, uuid))


    def get_document_by_uuid(self, uuid: str) -> Optional[Document]:
        """
        Fetches a single document by its UUID.

        Args:
            uuid: The UUID of the virtual document.

        Returns:
            A Document object if found, None otherwise.
        """
        if not self.connection:
            return None

        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags, 
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags
            FROM virtual_documents
            WHERE uuid = ?
        """
        cursor = self.connection.cursor()
        cursor.execute(sql, (uuid,))
        row = cursor.fetchone()
        if row:
            return self._row_to_doc(row)
        return None

    def reset_document_for_reanalysis(self, uuid: str):
        """Phase 102: Reset logical entity status for fresh AI processing without deleting the row."""
        sql = """
            UPDATE virtual_documents 
            SET status = 'NEW', 
                type_tags = '[]', 
                semantic_data = NULL,
                last_processed_at = NULL
            WHERE uuid = ?
        """
        with self.connection:
            self.connection.execute(sql, (uuid,))

    def queue_for_semantic_extraction(self, uuids: list[str]):
        """Phase 107: Queue documents for Stage 2 processing skip Stage 1."""
        sql = """
            UPDATE virtual_documents 
            SET status = 'STAGE2_PENDING'
            WHERE uuid = ? AND deleted = 0
        """
        with self.connection:
            for uid in uuids:
                self.connection.execute(sql, (uid,))

    def get_deleted_documents(self) -> List[Document]:
        """
        Wrapper for UI: Trash Bin now shows Deleted Semantic Entities.
        The physical document is just a container.
        """
        return self.get_deleted_entities_view()
    def get_available_extra_keys(self) -> list[str]:
        """
        Scan all documents for unique keys in JSON data.
        """
        keys = set()
        cursor = self.connection.cursor()
        
        # 1. Semantic Data Keys (AI Results)
        try:
            cursor.execute("SELECT semantic_data FROM virtual_documents WHERE semantic_data IS NOT NULL")
            for row in cursor.fetchall():
                if row[0]:
                    try:
                        data = json.loads(row[0])
                        if isinstance(data, dict):
                             self._extract_keys_recursive(data, keys, prefix="semantic:")
                    except: pass
        except: pass

        # 2. Add Stamp Labels (Phase 105: Dynamic Stamps)
        for label in self.get_unique_stamp_labels():
            keys.add(f"stamp_field:{label}")
                        
        return sorted(list(keys))

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
        Search Virtual Documents using a structured nested query object.
        """
        if not query or not query.get("conditions") and not query.get("field"):
             return self.get_all_entities_view()

        where_clause, params = self._build_where_clause(query)
        
        # Phase 105 Fix: Ensure we don't return deleted documents by default in Advanced Search
        # unless specifically filtered for 'deleted' (Trash Mode).
        if "deleted" not in where_clause.lower():
            where_clause = f"({where_clause}) AND deleted = 0"
            
        sql = f"""
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags,
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags
            FROM virtual_documents
            WHERE {where_clause}
            ORDER BY created_at DESC
        """
        
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append(self._row_to_doc(row))
        return results

    def count_documents_advanced(self, query: dict) -> int:
        """
        Efficiently count documents matching an advanced query.
        """
        if not query or (not query.get("conditions") and not query.get("field")):
            return self.count_documents()

        where_clause, params = self._build_where_clause(query)
        if "deleted" not in where_clause.lower():
            where_clause = f"({where_clause}) AND deleted = 0"

        sql = f"SELECT COUNT(*) FROM virtual_documents WHERE {where_clause}"
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        return cursor.fetchone()[0]

    def _build_where_clause(self, node: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """
        Recursively builds a SQL WHERE clause from a nested query dictionary.

        Args:
            node: A dictionary representing a query node (condition or group).

        Returns:
            A tuple containing the SQL string and the list of parameters.
        """
        if "field" in node:
            # Single condition
            field = node["field"]
            op = node["op"]
            val = node.get("value")
            negate = node.get("negate", False)

            # 1. Map Field to SQL Expression
            expr = self._map_field_to_sql(field)

            # 2. Map Operator to SQL
            clause, params = self._map_op_to_sql(expr, op, val)

            if negate:
                return f"NOT ({clause})", params
            return clause, params

        if "conditions" in node:
            # A group (AND/OR)
            logic_op = node.get("operator", "AND").upper()
            sub_clauses = []
            all_params = []

            for cond in node["conditions"]:
                clause, params = self._build_where_clause(cond)
                if clause:
                    sub_clauses.append(f"({clause})")
                    all_params.extend(params)

            if not sub_clauses:
                return "1=1", []

            return f" {logic_op} ".join(sub_clauses), all_params

        return "1=1", []

    def _map_field_to_sql(self, field: str) -> str:
        """Maps virtual field keys to SQL column expressions or JSON extractions."""
        # Simple Mappings
        mapping = {
            "uuid": "uuid",
            "status": "status",
            "page_count_virt": "page_count_virt",
            "created_at": "created_at",
            "last_processed_at": "last_processed_at",
            "last_used": "last_used",
            "cached_full_text": "cached_full_text",
            "original_filename": "export_filename",
            "deleted": "deleted",
            
            # Stage 1 Direct fields
            "type_tags": "type_tags", # JSON array
            "tags": "tags",           # JSON array (User)
            "sender": "sender",
            "doc_date": "doc_date",
            "amount": "amount",
            
            # Stage 1 Semantic fields (nested in semantic_data)
            "direction": "json_extract(semantic_data, '$.direction')",
            "tenant_context": "json_extract(semantic_data, '$.tenant_context')",
            "confidence": "json_extract(semantic_data, '$.confidence')",
            "reasoning": "json_extract(semantic_data, '$.reasoning')",
            "doc_type": "json_extract(semantic_data, '$.doc_types[0]')", # First one as primary for simple search
            "visual_audit_mode": "COALESCE(json_extract(semantic_data, '$.visual_audit.meta_mode'), 'NONE')",
            
            # Phase 105: Visual Audit / Stamps
            "stamp_text": "(SELECT group_concat(COALESCE(json_extract(s.value, '$.raw_content'), '')) "
                          "FROM json_each(COALESCE(json_extract(semantic_data, '$.visual_audit.layer_stamps'), "
                          "json_extract(semantic_data, '$.layer_stamps'))) AS s)",
            "stamp_type": "(SELECT group_concat(COALESCE(json_extract(s.value, '$.type'), '')) "
                          "FROM json_each(COALESCE(json_extract(semantic_data, '$.visual_audit.layer_stamps'), "
                          "json_extract(semantic_data, '$.layer_stamps'))) AS s)"
        }
        
        if field in mapping:
            return mapping[field]
            
        # JSON Path Fallback
        if field.startswith("json:"):
            path = field[5:]
            return f"json_extract(semantic_data, '$.{path}')"
        if field.startswith("semantic:"):
            path = field[9:]
            return f"json_extract(semantic_data, '$.{path}')"
            
        # Dynamic Stamp Fields (Phase 105)
        if field.startswith("stamp_field:"):
             label = field[12:]
             # Return subquery that aggregates values for THIS label from all stamps
             return f"(SELECT group_concat(COALESCE(json_extract(f.value, '$.normalized_value'), json_extract(f.value, '$.raw_value'))) " \
                    f" FROM json_each(COALESCE(json_extract(semantic_data, '$.visual_audit.layer_stamps'), " \
                    f" json_extract(semantic_data, '$.layer_stamps'))) AS s, " \
                    f" json_each(json_extract(s.value, '$.form_fields')) AS f " \
                    f" WHERE json_extract(f.value, '$.label') = '{label}')"
            
        return field # fallback

    def _map_op_to_sql(self, expr: str, op: str, val: Any) -> Tuple[str, List[Any]]:
        """
        Translates an abstract operator and value into a SQL clause and parameters.

        Args:
            expr: The SQL expression for the field.
            op: The operator (e.g., 'equals', 'contains').
            val: The comparison value.

        Returns:
            A tuple containing the SQL fragment and parameters.
        """
        if op == "equals":
            if isinstance(val, list):
                if not val:
                    return "1=1", []
                placeholders = ", ".join(["?" for _ in val])
                return f"{expr} COLLATE NOCASE IN ({placeholders})", val
            return f"{expr} = ? COLLATE NOCASE", [val]

        if op == "contains":
            if expr in ["type_tags", "tags"]:
                # Precise JSON array element match
                if isinstance(val, list):
                    if not val:
                        return "1=1", []
                    clauses = [f"EXISTS (SELECT 1 FROM json_each({expr}) WHERE value = ? COLLATE NOCASE)" for _ in val]
                    return "(" + " OR ".join(clauses) + ")", val
                return f"EXISTS (SELECT 1 FROM json_each({expr}) WHERE value = ? COLLATE NOCASE)", [val]

            if isinstance(val, list):
                if not val:
                    return "1=1", []
                clauses = [f"{expr} LIKE ?" for _ in val]
                params = [f"%{v}%" for v in val]
                return "(" + " OR ".join(clauses) + ")", params
            return f"{expr} LIKE ?", [f"%{val}%"]

        if op == "starts_with":
            return f"{expr} LIKE ?", [f"{val}%"]

        if op == "gt":
            return f"{expr} > ?", [val]

        if op == "gte":
            return f"{expr} >= ?", [val]

        if op == "lt":
            return f"{expr} < ?", [val]

        if op == "lte":
            return f"{expr} <= ?", [val]

        if op == "is_empty":
            return f"{expr} IS NULL OR {expr} = ''", []

        if op == "is_not_empty":
            return f"{expr} IS NOT NULL AND {expr} != ''", []

        if op == "in":
            if not isinstance(val, list):
                val = [val]
            placeholders = ", ".join(["?" for _ in val])
            return f"{expr} COLLATE NOCASE IN ({placeholders})", val

        if op == "between":
            if isinstance(val, list) and len(val) == 2:
                return f"{expr} BETWEEN ? AND ?", [val[0], val[1]]

        return "1=1", []

    def get_all_entities_view(self) -> List[Document]:
        """
        Primary data view for Stage 0/1 Documents.
        Targeting: virtual_documents.
        """
        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags,
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags
            FROM virtual_documents
            WHERE deleted = 0
            ORDER BY created_at DESC
        """
        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        return [self._row_to_doc(row) for row in rows]

    def _row_to_doc(self, row: Tuple[Any, ...]) -> Document:
        """
        Helper to convert a database row to a Document object.

        Args:
            row: A tuple returned by a database query.

        Returns:
            A populated Document object.
        """
        # Index Map:
        # 0:uuid, 1:source_mapping, 2:status, 3:filename, 4:page_count, 5:created_at,
        # 6:locked, 7:type_tags, 8:cached_full_text, 9:last_used, 10:last_processed_at, 11:semantic_data
        # 12:sender, 13:doc_date, 14:amount, 15:tags

        def safe_json_load(data: Optional[str], default: Any = None) -> Any:
            if not data:
                return default
            try:
                return json.loads(data)
            except (json.JSONDecodeError, TypeError):
                return default

        type_tags = safe_json_load(row[7] if len(row) > 7 else None, [])
        semantic_data = safe_json_load(row[11] if len(row) > 11 else None, {})
        tags_raw = row[15] if len(row) > 15 else None

        tags = []
        if tags_raw:
            try:
                tags = json.loads(tags_raw)
                if isinstance(tags, str):  # Handle legacy CSV format
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
            except (json.JSONDecodeError, TypeError):
                if isinstance(tags_raw, str):
                    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

        doc_data = {
            "uuid": row[0],
            "extra_data": {"source_mapping": row[1]},
            "status": row[2],
            "original_filename": row[3],
            "page_count": row[4],
            "created_at": row[5],
            "locked": bool(row[6]),
            "deleted": False,
            "type_tags": type_tags,
            "cached_full_text": row[8] if len(row) > 8 else None,
            "text_content": row[8] if len(row) > 8 else None,
            "last_used": row[9] if len(row) > 9 else None,
            "last_processed_at": row[10] if len(row) > 10 else None,
            "semantic_data": semantic_data,
            "sender": row[12] if len(row) > 12 else None,
            "doc_date": row[13] if len(row) > 13 else None,
            "amount": row[14] if len(row) > 14 else None,
            "tags": tags,
        }

        if semantic_data and isinstance(semantic_data, dict):
            doc_data.update(semantic_data)

        # Ensure type consistency (doc_type is not in the row directly but often in semantic_data)
        return Document(**doc_data)


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

    def search_documents(self, search_text: str) -> List[Document]:
        """
        FTS5 Search across virtual_documents.
        """
        if not search_text:
            return self.get_all_entities_view()
            
        sql = """
            SELECT v.uuid, v.source_mapping, v.status, 
                   COALESCE(v.export_filename, 'Entity ' || substr(v.uuid, 1, 8)),
                   v.page_count_virt, v.created_at, v.is_immutable, v.type_tags,
                   v.cached_full_text, v.last_used, v.last_processed_at,
                   v.semantic_data, v.sender, v.doc_date, v.amount, v.tags
            FROM virtual_documents v
            JOIN virtual_documents_fts f ON v.uuid = f.uuid
            WHERE f.cached_full_text MATCH ? AND v.deleted = 0
            ORDER BY rank
        """
        cursor = self.connection.cursor()
        cursor.execute(sql, (search_text,))
        rows = cursor.fetchall()
        
        return [self._row_to_doc(row) for row in rows]


    def delete_document(self, uuid: str) -> bool:
        """
        Marks a document as deleted (Soft Delete).

        Args:
            uuid: The UUID of the document to delete.

        Returns:
            True if the operation was successful, False otherwise.
        """
        if not self.connection:
            return False

        sql = "UPDATE virtual_documents SET deleted = 1 WHERE uuid = ?"
        with self.connection:
            self.connection.execute(sql, (uuid,))
            return self.connection.total_changes > 0

    def purge_document(self, uuid: str) -> bool:
        """
        Permanently delete a document by its UUID (Hard Delete).
        """
        sql = "DELETE FROM virtual_documents WHERE uuid = ?"
        with self.connection:
            self.connection.execute(sql, (uuid,))
            return self.connection.total_changes > 0

    def purge_entities_for_source(self, source_uuid: str):
        """Hard delete all virtual documents linked to this physical source."""
        sql = "DELETE FROM virtual_documents WHERE source_mapping LIKE ?"
        with self.connection:
            self.connection.execute(sql, (f'%{source_uuid}%',))

    def restore_document(self, uuid: str) -> bool:
        """
        Restores a soft-deleted document (moves it from Trash back to Active).

        Args:
            uuid: The UUID of the document to restore.

        Returns:
            True if the document was restored, False otherwise.
        """
        if not self.connection:
            return False

        sql = "UPDATE virtual_documents SET deleted = 0 WHERE uuid = ?"
        with self.connection:
            self.connection.execute(sql, (uuid,))
            return self.connection.total_changes > 0

    # --- Stage 2 Maintenance Functions ---

    def get_documents_missing_semantic_data(self) -> List[Document]:
        """
        Fetch documents where status is 'PROCESSED' but semantic_data is missing or empty.
        Excluded deleted and immutable documents.
        """
        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags,
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags
            FROM virtual_documents
            WHERE deleted = 0 
              AND is_immutable = 0
              AND (semantic_data IS NULL OR semantic_data = '{}' OR json_extract(semantic_data, '$.bodies') IS NULL OR json_extract(semantic_data, '$.bodies') = '{}')
            ORDER BY created_at DESC
        """
        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [self._row_to_doc(row) for row in rows]

    def get_documents_mismatched_semantic_data(self) -> List[Document]:
        """
        Fetch documents where semantic_data contents do not align with current type_tags.
        Logic: If a tag like 'INVOICE' is present, we expect a 'finance_body' in semantic_data['bodies'].
        """
        # We'll fetch all processed docs and filter in Python for complex logic
        # Or we can try some JSON SQL
        
        # Heuristic: 
        # INVOICE -> bodies.finance_body
        # CONTRACT -> bodies.legal_body
        # BANK_STATEMENT -> bodies.ledger_body
        # PAYSLIP -> bodies.hr_body
        # MEDICAL_DOCUMENT -> bodies.health_body
        
        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags,
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags
            FROM virtual_documents
            WHERE status = 'PROCESSED' 
              AND semantic_data IS NOT NULL 
              AND deleted = 0
              AND is_immutable = 0
        """
        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        all_docs = [self._row_to_doc(row) for row in rows]
        mismatched = []
        
        for doc in all_docs:
            if not doc.type_tags or not doc.semantic_data:
                continue
                
            bodies = doc.semantic_data.get("bodies", {})
            if not bodies:
                continue # If no bodies at all, it's 'Missing', not 'Mismatched'
                
            tags = [t.upper() for t in doc.type_tags]
            
            # Simplified Mismatch Logic
            is_mismatch = False
            
            mapping = {
                "INVOICE": "finance_body",
                "RECEIPT": "finance_body",
                "ORDER_CONFIRMATION": "finance_body",
                "DUNNING": "finance_body",
                "BANK_STATEMENT": "ledger_body",
                "CONTRACT": "legal_body",
                "OFFICIAL_LETTER": "legal_body",
                "PAYSLIP": "hr_body",
                "MEDICAL_DOCUMENT": "health_body",
                "UTILITY_BILL": "finance_body",
                "EXPENSE_REPORT": "travel_body"
            }
            
            # Check if any tag requires a body that is missing
            for tag, body_key in mapping.items():
                if tag in tags and body_key not in bodies:
                    is_mismatch = True
                    break
            
            # OR Check if semantic data has bodies for tags that are NOT present
            # (e.g. tag changed from INVOICE to CONTRACT, but finance_body remains)
            if not is_mismatch:
                for body_key in bodies.keys():
                    # Find tags that would justify this body
                    found_reason = False
                    for tag, mapped_body in mapping.items():
                        if mapped_body == body_key and tag in tags:
                            found_reason = True
                            break
                    if not found_reason and body_key in ["finance_body", "ledger_body", "legal_body", "hr_body", "health_body", "travel_body"]:
                        is_mismatch = True
                        break
            
            if is_mismatch:
                mismatched.append(doc)
                
        return mismatched

    def close(self) -> None:
        """
        Closes the database connection safely.
        """
        if self.connection:
            self.connection.close()
            self.connection = None

    # --- Phase 93: Stage 0/1 Entity & Tag Management ---

    def get_virtual_documents_by_source(self, source_uuid: str) -> List[Document]:
        """
        Fetch all virtual documents that include the given physical file UUID.
        """
        # We search inside the source_mapping JSON array.
        # This is slightly slow but correct for Stage 0/1.
        sql = "SELECT uuid FROM virtual_documents WHERE source_mapping LIKE ?"
        cursor = self.connection.cursor()
        cursor.execute(sql, (f'%{source_uuid}%',))
        uuids = [row[0] for row in cursor.fetchall()]
        
        results = []
        for v_uuid in uuids:
            doc = self.get_document_by_uuid(v_uuid)
            if doc: results.append(doc)
        return results

    def get_all_tags_with_counts(self) -> dict[str, int]:
        """
        Aggregate all tags from virtual_documents and return a count for each.
        Aggregates from both 'type_tags' (System) and 'tags' (User) columns.
        """
        sql = "SELECT type_tags, tags FROM virtual_documents"
        cursor = self.connection.cursor()
        tag_counts = {}
        
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            for (type_tags_json, tags_json) in rows:
                for json_val in [type_tags_json, tags_json]:
                    if not json_val: continue
                    try:
                        tags_list = json.loads(json_val)
                        if isinstance(tags_list, list):
                            for t in tags_list:
                                if t and isinstance(t, str):
                                    tag_counts[t] = tag_counts.get(t, 0) + 1
                    except: pass
        except Exception as e:
            print(f"[WARN] get_all_tags_with_counts failed: {e}")
            
        return tag_counts

    def get_virtual_uuids_with_text_content(self, text: str) -> List[str]:
        """
        Deep search for UUIDs of virtual documents that contain the given text.
        Searches:
        1. virtual_documents.cached_full_text
        2. physical_files.raw_ocr_data (and maps back to virtual_doc)
        """
        text = text.strip()
        if not text: return []
        
        found_uuids = set()
        
        # 1. Search Virtual Documents Cache
        sql_v = "SELECT uuid FROM virtual_documents WHERE cached_full_text LIKE ? AND deleted = 0"
        cursor = self.connection.cursor()
        with self.connection:
            cursor.execute(sql_v, (f"%{text}%",))
            for row in cursor.fetchall():
                found_uuids.add(row[0])
                
        # 2. Search Physical Files (Raw Data)
        # This is the "Deep Search" requested by user
        sql_p = "SELECT uuid FROM physical_files WHERE raw_ocr_data LIKE ?"
        phys_uuids = []
        with self.connection:
            cursor.execute(sql_p, (f"%{text}%",))
            phys_uuids = [r[0] for r in cursor.fetchall()]
            
        if phys_uuids:
            # Find Virtual Docs referencing these physical files
            # This logic assumes source_mapping contains the physical UUID string
            # We construct a massive OR query or iterate
            for p_uuid in phys_uuids:
                sql_map = "SELECT uuid FROM virtual_documents WHERE source_mapping LIKE ? AND deleted = 0"
                cursor.execute(sql_map, (f"%{p_uuid}%",))
                for row in cursor.fetchall():
                    found_uuids.add(row[0])
                    
        return list(found_uuids)

    def find_text_pages_in_document(self, doc_uuid: str, text: str) -> List[int]:
        """
        Identify logical page numbers (0-based) in a virtual document where text appears.
        Uses Raw OCR Data from physical files.
        """
        text = text.strip()
        if not text: return []
        
        matching_pages = []
        
        # 1. Get Source Mapping
        sql = "SELECT source_mapping FROM virtual_documents WHERE uuid = ?"
        cursor = self.connection.cursor()
        cursor.execute(sql, (doc_uuid,))
        row = cursor.fetchone()
        if not row or not row[0]:
            return []
            
        try:
            mapping = json.loads(row[0]) # List[{file_uuid, pages: [int], ...}]
        except:
            return []
            
        current_virt_page = 0
        
        # 2. Iterate segments
        for segment in mapping:
            p_uuid = segment.get("file_uuid")
            src_pages = segment.get("pages", []) # List of 0-based page indices in physical file
            
            if not p_uuid or not src_pages:
                continue
                
            # Get Raw Data for this file
            sql_ocr = "SELECT raw_ocr_data FROM physical_files WHERE uuid = ?"
            cursor.execute(sql_ocr, (p_uuid,))
            ocr_row = cursor.fetchone()
            
            if ocr_row and ocr_row[0]:
                try:
                    ocr_map = json.loads(ocr_row[0]) # Dict: "1": "Text", "2": "Text" (usually 1-based keys in Tesseract/OCR)
                except:
                    ocr_map = {}
                    
                # Check each page in this segment
                for i, src_page_idx in enumerate(src_pages):
                    virt_page_idx = current_virt_page + i
                    
                    # src_page_idx is 1-based (from source_mapping convention)
                    # OCR keys are strings of "1", "2"...
                    
                    # Correct lookup:
                    page_text = ocr_map.get(str(src_page_idx))
                    
                    snippet = (page_text[:30] + "...") if page_text else "None"
                    
                    if page_text and text.lower() in page_text.lower():
                        matching_pages.append(virt_page_idx)
                        
            current_virt_page += len(src_pages)
            
        return matching_pages

    def get_available_tags(self, system: bool = False) -> List[str]:
        """
        Return a list of unique tags.
        :param system: If True, return from 'type_tags' column, else from 'tags' (User).
        """
        col = "type_tags" if system else "tags"
        sql = f"SELECT {col} FROM virtual_documents WHERE {col} IS NOT NULL"
        cursor = self.connection.cursor()
        tags = set()
        try:
            cursor.execute(sql)
            for (json_val,) in cursor.fetchall():
                try:
                    data = json.loads(json_val)
                    if isinstance(data, list):
                        for t in data:
                            tags.add(str(t))
                except: pass
        except Exception as e:
            print(f"[WARN] get_available_tags failed: {e}")
        return sorted(list(tags))

    def rename_tag(self, old_name: str, new_name: str) -> int:
        """Rename a tag (Placeholder)."""
        return 0

    def delete_tag(self, tag_name: str) -> int:
        """Delete a tag (Placeholder)."""
        return 0



    def count_documents(self, filters: dict = None) -> int:
        """
        Count documents in virtual_documents.
        Simplified for Stage 0/1.
        """
        sql = "SELECT COUNT(*) FROM virtual_documents WHERE deleted = 0"
        cursor = self.connection.cursor()
        cursor.execute(sql)
        return cursor.fetchone()[0]


    def count_entities(self, status: str = None) -> int:
        """
        Count entries in virtual_documents (Active only).
        :param status: Optional status filter (e.g. 'NEW', 'PROCESSED')
        :return: Count
        """
        sql = "SELECT COUNT(*) FROM virtual_documents WHERE deleted = 0"
        params = []
        if status:
             sql += " AND status = ?"
             params.append(status)
             
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        return cursor.fetchone()[0]
        
    def get_deleted_entities_view(self) -> List[Document]:
        """
        Fetches all soft-deleted virtual documents for the Trash Bin view.

        Returns:
            A list of Document objects marked as deleted.
        """
        if not self.connection:
            return []

        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags,
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags
            FROM virtual_documents
            WHERE deleted = 1
            ORDER BY created_at DESC
        """
        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        return [self._row_to_doc(row) for row in rows]

    def delete_entity(self, uuid: str) -> bool:
        """
        Soft-deletes a virtual document (entity). Alias for delete_document.

        Args:
            uuid: The UUID of the document to delete.

        Returns:
            True if successful, False otherwise.
        """
        return self.delete_document(uuid)

    def restore_entity(self, uuid: str) -> bool:
        """
        Restores a soft-deleted virtual document. Alias for restore_document.

        Args:
            uuid: The UUID of the document to restore.

        Returns:
            True if successful, False otherwise.
        """
        return self.restore_document(uuid)

    def purge_entity(self, uuid: str) -> bool:
        """
        Permanently deletes a virtual document. Alias for purge_document.

        Args:
            uuid: The UUID of the document to purge.

        Returns:
            True if successful, False otherwise.
        """
        return self.purge_document(uuid)
            
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
            cursor.execute("DROP TABLE IF EXISTS virtual_documents")
            cursor.execute("DROP TABLE IF EXISTS physical_files")
            cursor.execute("DROP TABLE IF EXISTS virtual_documents_fts")
            
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
            raise # Re-raise to let the user know

    def get_source_mapping_from_entity(self, entity_uuid: str) -> Optional[list]:
        """
        Get the 'source_mapping' JSON (list of SourceReferences) for an entity.
        Used by GUI to find the physical file for a Logical Entity (Shadow Document).
        """
        cursor = self.connection.cursor()
        cursor.execute("SELECT source_mapping FROM virtual_documents WHERE uuid = ?", (entity_uuid,))
        row = cursor.fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return None

    def get_unique_stamp_labels(self) -> List[str]:
        """Fetch all unique labels used in stamp form fields across the database."""
        sql = """
            SELECT DISTINCT json_extract(f.value, '$.label')
            FROM virtual_documents,
                 json_each(COALESCE(json_extract(semantic_data, '$.visual_audit.layer_stamps'), 
                                    json_extract(semantic_data, '$.layer_stamps'))) AS s,
                 json_each(json_extract(s.value, '$.form_fields')) AS f
            WHERE f.value IS NOT NULL AND json_extract(f.value, '$.label') IS NOT NULL;
        """
        try:
            with self.connection:
                cursor = self.connection.cursor()
                cursor.execute(sql)
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DB] Error fetching unique stamp labels: {e}")
            return []
            
    def get_source_uuid_from_entity(self, entity_uuid: str) -> Optional[str]:
        """
        Resolves an entity UUID to its primary source physical UUID.

        Args:
            entity_uuid: The UUID of the virtual document.

        Returns:
            The primary source file UUID or None.
        """
        mapping = self.get_source_mapping_from_entity(entity_uuid)
        if mapping and len(mapping) > 0:
            return str(mapping[0].get("file_uuid"))
        return None

    def _create_fts_triggers(self) -> None:
        """
        Creates SQLite triggers to keep the FTS index synchronized with
        the virtual_documents table.
        """
        triggers = [
            # INSERT
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_ai AFTER INSERT ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(rowid, uuid, export_filename, type_tags, cached_full_text)
                VALUES (new.rowid, new.uuid, new.export_filename, new.type_tags, new.cached_full_text);
            END;
            """,
            # DELETE
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_ad AFTER DELETE ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(virtual_documents_fts, rowid, uuid, export_filename, type_tags, cached_full_text)
                VALUES('delete', old.rowid, old.uuid, old.export_filename, old.type_tags, old.cached_full_text);
            END;
            """,
            # UPDATE
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_au AFTER UPDATE ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(virtual_documents_fts, rowid, uuid, export_filename, type_tags, cached_full_text)
                VALUES('delete', old.rowid, old.uuid, old.export_filename, old.type_tags, old.cached_full_text);
                INSERT INTO virtual_documents_fts(rowid, uuid, export_filename, type_tags, cached_full_text)
                VALUES (new.rowid, new.uuid, new.export_filename, new.type_tags, new.cached_full_text);
            END;
            """
        ]
        if not self.connection:
            return
        with self.connection:
            for trigger_sql in triggers:
                self.connection.execute(trigger_sql)

    def _update_table(self, table: str, pk_val: str, updates: dict, pk_col: str = "uuid"):
        """Helper to update multiple columns in a table."""
        if not updates: return
        cols = ", ".join([f"{k} = ?" for k in updates.keys()])
        sql = f"UPDATE {table} SET {cols} WHERE {pk_col} = ?"
        vals = list(updates.values()) + [pk_val]
        with self.connection:
            self.connection.execute(sql, vals)

    # --- Compatibility / Legacy Methods ---

    def get_all_documents(self) -> List[Document]:
        """Compatibility wrapper for get_all_entities_view."""
        return self.get_all_entities_view()

    def insert_document(self, doc: Document) -> None:
        """
        Compatibility wrapper for inserting a document into virtual_documents (primarily for tests).

        Args:
            doc: The Document object to insert.
        """
        if not self.connection:
            return

        source_mapping = "[]"
        if doc.extra_data and "source_mapping" in doc.extra_data:
            source_mapping = json.dumps(doc.extra_data["source_mapping"])

        status = doc.status or "NEW"
        filename = doc.original_filename or "Unknown"
        type_tags_json = json.dumps(doc.type_tags or [])
        user_tags_json = json.dumps(doc.tags or [])

        # Build semantic data from extra fields
        semantic = {}
        fields_to_check = ["sender", "amount", "doc_date", "invoice_number", "tax_rate", "doc_type"]
        for field in fields_to_check:
            if hasattr(doc, field) and getattr(doc, field):
                semantic[field] = getattr(doc, field)

        if doc.semantic_data:
            semantic.update(doc.semantic_data)

        semantic_json = json.dumps(semantic, default=str)

        sql = """
            INSERT INTO virtual_documents (
                uuid, source_mapping, status, export_filename, created_at, 
                deleted, type_tags, semantic_data, page_count_virt, is_immutable, 
                cached_full_text, sender, doc_date, amount, tags
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, 1, 0, ?, ?, ?, ?, ?)
        """

        created = doc.created_at
        if not created:
            created = datetime.now().isoformat()

        try:
            with self.connection:
                self.connection.execute(sql, (
                    doc.uuid, source_mapping, status, filename,
                    created, type_tags_json, semantic_json, (doc.text_content or doc.cached_full_text),
                    doc.sender, str(doc.doc_date) if doc.doc_date else None,
                    float(doc.amount) if doc.amount else 0.0,
                    user_tags_json
                ))
        except sqlite3.Error as e:
            print(f"[WARN] insert_document compatibility failed: {e}")
