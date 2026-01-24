from typing import Optional, List
import json
import sqlite3
from .base import BaseRepository
from core.models.virtual import VirtualDocument, SourceReference

class LogicalRepository(BaseRepository):
    """
    Manages access to 'semantic_entities' table.
    """
    
    def save(self, doc: VirtualDocument):
        """
        Insert or Update a semantic entity.
        We update both Core CDM columns AND the JSON blobs.
        """
        # Helper for dates in JSON
        from datetime import date, datetime
        def json_serial(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
            
        # 1. Prepare JSONs
        mapping_json = doc.get_mapping_json()
        tags_json = doc.get_tags_json()
        # Ensure semantic_data has minimal structure
        canonical_json = json.dumps(doc.semantic_data, default=json_serial) if doc.semantic_data else None
        
        # 2. Extract CDM
        # If doc.semantic_data has 'summary', use it to backfill
        if not doc.sender_name and doc.semantic_data and 'summary' in doc.semantic_data:
             doc.sender_name = doc.semantic_data['summary'].get('sender_name')
             
        # 3. SQL (Upsert)
        sql = """
        INSERT OR REPLACE INTO semantic_entities (
            entity_uuid, source_doc_uuid, doc_type, 
            sender_name, doc_date, canonical_data, 
            status, created_at,
            source_mapping, type_tags, deleted
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """
        
        # Note: source_doc_uuid is deprecated but NOT NULL.
        # We must provide it. For now, use entity_uuid (Self-Ref to Shadow Document)
        # to satisfy FOREIGN KEY(source_doc_uuid) REFERENCES documents(uuid).
        # Fix for Phase 8: Point to Physical File UUID to support SQL View JOIN
        src_uid = doc.entity_uuid # Default Fallback (Safe Anchor)
        
        if doc.source_mapping and len(doc.source_mapping) > 0:
             # doc.source_mapping is list of SourceReference objects
             # We link the entity to the MAIN physical file (the first one)
             src_uid = doc.source_mapping[0].file_uuid

            
        values = (
            doc.entity_uuid,
            src_uid, # source_doc_uuid (Legacy/Anchor)
            doc.doc_type,
            doc.sender_name,
            doc.doc_date,
            canonical_json,
            doc.status,
            doc.created_at,
            mapping_json,
            tags_json,
            doc.deleted
        )
        
        with self.conn:
            self.conn.execute(sql, values)

    def get_by_uuid(self, uuid: str) -> Optional[VirtualDocument]:
        """Fetch Logical Document."""
        sql = """
        SELECT 
            entity_uuid, source_doc_uuid, doc_type, 
            sender_name, doc_date, canonical_data, 
            status, created_at,
            source_mapping, type_tags, deleted
        FROM semantic_entities
        WHERE entity_uuid = ?
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (uuid,))
        row = cursor.fetchone()
        
        if row:
            # entity_uuid=0, source=1, type=2, sender=3, date=4, canon=5, status=6, created=7, map=8, tags=9
            
            # Parse JSONs
            mapping = []
            if row[8]:
                try: 
                    raw_map = json.loads(row[8])
                    # Convert dicts to SourceReference
                    mapping = [SourceReference(**m) for m in raw_map]
                except: pass
                
            tags = []
            if row[9]:
                try: tags = json.loads(row[9])
                except: pass
                
            semantic = {}
            if row[5]:
                try: semantic = json.loads(row[5])
                except: pass
                
            doc = VirtualDocument(
                entity_uuid=row[0],
                source_mapping=mapping,
                type_tags=tags,
                semantic_data=semantic,
                doc_date=row[4],
                sender_name=row[3],
                doc_type=row[2],
                status=row[6],
                created_at=row[7],
                deleted=bool(row[10]) # Check index! 0..9 was tags. SELECT needs updating.
            )
            return doc
            
        return None

    def get_by_source_file(self, file_uuid: str) -> List[VirtualDocument]:
        """
        Find all logical entities that reference a specific physical file.
        This is tricky because 'source_doc_uuid' might be the entity itself (self-ref).
        We reliably find them by scanning the source_mapping JSON or using a join if we had a normalized table.
        Since we store mapping as JSON, we must query by `source_doc_uuid` (Legacy Anchor) 
        OR scan where source_mapping LIKE '%file_uuid%'.
        
        For robust "Re-Structure":
        If we strictly followed the rule that `source_doc_uuid` tracks the physical file, it would be easy.
        But in `save()`, we set `src_uid = doc.entity_uuid`.
        
        So we rely on `search_web`... no wait.
        We can use JSON functions in SQLite if enabled, or simple LIKE.
        LIKE '%"file_uuid": "UUID"%'
        """
        # "file_uuid": "..."
        pattern = f'%"{file_uuid}"%'
        sql = """
        SELECT 
            entity_uuid, source_doc_uuid, doc_type, 
            sender_name, doc_date, canonical_data, 
            status, created_at,
            source_mapping, type_tags
        FROM semantic_entities
        WHERE source_mapping LIKE ?
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (pattern,))
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            # Parse (Reuse logic? Refactor `_row_to_doc` later)
            mapping = []
            if row[8]:
                try: mapping = [SourceReference(**m) for m in json.loads(row[8])]
                except: pass
            
            tags = []
            if row[9]:
                try: tags = json.loads(row[9])
                except: pass
                
            semantic = {}
            if row[5]:
                try: semantic = json.loads(row[5])
                except: pass

            results.append(VirtualDocument(
                entity_uuid=row[0],
                source_mapping=mapping,
                type_tags=tags,
                semantic_data=semantic,
                doc_date=row[4],
                sender_name=row[3],
                doc_type=row[2],
                status=row[6],
                created_at=row[7]
            ))
        return results

    def delete_by_uuid(self, uuid: str):
        """Hard delete of a logical entity, decrementing physical ref count."""
        # 1. Get Source UUID (Locked in transaction?)
        cursor = self.conn.cursor()
        cursor.execute("SELECT source_doc_uuid FROM semantic_entities WHERE entity_uuid = ?", (uuid,))
        row = cursor.fetchone()
        
        if not row: return
        
        source_uuid = row[0]
        
        with self.conn:
             self.conn.execute("DELETE FROM semantic_entities WHERE entity_uuid = ?", (uuid,))
             # Decrement Ref Count (Physical/Legacy View)
             # Note: documents View relies on physical_files.ref_count
             self.conn.execute("UPDATE physical_files SET ref_count = MAX(0, ref_count - 1) WHERE file_uuid = ?", (source_uuid,))
