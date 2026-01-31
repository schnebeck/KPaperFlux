"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/repositories/logical_repo.py
Version:        1.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Repository for managing persistence of VirtualDocument models in
                the sqlite database. Handles complex serialization of mapping
                and semantic data.
------------------------------------------------------------------------------
"""

import json
from datetime import date, datetime
from typing import Any, List, Optional

from core.models.virtual import VirtualDocument

from .base import BaseRepository


class EnhancedJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder to handle datetime and date objects.
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


class LogicalRepository(BaseRepository):
    """
    Manages access to the 'virtual_documents' table.
    """

    def save(self, doc: VirtualDocument) -> None:
        """
        Inserts or updates a virtual document record.

        Args:
            doc: The VirtualDocument instance to save.
        """
        # 1. Prepare JSON mapping
        mapping_json = doc.get_mapping_json()
        semantic_json = json.dumps(doc.semantic_data, cls=EnhancedJSONEncoder) if doc.semantic_data else None

        # 2. Calculate Total Pages
        total_pages = sum(len(ref.pages) for ref in doc.source_mapping)

        # 3. SQL (Upsert)
        sql = """
        INSERT OR REPLACE INTO virtual_documents (
            uuid, source_mapping, status, export_filename, 
            last_used, last_processed_at, is_immutable, thumbnail_path, 
            cached_full_text, semantic_data, created_at, deleted, page_count_virt,
            type_tags, sender, doc_date, amount, tags
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """

        type_tags_json = json.dumps(doc.type_tags) if doc.type_tags else None
        tags_json = json.dumps(doc.tags) if doc.tags else None

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
            total_pages,
            type_tags_json,
            doc.sender,
            doc.doc_date,
            doc.amount,
            tags_json,
        )

        with self.conn:
            self.conn.execute(sql, values)

    def get_by_uuid(self, uuid: str) -> Optional[VirtualDocument]:
        """
        Fetches a logical document by its UUID.

        Args:
            uuid: The unique identifier.

        Returns:
            The VirtualDocument instance if found, else None.
        """
        sql = """
        SELECT 
            uuid, source_mapping, status, export_filename, last_used, 
            last_processed_at, is_immutable, thumbnail_path, cached_full_text, 
            semantic_data, created_at, deleted, page_count_virt, type_tags,
            sender, doc_date, amount, tags
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
        Finds all logical entities that reference a specific physical file.

        Args:
            file_uuid: The UUID of the physical file.

        Returns:
            A list of VirtualDocument instances referencing the file.
        """
        pattern = f'%"{file_uuid}"%'
        sql = """
        SELECT 
            uuid, source_mapping, status, export_filename, last_used, 
            last_processed_at, is_immutable, thumbnail_path, cached_full_text, 
            semantic_data, created_at, deleted, page_count_virt, type_tags,
            sender, doc_date, amount, tags
        FROM virtual_documents
        WHERE source_mapping LIKE ?
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (pattern,))
        rows = cursor.fetchall()

        results: List[VirtualDocument] = []
        for row in rows:
            results.append(VirtualDocument.from_row(row))
        return results

    def delete_by_uuid(self, uuid: str) -> None:
        """
        Hard deletes a virtual document record.

        Args:
            uuid: The UUID of the record to delete.
        """
        with self.conn:
            self.conn.execute("DELETE FROM virtual_documents WHERE uuid = ?", (uuid,))

    def get_all(self) -> List[VirtualDocument]:
        """
        Fetches all logical documents (including deleted).

        Returns:
            A list of all VirtualDocument instances.
        """
        sql = """
        SELECT 
            uuid, source_mapping, status, export_filename, last_used, 
            last_processed_at, is_immutable, thumbnail_path, cached_full_text, 
            semantic_data, created_at, deleted, page_count_virt, type_tags,
            sender, doc_date, amount, tags
        FROM virtual_documents
        """
        cursor = self.conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [VirtualDocument.from_row(row) for row in rows]
