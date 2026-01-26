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
        allowed = ["status", "export_filename", "deleted", "is_immutable", "locked", "type_tags", "cached_full_text"]
        filtered = {k: v for k, v in updates.items() if k in allowed}
        
        if "locked" in filtered:
             filtered["is_immutable"] = int(filtered.pop("locked"))
             
        if "type_tags" in filtered and isinstance(filtered["type_tags"], list):
             filtered["type_tags"] = json.dumps(filtered["type_tags"])
        
        if filtered:
            self._update_table("virtual_documents", uuid, filtered, pk_col="uuid")
            return True
        return False

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
                   cached_full_text
            FROM virtual_documents
            WHERE uuid = ?
        """
        cursor = self.connection.cursor()
        cursor.execute(sql, (uuid,))
        row = cursor.fetchone()
        if row:
            type_tags = []
            if row[7]:
                try: type_tags = json.loads(row[7])
                except: pass
                
            return Document(
                uuid=row[0],
                extra_data={"source_mapping": row[1]},
                status=row[2],
                original_filename=row[3],
                page_count=row[4],
                created_at=row[5],
                locked=bool(row[6]),
                deleted=False,
                doc_type="entity",
                type_tags=type_tags,
                cached_full_text=row[8] if len(row) > 8 else None,
                text_content=row[8] if len(row) > 8 else None # keep for compatibility
            )
        return None

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
        # In Stage 0/1, we only have source_mapping as JSON in virtual_documents.
        # Legacy extra_data/semantic_data are gone.
        sql = "SELECT source_mapping FROM virtual_documents WHERE source_mapping IS NOT NULL"
        cursor = self.connection.cursor()
        keys = set()
        
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            for row in rows:
                if row[0]:
                    try:
                        data = json.loads(row[0])
                        if isinstance(data, list):
                             # source_mapping is a list. Extract keys from elements?
                             for item in data:
                                 if isinstance(item, dict):
                                     self._extract_keys_recursive(item, keys, prefix="source:")
                    except:
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
        Search Virtual Documents using a structured query.
        Simplified for Stage 0/1.
        """
        # For now, we return all as we transition to the new structured query builder.
        return self.get_all_entities_view()

    def get_all_entities_view(self) -> List[Document]:
        """
        Primary data view for Stage 0/1 Documents.
        Targeting: virtual_documents.
        """
        sql = """
            SELECT uuid, source_mapping, status, 
                   COALESCE(export_filename, 'Entity ' || substr(uuid, 1, 8)),
                   page_count_virt, created_at, is_immutable, type_tags
            FROM virtual_documents
            WHERE deleted = 0
            ORDER BY created_at DESC
        """
        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        docs = []
        for row in rows:
            type_tags = []
            if len(row) > 7 and row[7]:
                 try: type_tags = json.loads(row[7])
                 except: pass

            docs.append(Document(
                uuid=row[0],
                extra_data={"source_mapping": row[1]},
                status=row[2],
                original_filename=row[3],
                page_count=row[4],
                created_at=row[5],
                locked=bool(row[6]),
                deleted=False,
                doc_type="entity",
                type_tags=type_tags
            ))
        return docs


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
                   v.page_count_virt, v.created_at, v.is_immutable, v.type_tags
            FROM virtual_documents v
            JOIN virtual_documents_fts f ON v.uuid = f.uuid
            WHERE f.content MATCH ? AND v.deleted = 0
            ORDER BY rank
        """
        cursor = self.connection.cursor()
        cursor.execute(sql, (search_text,))
        rows = cursor.fetchall()
        
        docs = []
        for row in rows:
            type_tags = []
            if len(row) > 7 and row[7]:
                 try: type_tags = json.loads(row[7])
                 except: pass

            docs.append(Document(
                uuid=row[0],
                extra_data={"source_mapping": row[1]},
                status=row[2],
                original_filename=row[3],
                page_count=row[4],
                created_at=row[5],
                locked=bool(row[6]),
                deleted=False,
                doc_type="entity",
                type_tags=type_tags
            ))
        return docs


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
                v.created_at
            FROM virtual_documents v
            WHERE v.deleted = 1
            ORDER BY v.created_at DESC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            doc = Document(
                uuid=row[0],
                extra_data={"source_mapping": row[1]},
                status=row[2],
                original_filename=row[3],
                page_count=row[4],
                created_at=row[5],
                deleted=True,
                doc_type="entity"
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

    def _create_fts_triggers(self):
        """Create triggers to sync FTS table with virtual_documents."""
        triggers = [
            # INSERT
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_ai AFTER INSERT ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(rowid, uuid, filename, content)
                VALUES (new.rowid, new.uuid, new.export_filename, new.cached_full_text);
            END;
            """,
            # DELETE
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_ad AFTER DELETE ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(virtual_documents_fts, rowid, uuid, filename, content)
                VALUES('delete', old.rowid, old.uuid, old.export_filename, old.cached_full_text);
            END;
            """,
            # UPDATE
            """
            CREATE TRIGGER IF NOT EXISTS virtual_documents_au AFTER UPDATE ON virtual_documents BEGIN
                INSERT INTO virtual_documents_fts(virtual_documents_fts, rowid, uuid, filename, content)
                VALUES('delete', old.rowid, old.uuid, old.export_filename, old.cached_full_text);
                INSERT INTO virtual_documents_fts(rowid, uuid, filename, content)
                VALUES (new.rowid, new.uuid, new.export_filename, new.cached_full_text);
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
