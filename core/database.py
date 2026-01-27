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
            -- Using a simplified version: Number of source segments (files)
            page_count_virt INTEGER DEFAULT 0,
            type_tags TEXT -- JSON List of strings
        );
        """
        
        create_virtual_documents_fts = """
        CREATE VIRTUAL TABLE IF NOT EXISTS virtual_documents_fts USING fts5(
            uuid UNINDEXED,
            filename,
            type_tags,
            content,
            content='virtual_documents',
            content_rowid='rowid'
        );
        """
        
        with self.connection:
            self.connection.execute(create_physical_files_table)
            self.connection.execute(create_virtual_documents_table)
            self.connection.execute(create_virtual_documents_fts)
            
            # Migration: Ensure type_tags exists if table was created earlier
            try:
                self.connection.execute("ALTER TABLE virtual_documents ADD COLUMN type_tags TEXT")
            except sqlite3.OperationalError:
                pass # Already exists
                
            self.connection.execute("DROP VIEW IF EXISTS documents")
        
        self._create_fts_triggers()
        self.connection.commit()




    def update_document_metadata(self, uuid: str, updates: dict) -> bool:
        """
        Update specific fields of a VirtualDocument.
        """
        if not updates: return False
        
        # Whitelist for Stage 0/1
        allowed = ["status", "export_filename", "deleted", "is_immutable", "locked", "type_tags", "cached_full_text", "last_used", "last_processed_at"]
        filtered = {k: v for k, v in updates.items() if k in allowed}
        
        if "locked" in filtered:
             filtered["is_immutable"] = int(filtered.pop("locked"))
             
        if "type_tags" in filtered and isinstance(filtered["type_tags"], list):
             filtered["type_tags"] = json.dumps(filtered["type_tags"])
        
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
        """Fetch a single Stage 0/1 document."""
        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags, 
                   cached_full_text, last_used, last_processed_at,
                   semantic_data
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
        
        # 1. Source Mapping Keys
        try:
            cursor.execute("SELECT source_mapping FROM virtual_documents WHERE source_mapping IS NOT NULL")
            for row in cursor.fetchall():
                if row[0]:
                    try:
                        data = json.loads(row[0])
                        if isinstance(data, list):
                             for item in data:
                                 if isinstance(item, dict):
                                     self._extract_keys_recursive(item, keys, prefix="source:")
                    except: pass
        except: pass

        # 2. Semantic Data Keys (AI Results)
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
        
        sql = f"""
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags,
                   cached_full_text, last_used, last_processed_at,
                   semantic_data
            FROM virtual_documents
            WHERE {where_clause}
            ORDER BY created_at DESC
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [self._row_to_doc(row) for row in rows]
        except sqlite3.Error as e:
            print(f"[Database] Advanced Search Error: {e}\nSQL: {sql}\nParams: {params}")
            return []

    def _build_where_clause(self, node: dict):
        """Recursively builds SQL WHERE clause from query node."""
        if "field" in node:
            # It's a single condition
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
            
        elif "conditions" in node:
            # It's a group (AND/OR)
            logic_op = node.get("operator", "AND").upper()
            sub_clauses = []
            all_params = []
            
            for cond in node["conditions"]:
                clause, params = self._build_where_clause(cond)
                if clause:
                    sub_clauses.append(f"({clause})")
                    all_params.extend(params)
            
            if not sub_clauses:
                return "1=1", [] # No-op
                
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
            
            # Stage 1 Semantic fields (nested in semantic_data)
            "direction": "json_extract(semantic_data, '$.direction')",
            "tenant_context": "json_extract(semantic_data, '$.tenant_context')",
            "confidence": "json_extract(semantic_data, '$.confidence')",
            "reasoning": "json_extract(semantic_data, '$.reasoning')",
            "doc_type": "json_extract(semantic_data, '$.doc_types[0]')" # First one as primary for simple search
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
            
        return field # fallback

    def _map_op_to_sql(self, expr: str, op: str, val: Any) -> tuple:
        """Translates operator and value into SQL clause and params."""
        if op == "equals":
            return f"{expr} = ?", [val]
        if op == "contains":
            # For type_tags (JSON array), we use LIKE since SQLite is flexible
            # Or json_each if we wanted perfect precision.
            return f"{expr} LIKE ?", [f"%{val}%"]
        if op == "starts_with":
            return f"{expr} LIKE ?", [f"{val}%"]
        if op == "gt":
            return f"{expr} > ?", [val]
        if op == "lt":
            return f"{expr} < ?", [val]
        if op == "is_empty":
            return f"{expr} IS NULL OR {expr} = ''", []
        if op == "is_not_empty":
            return f"{expr} IS NOT NULL AND {expr} != ''", []
        if op == "in":
            if not isinstance(val, list): val = [val]
            placeholders = ", ".join(["?" for _ in val])
            return f"{expr} IN ({placeholders})", val
        if op == "between":
            if isinstance(val, list) and len(val) == 2:
                return f"{expr} BETWEEN ? AND ?", [val[0], val[1]]
                
        return "1=1", [] # Fallback

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
                   semantic_data
            FROM virtual_documents
            WHERE deleted = 0
            ORDER BY created_at DESC
        """
        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        return [self._row_to_doc(row) for row in rows]

    def _row_to_doc(self, row) -> Document:
        """Helper to convert a DB row to a Document object with semantic metadata."""
        # Index Map: 
        # 0:uuid, 1:source_mapping, 2:status, 3:filename, 4:page_count, 5:created_at, 
        # 6:locked, 7:type_tags, 8:cached_full_text, 9:last_used, 10:last_processed_at, 11:semantic_data
        
        type_tags = []
        if len(row) > 7 and row[7]:
            try: type_tags = json.loads(row[7])
            except: pass
            
        semantic_data = None
        if len(row) > 11 and row[11]:
            try: semantic_data = json.loads(row[11])
            except: pass

        doc_data = {
            "uuid": row[0],
            "extra_data": {"source_mapping": row[1]},
            "status": row[2],
            "original_filename": row[3],
            "page_count": row[4],
            "created_at": row[5],
            "locked": bool(row[6]),
            "deleted": False,
            "doc_type": "entity",
            "type_tags": type_tags,
            "cached_full_text": row[8] if len(row) > 8 else None,
            "text_content": row[8] if len(row) > 8 else None,
            "last_used": row[9] if len(row) > 9 else None,
            "last_processed_at": row[10] if len(row) > 10 else None,
            "semantic_data": semantic_data
        }

        # If semantic_data exists, Pydantic Document model has many attributes 
        # that match standard semantic keys (invoice_number -> invoice_number etc).
        if semantic_data:
             doc_data.update(semantic_data)
             
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
                   v.semantic_data
            FROM virtual_documents v
            JOIN virtual_documents_fts f ON v.uuid = f.uuid
            WHERE f.content MATCH ? AND v.deleted = 0
            ORDER BY rank
        """
        cursor = self.connection.cursor()
        cursor.execute(sql, (search_text,))
        rows = cursor.fetchall()
        
        return [self._row_to_doc(row) for row in rows]


    def delete_document(self, uuid: str) -> bool:
        """
        Delete a document by its UUID (Soft Delete).
        Applies to virtual_documents.
        """
        sql_ent = "UPDATE virtual_documents SET deleted = 1 WHERE uuid = ?"
        
        cursor = self.connection.cursor()
        with self.connection:
            cursor.execute(sql_ent, (uuid,))
            
        return cursor.rowcount > 0

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
        Restore a soft-deleted document (Trash -> Normal).
        """
        sql_ent = "UPDATE virtual_documents SET deleted = 0 WHERE uuid = ?"
        
        with self.connection:
            self.connection.execute(sql_ent, (uuid,))
            
        return self.connection.total_changes > 0

    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()

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
        Tags are stored in semantic_data->tags_and_flags as a JSON list.
        """
        sql = "SELECT json_extract(semantic_data, '$.tags_and_flags') FROM virtual_documents WHERE semantic_data IS NOT NULL"
        cursor = self.connection.cursor()
        tag_counts = {}
        
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            for (tags_json,) in rows:
                if not tags_json: continue
                try:
                    tags_list = json.loads(tags_json)
                    if isinstance(tags_list, list):
                        for t in tags_list:
                            if t and isinstance(t, str):
                                tag_counts[t] = tag_counts.get(t, 0) + 1
                except: pass
        except sqlite3.OperationalError:
            pass
            
        return tag_counts

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
        
    def get_deleted_entities_view(self) -> list:
        """
        Fetch ALL 'soft-deleted' virtual documents for Trash Bin view.
        """
        cursor = self.connection.cursor()
        sql = """
            SELECT 
                v.uuid,
                v.source_mapping,
                v.status,
                COALESCE(v.export_filename, 'Entity ' || substr(v.uuid, 1, 8)) as filename,
                v.page_count_virt,
                v.created_at,
                v.is_immutable,
                v.type_tags,
                v.cached_full_text,
                v.last_used,
                v.last_processed_at
            FROM virtual_documents v
            WHERE v.deleted = 1
            ORDER BY v.created_at DESC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            type_tags = []
            if len(row) > 7 and row[7]:
                 try: type_tags = json.loads(row[7])
                 except: pass

            doc = Document(
                uuid=row[0],
                extra_data={"source_mapping": row[1]},
                status=row[2],
                original_filename=row[3],
                page_count=row[4],
                created_at=row[5],
                locked=bool(row[6]) if len(row) > 6 else False,
                deleted=True,
                doc_type="entity",
                type_tags=type_tags,
                cached_full_text=row[8] if len(row) > 8 else None,
                text_content=row[8] if len(row) > 8 else None,
                last_used=row[9] if len(row) > 9 else None,
                last_processed_at=row[10] if len(row) > 10 else None
            )
            results.append(doc)
            
        return results

    def delete_entity(self, uuid: str) -> bool:
        """Soft Delete a Virtual Document."""
        cursor = self.connection.cursor()
        cursor.execute("UPDATE virtual_documents SET deleted = 1 WHERE uuid = ?", (uuid,))
        self.connection.commit()
        return cursor.rowcount > 0

    def restore_entity(self, uuid: str) -> bool:
        """Restore a Soft Deleted Virtual Document."""
        cursor = self.connection.cursor()
        cursor.execute("UPDATE virtual_documents SET deleted = 0 WHERE uuid = ?", (uuid,))
        self.connection.commit()
        return cursor.rowcount > 0

    def purge_entity(self, uuid: str) -> bool:
        """
        Permanently Delete an Entity (Virtual Document).
        """
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM virtual_documents WHERE uuid = ?", (uuid,))
        self.connection.commit()
        return cursor.rowcount > 0
            
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
            return False

    def get_source_mapping_from_entity(self, entity_uuid: str) -> Optional[list]:
        """
        Get the 'source_mapping' JSON (list of SourceReferences) for an entity.
        Used by GUI to find the physical file for a Logical Entity (Shadow Document).
        """
        cursor = self.connection.cursor()
        cursor.execute("SELECT source_mapping FROM virtual_documents WHERE uuid = ?", (entity_uuid,))
        row = cursor.fetchone()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except:
                pass
        return None

    def get_source_uuid_from_entity(self, entity_uuid: str) -> Optional[str]:
        """Phase 98: Resolve an entity UUID to its primary source physical UUID."""
        mapping = self.get_source_mapping_from_entity(entity_uuid)
        if mapping and len(mapping) > 0:
            return mapping[0].get("file_uuid")
        return None

    def _create_fts_triggers(self):
        """Create triggers to sync FTS table with virtual_documents."""
        triggers = [
            # INSERT
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_ai AFTER INSERT ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(rowid, uuid, filename, type_tags, content)
                VALUES (new.rowid, new.uuid, new.export_filename, new.type_tags, new.cached_full_text);
            END;
            """,
            # DELETE
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_ad AFTER DELETE ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(virtual_documents_fts, rowid, uuid, filename, type_tags, content)
                VALUES('delete', old.rowid, old.uuid, old.export_filename, old.type_tags, old.cached_full_text);
            END;
            """,
            # UPDATE
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_au AFTER UPDATE ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(virtual_documents_fts, rowid, uuid, filename, type_tags, content)
                VALUES('delete', old.rowid, old.uuid, old.export_filename, old.type_tags, old.cached_full_text);
                INSERT INTO virtual_documents_fts(rowid, uuid, filename, type_tags, content)
                VALUES (new.rowid, new.uuid, new.export_filename, new.type_tags, new.cached_full_text);
            END;
            """
        ]
        with self.connection:
            for t in triggers:
                self.connection.execute(t)

    def _update_table(self, table: str, pk_val: str, updates: dict, pk_col: str = "uuid"):
        """Helper to update multiple columns in a table."""
        if not updates: return
        cols = ", ".join([f"{k} = ?" for k in updates.keys()])
        sql = f"UPDATE {table} SET {cols} WHERE {pk_col} = ?"
        vals = list(updates.values()) + [pk_val]
        with self.connection:
            self.connection.execute(sql, vals)
