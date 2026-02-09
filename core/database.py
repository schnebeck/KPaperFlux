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
import logging
import sqlite3
import traceback
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from core.models.virtual import VirtualDocument as Document
from core.models.semantic import SemanticExtraction

# --- Central Logging Setup ---
logger = logging.getLogger("KPaperFlux.Database")


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
        self.init_db()
        # Source of truth for document selection to avoid index mismatches
        self._doc_select = """
            uuid, source_mapping, status, export_filename, last_used, 
            last_processed_at, is_immutable, thumbnail_path, cached_full_text, 
            semantic_data, created_at, deleted, page_count_virt, type_tags,
            tags, deleted_at, locked_at, exported_at, pdf_class
        """

    def _connect(self) -> None:
        """
        Establishes a connection to the database and configures performance PRAGMAs.
        Enables WAL mode and foreign key constraints.
        """
        try:
            # check_same_thread=False allows using the connection across worker threads
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self.connection.row_factory = sqlite3.Row  # Enable named column access
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            logger.info(f"Connected to database at {self.db_path} (WAL mode enabled)")
        except sqlite3.Error as e:
            logger.critical(f"Failed to connect to database: {e}")
            raise

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
            tags TEXT,
            pdf_class TEXT DEFAULT 'C'
        );
        """

        # Using FTS5 for efficient full-text search across content and metadata
        create_virtual_documents_fts = """
        CREATE VIRTUAL TABLE IF NOT EXISTS virtual_documents_fts USING fts5(
            uuid UNINDEXED,
            export_filename,
            type_tags,
            cached_full_text
        );
        """

        if not self.connection:
            return

        with self.connection:
            self.connection.execute(create_physical_files_table)
            self.connection.execute(create_virtual_documents_table)
            self.connection.execute(create_virtual_documents_fts)
            self._migrate_schema()
            self._create_fts_triggers()
            self._create_usage_triggers()
            self._create_ref_count_triggers()

    def _create_ref_count_triggers(self) -> None:
        """
        Maintains 'ref_count' in physical_files based on usage in virtual_documents.
        This ensures physical files are only deleted when no logical entity refers to them.
        """
        triggers = [
            """
            CREATE TRIGGER IF NOT EXISTS vd_ref_count_insert AFTER INSERT ON virtual_documents
            BEGIN
                UPDATE physical_files 
                SET ref_count = ref_count + 1
                WHERE uuid IN (
                    SELECT json_extract(value, '$.file_uuid') 
                    FROM json_each(new.source_mapping)
                );
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS vd_ref_count_delete AFTER DELETE ON virtual_documents
            BEGIN
                UPDATE physical_files 
                SET ref_count = ref_count - 1
                WHERE uuid IN (
                    SELECT json_extract(value, '$.file_uuid') 
                    FROM json_each(old.source_mapping)
                );
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS vd_ref_count_update AFTER UPDATE ON virtual_documents
            WHEN (old.source_mapping IS NOT new.source_mapping)
            BEGIN
                -- Decrement old
                UPDATE physical_files 
                SET ref_count = ref_count - 1
                WHERE uuid IN (
                    SELECT json_extract(value, '$.file_uuid') 
                    FROM json_each(old.source_mapping)
                );
                -- Increment new
                UPDATE physical_files 
                SET ref_count = ref_count + 1
                WHERE uuid IN (
                    SELECT json_extract(value, '$.file_uuid') 
                    FROM json_each(new.source_mapping)
                );
            END;
            """
        ]
        with self.connection:
            for trigger_sql in triggers:
                self.connection.execute(trigger_sql)

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
            "status", "export_filename", "deleted", "is_immutable",
            "type_tags", "cached_full_text", "last_used", "last_processed_at",
            "semantic_data", "tags",
            "deleted_at", "locked_at", "exported_at", "pdf_class"
        ]
        filtered = {k: v for k, v in updates.items() if k in allowed}

        if "is_immutable" in filtered:
            val = bool(filtered["is_immutable"])
            filtered["is_immutable"] = int(val)
            if val:
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

        if "semantic_data" in filtered:
            sd = filtered["semantic_data"]
            if hasattr(sd, "model_dump"):
                # Use model_dump(mode='json') to handle Decimal, UUID, etc.
                filtered["semantic_data"] = json.dumps(sd.model_dump(mode='json'), ensure_ascii=False)
            elif isinstance(sd, (dict, list)):
                filtered["semantic_data"] = json.dumps(sd, ensure_ascii=False, default=str)

        if filtered:
            self._update_table("virtual_documents", uuid, filtered, pk_col="uuid")
            return True
        return False

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

        sql = f"""
            SELECT {self._doc_select}
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
            SELECT {self._doc_select}
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

    def sum_documents_advanced(self, query: Dict[str, Any], field: str = "amount") -> float:
        """
        Calculates the sum of a numeric field for documents matching a query.
        
        Args:
            query: Structured query dictionary.
            field: The logical field name to sum (e.g., 'amount').
            
        Returns:
            The total sum as a float.
        """
        if not self.connection:
            return 0.0

        where_clause, params = self._build_where_clause(query or {})
        if "deleted" not in where_clause.lower():
            where_clause = f"({where_clause}) AND deleted = 0"

        expr = self._map_field_to_sql(field)
        # Use CAST for safety with JSON values stored as strings
        sql = f"SELECT SUM(CAST({expr} AS REAL)) FROM virtual_documents WHERE {where_clause}"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
            result = cursor.fetchone()
            return result[0] if result and result[0] is not None else 0.0
        except sqlite3.Error as e:
            print(f"[DB] Error in sum_documents_advanced: {e}")
            return 0.0

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
            "sender": "json_extract(semantic_data, '$.meta_header.sender.name')",
            "doc_date": "json_extract(semantic_data, '$.meta_header.doc_date')",
            "amount": "CAST(json_extract(semantic_data, '$.bodies.finance_body.monetary_summation.grand_total_amount') AS REAL)",
            
            # Semantic shortcuts
            "direction": "json_extract(semantic_data, '$.direction')",
            "tenant_context": "json_extract(semantic_data, '$.tenant_context')",
            "classification": "json_extract(type_tags, '$[0]')",
            "visual_audit_mode": "COALESCE(json_extract(semantic_data, '$.visual_audit.meta_mode'), 'NONE')",
            
            # Forensic/Stamp aggregations
            "stamp_text": "(SELECT group_concat(COALESCE(json_extract(s.value, '$.raw_content'), '')) "
                          "FROM json_each(json_extract(semantic_data, '$.visual_audit.layer_stamps')) AS s)",
            "stamp_type": "(SELECT group_concat(COALESCE(json_extract(s.value, '$.type'), '')) "
                          "FROM json_each(json_extract(semantic_data, '$.visual_audit.layer_stamps')) AS s)"
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
        sql = f"""
            SELECT {self._doc_select}
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
                if isinstance(data, (bytes, str)):
                    return json.loads(data)
                return data
            except (json.JSONDecodeError, TypeError):
                return default

        type_tags = safe_json_load(row["type_tags"], [])
        semantic_raw = safe_json_load(row["semantic_data"], {})
        tags_raw = row["tags"]
        
        # 1. Hydrate Semantic Model
        semantic_data = None
        if semantic_raw:
            try:
                semantic_data = SemanticExtraction(**semantic_raw)
            except Exception as e:
                logger.warning(f"Metadata degradation for {row['uuid']}: {e}")
                # Fallback: still try to use the raw dict if valid (extra='ignore' in Document will handle it)
                semantic_data = None

        tags: List[str] = []
        if tags_raw:
            try:
                tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Error parsing tags for {row['uuid']}: {e}")

        doc_data = {
            "uuid": row["uuid"],
            "extra_data": {"source_mapping": row["source_mapping"]},
            "status": row["status"],
            "original_filename": row["export_filename"] or f"Entity {str(row['uuid'])[:8]}",
            "page_count": row["page_count_virt"],
            "created_at": row["created_at"],
            "last_used": row["last_used"],
            "last_processed_at": row["last_processed_at"],
            "is_immutable": bool(row["is_immutable"]),
            "deleted": bool(row["deleted"]),
            "type_tags": type_tags,
            "cached_full_text": row["cached_full_text"],
            "text_content": row["cached_full_text"],
            "semantic_data": semantic_data,
            "tags": tags,
            "deleted_at": row["deleted_at"] if "deleted_at" in row.keys() else None,
            "locked_at": row["locked_at"] if "locked_at" in row.keys() else None,
            "exported_at": row["exported_at"] if "exported_at" in row.keys() else None,
        }

        try:
            return Document(**doc_data)
        except Exception as e:
            logger.error(f"ValidationError for {doc_data.get('uuid')}: {e}")
            return None

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
            
        sql = f"""
            SELECT {', '.join(['v.' + c.strip() for c in self._doc_select.split(',')])}
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
        sql = f"""
            SELECT {self._doc_select}
            FROM virtual_documents
            WHERE deleted = 0 
              AND is_immutable = 0
              AND (semantic_data IS NULL OR semantic_data = '{{}}' OR 
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
        sql = f"""
            SELECT {self._doc_select}
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
                
            bodies = doc.semantic_data.bodies
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
        sql = f"""
            SELECT {self._doc_select}
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

    def _migrate_schema(self) -> None:
        """Adds missing columns for hybrid protection support."""
        if not self.connection: return
        
        cursor = self.connection.cursor()
        cursor.execute("PRAGMA table_info(virtual_documents)")
        cols = [row[1] for row in cursor.fetchall()]
        
        if "pdf_class" not in cols:
            print("[DB] Migrating: Adding 'pdf_class' to virtual_documents")
            try:
                with self.connection:
                    self.connection.execute("ALTER TABLE virtual_documents ADD COLUMN pdf_class TEXT DEFAULT 'C'")
            except Exception as e:
                print(f"[DB] Migration Error: {e}")

    def _create_fts_triggers(self) -> None:
        """Maintains FTS synchronicity via SQLite triggers."""
        triggers = [
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_ai AFTER INSERT ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(uuid, export_filename, type_tags, cached_full_text)
                VALUES (new.uuid, new.export_filename, new.type_tags, new.cached_full_text);
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_ad AFTER DELETE ON virtual_documents BEGIN
                DELETE FROM virtual_documents_fts WHERE uuid = old.uuid;
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_au AFTER UPDATE ON virtual_documents
            WHEN (old.export_filename IS NOT new.export_filename OR
                  old.type_tags IS NOT new.type_tags OR
                  old.cached_full_text IS NOT new.cached_full_text)
            BEGIN
                DELETE FROM virtual_documents_fts WHERE uuid = old.uuid;
                INSERT INTO virtual_documents_fts(uuid, export_filename, type_tags, cached_full_text)
                VALUES (new.uuid, new.export_filename, new.type_tags, new.cached_full_text);
            END;
            """
        ]
        with self.connection:
            for trigger_sql in triggers:
                self.connection.execute(trigger_sql)

    def _create_usage_triggers(self) -> None:
        """
        Phase 110: Atomic Usage Tracker.
        Sets 'last_used' to Current Timestamp whenever document metadata
        or content is changed (INSERT or UPDATE), but NOT during passive selection.
        """
        triggers = [
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_usage_insert 
            AFTER INSERT ON virtual_documents
            FOR EACH ROW
            WHEN (new.last_used IS NULL)
            BEGIN
                UPDATE virtual_documents 
                SET last_used = strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') 
                WHERE uuid = new.uuid;
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_usage_update 
            AFTER UPDATE ON virtual_documents
            FOR EACH ROW
            WHEN (
                (new.last_used IS old.last_used OR new.last_used IS NULL) AND
                (
                    old.status IS NOT new.status OR
                    old.export_filename IS NOT new.export_filename OR
                    old.is_immutable IS NOT new.is_immutable OR
                    old.semantic_data IS NOT new.semantic_data OR
                    old.deleted IS NOT new.deleted OR
                    old.type_tags IS NOT new.type_tags OR
                    old.tags IS NOT new.tags
                )
            )
            BEGIN
                UPDATE virtual_documents 
                SET last_used = strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') 
                WHERE uuid = new.uuid;
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

    def rename_tag(self, old_tag: str, new_tag: str) -> int:
        """
        Renames a tag across all documents.
        Returns the number of documents modified.
        """
        cursor = self.connection.cursor()
        sql_find = "SELECT uuid, tags FROM virtual_documents WHERE tags LIKE ?"
        cursor.execute(sql_find, (f'%"%s"%' % old_tag.replace('"', '""'),))
        rows = cursor.fetchall()
        
        count = 0
        for uid, tags_json in rows:
            try:
                tags = json.loads(tags_json or "[]")
                if old_tag in tags:
                    # Replace
                    tags = [new_tag if t == old_tag else t for t in tags]
                    # Unique
                    tags = list(dict.fromkeys(tags))
                    self.update_document_metadata(uid, {"tags": tags})
                    count += 1
            except Exception:
                continue
        return count

    def delete_tag(self, tag: str) -> int:
        """
        Removes a tag from all documents.
        """
        cursor = self.connection.cursor()
        sql_find = "SELECT uuid, tags FROM virtual_documents WHERE tags LIKE ?"
        cursor.execute(sql_find, (f'%"%s"%' % tag.replace('"', '""'),))
        rows = cursor.fetchall()
        
        count = 0
        for uid, tags_json in rows:
            try:
                tags = json.loads(tags_json or "[]")
                if tag in tags:
                    tags = [t for t in tags if t != tag]
                    self.update_document_metadata(uid, {"tags": tags})
                    count += 1
            except Exception:
                continue
        return count

    def merge_tags(self, tags_to_merge: List[str], target_tag: str) -> int:
        """
        Merges multiple tags into a single target tag.
        """
        cursor = self.connection.cursor()
        sql_find = "SELECT uuid, tags FROM virtual_documents"
        cursor.execute(sql_find)
        rows = cursor.fetchall()
        
        count = 0
        merge_set = set(tags_to_merge)
        for uid, tags_json in rows:
            try:
                tags = json.loads(tags_json or "[]")
                current_set = set(tags)
                if current_set.intersection(merge_set):
                    # Remove merging tags
                    new_tags = [t for t in tags if t not in merge_set]
                    # Add target if not present
                    if target_tag not in new_tags:
                        new_tags.append(target_tag)
                    
                    self.update_document_metadata(uid, {"tags": new_tags})
                    count += 1
            except Exception:
                continue
        return count

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
                cached_full_text, tags,
                deleted_at, locked_at, exported_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, 1, 0, ?, ?, ?, ?, ?)
        """
        try:
            with self.connection:
                if isinstance(doc.semantic_data, SemanticExtraction):
                    sd_json = json.dumps(doc.semantic_data.model_dump(mode='json'))
                else:
                    sd_json = json.dumps(doc.semantic_data or {}, default=str)

                self.connection.execute(sql, (
                    doc.uuid, sm_json, doc.status or "NEW", doc.original_filename or "Unknown",
                    created, type_tags_json, sd_json, (doc.text_content or doc.cached_full_text),
                    user_tags_json,
                    doc.deleted_at, doc.locked_at, doc.exported_at
                ))
        except sqlite3.Error as e:
            logger.error(f"Failed to insert document {doc.uuid}: {e}")

