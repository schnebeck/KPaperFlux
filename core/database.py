"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/database.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Central database manager for SQLite persistence. Handles 
                schema initialization, migrations, and complex domain-specific 
                queries for physical files and virtual documents. Implements 
                FTS5 search and advanced nested filtering logic.
------------------------------------------------------------------------------
"""

import json
import sqlite3
import traceback
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from core.document import Document


class DatabaseManager:
    """
    Manages SQLite database connections, schema migrations, and high-level
    API for document persistence and retrieval.
    """

    def __init__(self, db_path: str = "kpaperflux.db") -> None:
        """
        Initializes the DatabaseManager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path: str = db_path
        self.connection: Optional[sqlite3.Connection] = None
        self._connect()

    def _connect(self) -> None:
        """
        Establishes a connection to the database and configures performance PRAGMAs.
        Enables WAL mode and foreign key constraints.
        """
        # check_same_thread=False allows using the connection across worker threads
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")

    def init_db(self) -> None:
        """
        Initializes the database schema and handles migrations for all components.
        Creates tables for physical files, virtual documents, and FTS5 search index.
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
            deleted_at DATETIME,
            locked_at DATETIME,
            exported_at DATETIME,
            page_count_virt INTEGER DEFAULT 0,
            type_tags TEXT, -- JSON List of strings
            sender TEXT,
            doc_date TEXT,
            amount REAL,
            tags TEXT
        );
        """

        # Using FTS5 for efficient full-text search across content and metadata
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
            self._create_fts_triggers()

    def matches_condition(self, entity_uuid: str, query_dict: Dict[str, Any]) -> bool:
        """
        Checks if a specific document matches a set of filter conditions.
        Used by the RulesEngine for automated tagging.

        Args:
            entity_uuid: The UUID of the virtual document to evaluate.
            query_dict: A dictionary defining the search/filter criteria.

        Returns:
            True if the document fulfills the conditions.
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
            return False

    def update_document_metadata(self, uuid: str, updates: Dict[str, Any]) -> bool:
        """
        Updates specific fields of a virtual document in the database.
        Handles serialization of complex types (lists, dicts).

        Args:
            uuid: The UUID of the document to update.
            updates: A dictionary of fields and their new values.

        Returns:
            True if at least one field was updated successfully.
        """
        if not self.connection or not updates:
            return False

        # Whitelist of fields allowed for direct update
        allowed = [
            "status", "export_filename", "deleted", "is_immutable", "locked",
            "type_tags", "cached_full_text", "last_used", "last_processed_at",
            "semantic_data", "sender", "amount", "doc_date", "tags",
            "deleted_at", "locked_at", "exported_at"
        ]
        filtered = {k: v for k, v in updates.items() if k in allowed}

        if "locked" in filtered:
            locked_val = bool(filtered.pop("locked"))
            filtered["is_immutable"] = int(locked_val)
            if locked_val:
                filtered["locked_at"] = datetime.now().isoformat()
            else:
                filtered["locked_at"] = None

        if "deleted" in filtered:
            deleted_val = bool(filtered["deleted"])
            if deleted_val:
                 filtered["deleted_at"] = datetime.now().isoformat()
            else:
                 filtered["deleted_at"] = None

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

    def touch_last_used(self, uuid: str) -> None:
        """
        Updates the legacy 'last_used' timestamp to current local time.

        Args:
            uuid: The document UUID to update.
        """
        now = datetime.now().isoformat()
        self.update_document_metadata(uuid, {"last_used": now})

    def update_document_status(self, uuid: str, new_status: str) -> None:
        """
        Direct helper to update a document's status.

        Args:
            uuid: The document identifier.
            new_status: The new status string (e.g., 'PROCESSED').
        """
        sql = "UPDATE virtual_documents SET status = ? WHERE uuid = ?"
        with self.connection:
            self.connection.execute(sql, (new_status, uuid))

    def get_document_by_uuid(self, uuid: str) -> Optional[Document]:
        """
        Retrieves a single virtual document by its unique UUID.

        Args:
            uuid: The document UUID.

        Returns:
            A populated Document object if found, else None.
        """
        if not self.connection:
            return None

        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags, 
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags,
                   deleted_at, locked_at, exported_at
            FROM virtual_documents
            WHERE uuid = ?
        """
        cursor = self.connection.cursor()
        cursor.execute(sql, (uuid,))
        row = cursor.fetchone()
        if row:
            return self._row_to_doc(row)
        return None

    def reset_document_for_reanalysis(self, uuid: str) -> None:
        """
        Resets a document's status and AI-derived metadata for fresh processing.

        Args:
            uuid: The UUID of the document to reset.
        """
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

    def queue_for_semantic_extraction(self, uuids: List[str]) -> None:
        """
        Queues documents for Stage 2 processing (Semantic Extraction).

        Args:
            uuids: List of document identifiers to queue.
        """
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
        Retrieves all documents currently marked as deleted (Trash Bin).

        Returns:
            A list of soft-deleted Document objects.
        """
        return self.get_deleted_entities_view()

    def get_available_extra_keys(self) -> List[str]:
        """
        Scans all documents to identify unique keys present in JSON metadata.

        Returns:
            A sorted list of flattened keys (e.g., 'semantic:total_amount').
        """
        keys: Set[str] = set()
        if not self.connection:
            return []

        cursor = self.connection.cursor()
        
        # 1. Extract from AI Results (Semantic Data)
        try:
            cursor.execute("SELECT semantic_data FROM virtual_documents WHERE semantic_data IS NOT NULL")
            for row in cursor.fetchall():
                if row[0]:
                    try:
                        data = json.loads(row[0])
                        if isinstance(data, dict):
                             self._extract_keys_recursive(data, keys, prefix="semantic:")
                    except (json.JSONDecodeError, TypeError):
                        pass
        except sqlite3.Error:
            pass

        # 2. Extract from Stamp Labels
        for label in self.get_unique_stamp_labels():
            keys.add(f"stamp_field:{label}")
                        
        return sorted(list(keys))

    def _extract_keys_recursive(self, obj: Any, keys_set: Set[str], prefix: str = "") -> None:
        """
        Recursively flattens JSON keys into a dot-notated set.

        Args:
            obj: The object to traverse.
            keys_set: The set to populate with keys.
            prefix: The current prefix for nested keys.
        """
        if isinstance(obj, dict):
            for k, v in obj.items():
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

    def search_documents_advanced(self, query: Dict[str, Any]) -> List[Document]:
        """
        Performs an advanced search using a nested query structure.

        Args:
            query: Structured query dictionary with conditions and operators.

        Returns:
            A list of matching Document objects.
        """
        if not query or (not query.get("conditions") and not query.get("field")):
             return self.get_all_entities_view()

        where_clause, params = self._build_where_clause(query)
        
        # Exclude deleted documents unless explicitly searched
        if "deleted" not in where_clause.lower():
            where_clause = f"({where_clause}) AND deleted = 0"
            
        sql = f"""
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags,
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags,
                   deleted_at, locked_at, exported_at
            FROM virtual_documents
            WHERE {where_clause}
            ORDER BY created_at DESC
        """
        
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        return [self._row_to_doc(row) for row in rows]

    def count_documents_advanced(self, query: Dict[str, Any]) -> int:
        """
        Returns the number of documents matching an advanced query.

        Args:
            query: Structured query dictionary.

        Returns:
            The count of matching records.
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
        Recursively translates a query node into SQL WHERE fragments.

        Args:
            node: The query node (condition or group).

        Returns:
            A tuple of (SQL string, parameters list).
        """
        if "field" in node:
            field = node["field"]
            op = node["op"]
            val = node.get("value")
            negate = node.get("negate", False)

            expr = self._map_field_to_sql(field)
            clause, params = self._map_op_to_sql(expr, op, val)

            if negate:
                return f"NOT ({clause})", params
            return clause, params

        if "conditions" in node:
            logic_op = str(node.get("operator", "AND")).upper()
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
        """
        Maps logical field names to database-level SQL expressions.
        Supports direct columns and nested JSON paths.

        Args:
            field: The logical field name.

        Returns:
            A SQL expression string.
        """
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
            "type_tags": "type_tags",
            "tags": "tags",
            "sender": "sender",
            "doc_date": "doc_date",
            "amount": "amount",
            
            # Semantic shortcuts
            "direction": "json_extract(semantic_data, '$.direction')",
            "tenant_context": "json_extract(semantic_data, '$.tenant_context')",
            "confidence": "json_extract(semantic_data, '$.confidence')",
            "reasoning": "json_extract(semantic_data, '$.reasoning')",
            "doc_type": "json_extract(semantic_data, '$.doc_types[0]')",
            "visual_audit_mode": "COALESCE(json_extract(semantic_data, '$.visual_audit.meta_mode'), 'NONE')",
            
            # Forensic/Stamp aggregations
            "stamp_text": "(SELECT group_concat(COALESCE(json_extract(s.value, '$.raw_content'), '')) "
                          "FROM json_each(COALESCE(json_extract(semantic_data, '$.visual_audit.layer_stamps'), "
                          "json_extract(semantic_data, '$.layer_stamps'))) AS s)",
            "stamp_type": "(SELECT group_concat(COALESCE(json_extract(s.value, '$.type'), '')) "
                          "FROM json_each(COALESCE(json_extract(semantic_data, '$.visual_audit.layer_stamps'), "
                          "json_extract(semantic_data, '$.layer_stamps'))) AS s)"
        }
        
        if field in mapping:
            return mapping[field]
            
        # Dynamic JSON mapping
        if field.startswith("json:") or field.startswith("semantic:"):
            path = field.split(":", 1)[1]
            return f"json_extract(semantic_data, '$.{path}')"
            
        # Dynamic Stamp Form Fields
        if field.startswith("stamp_field:"):
             label = field[12:]
             return f"(SELECT group_concat(COALESCE(json_extract(f.value, '$.normalized_value'), " \
                    f"json_extract(f.value, '$.raw_value'))) " \
                    f" FROM json_each(COALESCE(json_extract(semantic_data, '$.visual_audit.layer_stamps'), " \
                    f" json_extract(semantic_data, '$.layer_stamps'))) AS s, " \
                    f" json_each(json_extract(s.value, '$.form_fields')) AS f " \
                    f" WHERE json_extract(f.value, '$.label') = '{label}')"
            
        return field

    def _map_op_to_sql(self, expr: str, op: str, val: Any) -> Tuple[str, List[Any]]:
        """
        Translates a logical operator and value into a SQL condition.

        Args:
            expr: The SQL field expression.
            op: The operator key.
            val: The value to compare against.

        Returns:
            A tuple of (SQL condition string, parameters list).
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
                # JSON array intersection logic
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

        if op in ["gt", "gte", "lt", "lte"]:
            sql_ops = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
            return f"{expr} {sql_ops[op]} ?", [val]

        if op == "is_empty":
            return f"{expr} IS NULL OR {expr} = ''", []

        if op == "is_not_empty":
            return f"{expr} IS NOT NULL AND {expr} != ''", []

        if op == "between":
            if isinstance(val, list) and len(val) == 2:
                return f"{expr} BETWEEN ? AND ?", [val[0], val[1]]

        return "1=1", []

    def get_all_entities_view(self) -> List[Document]:
        """
        Retrieves all active (non-deleted) logical documents.

        Returns:
            A list of Document objects ordered by creation date.
        """
        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags,
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags,
                   deleted_at, locked_at, exported_at
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
        Converts a database result tuple into a fully hydrated Document object.

        Args:
            row: The raw database row tuple.

        Returns:
            A validated Document instance.
        """
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

        tags: List[str] = []
        if tags_raw:
            try:
                tags = json.loads(tags_raw)
                if isinstance(tags, str):
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
            "deleted_at": row[16] if len(row) > 16 else None,
            "locked_at": row[17] if len(row) > 17 else None,
            "exported_at": row[18] if len(row) > 18 else None,
        }

        # Merge semantic fields into the main document body for Pydantic mapping
        if semantic_data and isinstance(semantic_data, dict):
            doc_data.update(semantic_data)

        return Document(**doc_data)

    def search_documents(self, search_text: str) -> List[Document]:
        """
        Performs a full-text search across all documents using FTS5.

        Args:
            search_text: The query string.

        Returns:
            A ranked list of matching Document objects.
        """
        if not search_text:
            return self.get_all_entities_view()
            
        sql = """
            SELECT v.uuid, v.source_mapping, v.status, 
                   COALESCE(v.export_filename, 'Entity ' || substr(v.uuid, 1, 8)),
                   v.page_count_virt, v.created_at, v.is_immutable, v.type_tags,
                   v.cached_full_text, v.last_used, v.last_processed_at,
                   v.semantic_data, v.sender, v.doc_date, v.amount, v.tags,
                   v.deleted_at, v.locked_at, v.exported_at
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
        Performs a soft-delete on a document and records the timestamp.
        """
        now = datetime.now().isoformat()
        sql = "UPDATE virtual_documents SET deleted = 1, deleted_at = ? WHERE uuid = ?"
        with self.connection:
            self.connection.execute(sql, (now, uuid))
            return self.connection.total_changes > 0

    def mark_documents_deleted(self, uuids: List[str]) -> None:
        """Soft-deletes multiple documents and records the deletion timestamp."""
        now = datetime.now().isoformat()
        sql = "UPDATE virtual_documents SET deleted = 1, deleted_at = ? WHERE uuid = ?"
        with self.connection:
            for uid in uuids:
                self.connection.execute(sql, (now, uid))

    def purge_document(self, uuid: str) -> bool:
        """
        Permanently deletes a document record and its FTS entry.

        Args:
            uuid: The document UUID.

        Returns:
            True if successful.
        """
        sql = "DELETE FROM virtual_documents WHERE uuid = ?"
        with self.connection:
            self.connection.execute(sql, (uuid,))
            return self.connection.total_changes > 0

    def purge_entities_for_source(self, source_uuid: str) -> None:
        """
        Hard deletes all logical entities referencing a specific physical source.

        Args:
            source_uuid: The UUID of the physical source.
        """
        sql = "DELETE FROM virtual_documents WHERE source_mapping LIKE ?"
        with self.connection:
            self.connection.execute(sql, (f'%{source_uuid}%',))

    def restore_document(self, uuid: str) -> bool:
        """
        Restores a document from the trash bin and clears the deletion timestamp.
        """
        sql = "UPDATE virtual_documents SET deleted = 0, deleted_at = NULL WHERE uuid = ?"
        with self.connection:
            self.connection.execute(sql, (uuid,))
            return self.connection.total_changes > 0

    def get_documents_missing_semantic_data(self) -> List[Document]:
        """
        Identifies documents that lack structural semantic metadata.
        Used for maintenance and catch-up processing.

        Returns:
            List of incomplete Document objects.
        """
        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags,
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags,
                   deleted_at, locked_at, exported_at
            FROM virtual_documents
            WHERE deleted = 0 
              AND is_immutable = 0
              AND (semantic_data IS NULL OR semantic_data = '{}' OR 
                   json_extract(semantic_data, '$.bodies') IS NULL)
            ORDER BY created_at DESC
        """
        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [self._row_to_doc(row) for row in rows]

    def get_documents_mismatched_semantic_data(self) -> List[Document]:
        """
        Forensic check for Documents whose semantic bodies don't match their type tags.
        Example: Document tagged as INVOICE but missing a 'finance_body'.

        Returns:
            List of documents requiring re-analysis.
        """
        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags,
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags,
                   deleted_at, locked_at, exported_at
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
        mismatched: List[Document] = []
        
        # Mappings of Tag -> Expected Semantic Body
        body_mapping = {
            "INVOICE": "finance_body", "RECEIPT": "finance_body",
            "ORDER_CONFIRMATION": "finance_body", "DUNNING": "finance_body",
            "BANK_STATEMENT": "ledger_body", "CONTRACT": "legal_body",
            "OFFICIAL_LETTER": "legal_body", "PAYSLIP": "hr_body",
            "MEDICAL_DOCUMENT": "health_body", "UTILITY_BILL": "finance_body",
            "EXPENSE_REPORT": "travel_body"
        }
        
        for doc in all_docs:
            if not doc.type_tags or not doc.semantic_data:
                continue
                
            bodies = doc.semantic_data.get("bodies", {})
            if not bodies:
                continue
                
            tags = [t.upper() for t in doc.type_tags]
            is_mismatch = False
            
            for tag, body_key in body_mapping.items():
                if tag in tags and body_key not in bodies:
                    is_mismatch = True
                    break
            
            if not is_mismatch:
                for body_key in bodies.keys():
                    if body_key in ["finance_body", "ledger_body", "legal_body", "hr_body", "health_body"]:
                        # Check if any tag justifies this body
                        if not any(v == body_key and k in tags for k, v in body_mapping.items()):
                            is_mismatch = True
                            break
            
            if is_mismatch:
                mismatched.append(doc)
                
        return mismatched

    def close(self) -> None:
        """Safely closes the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def get_virtual_documents_by_source(self, source_uuid: str) -> List[Document]:
        """
        Finds all virtual documents that incorporate a specific physical file.

        Args:
            source_uuid: The physical file UUID.

        Returns:
            List of referencing documents.
        """
        sql = "SELECT uuid FROM virtual_documents WHERE source_mapping LIKE ?"
        cursor = self.connection.cursor()
        cursor.execute(sql, (f'%{source_uuid}%',))
        uuids = [row[0] for row in cursor.fetchall()]
        
        results = []
        for v_uuid in uuids:
            doc = self.get_document_by_uuid(v_uuid)
            if doc:
                results.append(doc)
        return results

    def get_all_tags_with_counts(self) -> Dict[str, int]:
        """
        Aggregates all unique tags and type labels from the database.

        Returns:
            A dictionary mapping tag names to their occurrence counts.
        """
        sql = "SELECT type_tags, tags FROM virtual_documents"
        cursor = self.connection.cursor()
        tag_counts: Dict[str, int] = {}
        
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            for (type_tags_json, tags_json) in rows:
                for json_val in [type_tags_json, tags_json]:
                    if not json_val:
                        continue
                    try:
                        tags_list = json.loads(json_val)
                        if isinstance(tags_list, list):
                            for t in tags_list:
                                if t and isinstance(t, str):
                                    tag_counts[t] = tag_counts.get(t, 0) + 1
                    except (json.JSONDecodeError, TypeError):
                        pass
        except Exception as e:
            print(f"[WARN] get_all_tags_with_counts failed: {e}")
            
        return tag_counts

    def get_virtual_uuids_with_text_content(self, text: str) -> List[str]:
        """
        Performs a deep search for documents containing a specific text snippet.
        Searches cached logical text and raw physical OCR data.

        Args:
            text: The text to search for.

        Returns:
            List of matching document identifiers.
        """
        text = text.strip()
        if not text:
            return []
        
        found_uuids: Set[str] = set()
        cursor = self.connection.cursor()
        
        # 1. Logical Search
        sql_v = "SELECT uuid FROM virtual_documents WHERE cached_full_text LIKE ? AND deleted = 0"
        cursor.execute(sql_v, (f"%{text}%",))
        for row in cursor.fetchall():
            found_uuids.add(row[0])
                
        # 2. Deep Physical Search
        sql_p = "SELECT uuid FROM physical_files WHERE raw_ocr_data LIKE ?"
        cursor.execute(sql_p, (f"%{text}%",))
        phys_uuids = [r[0] for r in cursor.fetchall()]
            
        if phys_uuids:
            for p_uuid in phys_uuids:
                sql_map = "SELECT uuid FROM virtual_documents WHERE source_mapping LIKE ? AND deleted = 0"
                cursor.execute(sql_map, (f"%{p_uuid}%",))
                for row in cursor.fetchall():
                    found_uuids.add(row[0])
                    
        return list(found_uuids)

    def find_text_pages_in_document(self, doc_uuid: str, text: str) -> List[int]:
        """
        Identifies logical page numbers within a document where text appears.

        Args:
            doc_uuid: The target virtual document ID.
            text: Search string.

        Returns:
            A list of 0-based logical page indices.
        """
        text = text.strip()
        if not text:
            return []
        
        matching_pages: List[int] = []
        sql = "SELECT source_mapping FROM virtual_documents WHERE uuid = ?"
        cursor = self.connection.cursor()
        cursor.execute(sql, (doc_uuid,))
        row = cursor.fetchone()
        
        if not row or not row[0]:
            return []
            
        try:
            mapping = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return []
            
        current_virt_page = 0
        for segment in mapping:
            p_uuid = segment.get("file_uuid")
            src_pages = segment.get("pages", [])
            
            if not p_uuid or not src_pages:
                continue
                
            cursor.execute("SELECT raw_ocr_data FROM physical_files WHERE uuid = ?", (p_uuid,))
            ocr_row = cursor.fetchone()
            
            if ocr_row and ocr_row[0]:
                try:
                    ocr_map = json.loads(ocr_row[0])
                except (json.JSONDecodeError, TypeError):
                    ocr_map = {}
                    
                for i, src_page_idx in enumerate(src_pages):
                    virt_page_idx = current_virt_page + i
                    # OCR map keys are strings of 1-based indices
                    page_text = ocr_map.get(str(src_page_idx))
                    if page_text and text.lower() in page_text.lower():
                        matching_pages.append(virt_page_idx)
                        
            current_virt_page += len(src_pages)
            
        return matching_pages

    def get_available_tags(self, system: bool = False) -> List[str]:
        """
        Returns a sorted list of unique tags from either system or user namespace.

        Args:
            system: If True, pulls from 'type_tags', else from 'tags'.

        Returns:
            List of unique tag names.
        """
        col = "type_tags" if system else "tags"
        sql = f"SELECT {col} FROM virtual_documents WHERE {col} IS NOT NULL"
        cursor = self.connection.cursor()
        tags: Set[str] = set()
        try:
            cursor.execute(sql)
            for (json_val,) in cursor.fetchall():
                try:
                    data = json.loads(json_val)
                    if isinstance(data, list):
                        for t in data:
                            tags.add(str(t))
                except (json.JSONDecodeError, TypeError):
                    pass
        except sqlite3.Error:
            pass
        return sorted(list(tags))

    def count_documents(self) -> int:
        """Returns total count of non-deleted documents."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM virtual_documents WHERE deleted = 0")
        return int(cursor.fetchone()[0])

    def count_entities(self, status: Optional[str] = None) -> int:
        """
        Returns count of non-deleted documents, optionally filtered by status.

        Args:
            status: Status string (e.g., 'NEW').

        Returns:
            Integer count.
        """
        sql = "SELECT COUNT(*) FROM virtual_documents WHERE deleted = 0"
        params = []
        if status:
             sql += " AND status = ?"
             params.append(status)
             
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        return int(cursor.fetchone()[0])
        
    def get_deleted_entities_view(self) -> List[Document]:
        """Provides Trash Bin view data."""
        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags,
                   cached_full_text, last_used, last_processed_at,
                   semantic_data,
                   sender, doc_date, amount, tags,
                   deleted_at, locked_at, exported_at
            FROM virtual_documents
            WHERE deleted = 1
            ORDER BY created_at DESC
        """
        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [self._row_to_doc(row) for row in rows]

    def purge_all_data(self, vault_path: str) -> bool:
        """
        DESTRUCTIVE: Resets database and clears vault directory.
        Used for full environment reset.

        Args:
            vault_path: Path to the immutable vault.

        Returns:
            True if purge completed successfully.
        """
        import os
        import shutil
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("DROP TABLE IF EXISTS virtual_documents")
            cursor.execute("DROP TABLE IF EXISTS physical_files")
            cursor.execute("DROP TABLE IF EXISTS virtual_documents_fts")
            self.connection.commit()
            
            self.init_db()
            
            if vault_path and os.path.exists(vault_path):
                for filename in os.listdir(vault_path):
                    file_path = os.path.join(vault_path, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        print(f"Purge error at {file_path}: {e}")
            return True
        except Exception:
            return False

    def get_source_mapping_from_entity(self, entity_uuid: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieves raw source mapping for a virtual entity."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT source_mapping FROM virtual_documents WHERE uuid = ?", (entity_uuid,))
        row = cursor.fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return None

    def get_unique_stamp_labels(self) -> List[str]:
        """Aggregates all unique labels from detected stamps in semantic data."""
        sql = """
            SELECT DISTINCT json_extract(f.value, '$.label')
            FROM virtual_documents,
                 json_each(COALESCE(json_extract(semantic_data, '$.visual_audit.layer_stamps'), 
                                    json_extract(semantic_data, '$.layer_stamps'))) AS s,
                 json_each(json_extract(s.value, '$.form_fields')) AS f
            WHERE f.value IS NOT NULL AND json_extract(f.value, '$.label') IS NOT NULL;
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql)
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []
            
    def get_source_uuid_from_entity(self, entity_uuid: str) -> Optional[str]:
        """Returns the first physical file ID associated with a virtual entity."""
        mapping = self.get_source_mapping_from_entity(entity_uuid)
        if mapping and len(mapping) > 0:
            return str(mapping[0].get("file_uuid"))
        return None

    def _create_fts_triggers(self) -> None:
        """Maintains FTS synchronicity via SQLite triggers."""
        triggers = [
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_ai AFTER INSERT ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(rowid, uuid, export_filename, type_tags, cached_full_text)
                VALUES (new.rowid, new.uuid, new.export_filename, new.type_tags, new.cached_full_text);
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_ad AFTER DELETE ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(virtual_documents_fts, rowid, uuid, export_filename, type_tags, cached_full_text)
                VALUES('delete', old.rowid, old.uuid, old.export_filename, old.type_tags, old.cached_full_text);
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_au AFTER UPDATE ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(virtual_documents_fts, rowid, uuid, export_filename, type_tags, cached_full_text)
                VALUES('delete', old.rowid, old.uuid, old.export_filename, old.type_tags, old.cached_full_text);
                INSERT INTO virtual_documents_fts(rowid, uuid, export_filename, type_tags, cached_full_text)
                VALUES (new.rowid, new.uuid, new.export_filename, new.type_tags, new.cached_full_text);
            END;
            """
        ]
        with self.connection:
            for trigger_sql in triggers:
                self.connection.execute(trigger_sql)

    def _update_table(self, table: str, pk_val: str, updates: Dict[str, Any], pk_col: str = "uuid") -> None:
        """Internal generic update helper."""
        if not updates:
            return
        cols = ", ".join([f"{k} = ?" for k in updates.keys()])
        sql = f"UPDATE {table} SET {cols} WHERE {pk_col} = ?"
        vals = list(updates.values()) + [pk_val]
        with self.connection:
            self.connection.execute(sql, vals)

    # --- Backwards Compatibility ---
    def get_all_documents(self) -> List[Document]:
        return self.get_all_entities_view()

    def insert_document(self, doc: Document) -> None:
        """Compatibility insert for unit tests."""
        created = doc.created_at or datetime.now().isoformat()
        type_tags_json = json.dumps(doc.type_tags or [])
        user_tags_json = json.dumps(doc.tags or [])
        sm_json = "[]"
        if doc.extra_data and "source_mapping" in doc.extra_data:
            sm_json = json.dumps(doc.extra_data["source_mapping"])

        sql = """
            INSERT INTO virtual_documents (
                uuid, source_mapping, status, export_filename, created_at, 
                deleted, type_tags, semantic_data, page_count_virt, is_immutable, 
                cached_full_text, sender, doc_date, amount, tags,
                deleted_at, locked_at, exported_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?, '{}', 1, 0, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self.connection:
                self.connection.execute(sql, (
                    doc.uuid, sm_json, doc.status or "NEW", doc.original_filename or "Unknown",
                    created, type_tags_json, (doc.text_content or doc.cached_full_text),
                    doc.sender, str(doc.doc_date) if doc.doc_date else None,
                    float(doc.amount) if doc.amount else 0.0,
                    user_tags_json,
                    doc.deleted_at, doc.locked_at, doc.exported_at
                ))
        except sqlite3.Error:
            pass
