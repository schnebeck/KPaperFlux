from typing import Optional, List
import json
import sqlite3
from .base import BaseRepository
from core.models.virtual import VirtualDocument, SourceReference

class LogicalRepository(BaseRepository):
    """
    Manages access to 'virtual_documents' table.
    """
    
    def save(self, doc: VirtualDocument):
        """
        Insert or Update a virtual document.
        """
        # 1. Prepare JSON mapping
        mapping_json = doc.get_mapping_json()
        semantic_json = json.dumps(doc.semantic_data) if doc.semantic_data else None
        
        # 2. Calculate Total Pages
        total_pages = sum(len(ref.pages) for ref in doc.source_mapping)
        
        # 3. SQL (Upsert)
        sql = """
        INSERT OR REPLACE INTO virtual_documents (
            uuid, source_mapping, status, export_filename, 
            last_used, last_processed_at, is_immutable, thumbnail_path, 
            cached_full_text, semantic_data, created_at, deleted, page_count_virt
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """
        
        values = (
            doc.uuid,
            mapping_json,
            doc.status,
            doc.export_filename,
            doc.last_used,
            doc.last_processed_at,
            int(doc.is_immutable),
            doc.thumbnail_path,
            doc.cached_full_text,
            semantic_json,
            doc.created_at,
            int(doc.deleted),
            total_pages
        )
        
        with self.conn:
            self.conn.execute(sql, values)

    def get_by_uuid(self, uuid: str) -> Optional[VirtualDocument]:
        """Fetch Logical Document."""
        sql = """
        SELECT 
            uuid, source_mapping, status, export_filename, last_used, 
            last_processed_at, is_immutable, thumbnail_path, cached_full_text, 
            semantic_data, created_at, deleted, page_count_virt
        FROM virtual_documents
        WHERE uuid = ?
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (uuid,))
        row = cursor.fetchone()
        
        if row:
            return VirtualDocument.from_row(row)
        return None

    def get_by_source_file(self, file_uuid: str) -> List[VirtualDocument]:
        """
        Find all logical entities that reference a specific physical file.
        """
        pattern = f'%"{file_uuid}"%'
        sql = """
        SELECT 
            uuid, source_mapping, status, export_filename, last_used, 
            last_processed_at, is_immutable, thumbnail_path, cached_full_text, 
            semantic_data, created_at, deleted, page_count_virt
        FROM virtual_documents
        WHERE source_mapping LIKE ?
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (pattern,))
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append(VirtualDocument.from_row(row))
        return results

    def delete_by_uuid(self, uuid: str):
        """Hard delete of a virtual document."""
        with self.conn:
             self.conn.execute("DELETE FROM virtual_documents WHERE uuid = ?", (uuid,))
