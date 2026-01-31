"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/repositories/logical_repo.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Repository for managing persistence of VirtualDocument models in 
                the SQLite database. Handles complex serialization of mapping 
                and semantic data using custom JSON encoders for temporal data.
------------------------------------------------------------------------------
"""

import json
from datetime import date, datetime
from typing import Any, List, Optional, Tuple

from core.models.virtual import VirtualDocument

from .base import BaseRepository


class EnhancedJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder to handle datetime and date objects.
    Ensures that semantic data remains serializable even with complex types.
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


class LogicalRepository(BaseRepository):
    """
    Manages access to the 'virtual_documents' table, providing persistence
    for logical business entities.
    """

    def save(self, doc: VirtualDocument) -> bool:
        """
        Inserts or updates a virtual document record in the database.

        Args:
            doc: The VirtualDocument instance to persist.

        Returns:
            True if the operation was successful.
        """
        # 1. Prepare JSON structures
        mapping_json = doc.to_source_mapping_json()
        semantic_json = json.dumps(doc.semantic_data, cls=EnhancedJSONEncoder) if doc.semantic_data else None
        type_tags_json = json.dumps(doc.type_tags) if doc.type_tags else None
        tags_json = json.dumps(doc.tags) if doc.tags else None

        # 2. Re-calculate Total Pages for physical tracking
        total_pages = sum(len(ref.pages) for ref in doc.source_mapping)

        # 3. SQL execution
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

        try:
            with self.conn:
                self.conn.execute(sql, values)
            return True
        except Exception as e:
            print(f"[LogicalRepo] Save error: {e}")
            return False

    def get_by_uuid(self, uuid: str) -> Optional[VirtualDocument]:
        """
        Fetches a logical document by its unique UUID.

        Args:
            uuid: The document UUID.

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
        Finds all logical entities that reference a specific physical file UUID.

        Args:
            file_uuid: The UUID of the physical source file.

        Returns:
            A list of matching VirtualDocument instances.
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

        return [VirtualDocument.from_row(row) for row in rows]

    def delete_by_uuid(self, uuid: str) -> bool:
        """
        Hard deletes a virtual document record from the database.

        Args:
            uuid: The UUID of the record to remove.

        Returns:
            True if the operation was successful.
        """
        try:
            with self.conn:
                self.conn.execute("DELETE FROM virtual_documents WHERE uuid = ?", (uuid,))
            return True
        except Exception as e:
            print(f"[LogicalRepo] Delete error: {e}")
            return False

    def get_all(self, include_deleted: bool = True) -> List[VirtualDocument]:
        """
        Fetches all logical documents from the repository.

        Args:
            include_deleted: If False, filters out records marked as deleted.

        Returns:
            A list of VirtualDocument instances.
        """
        sql = """
        SELECT 
            uuid, source_mapping, status, export_filename, last_used, 
            last_processed_at, is_immutable, thumbnail_path, cached_full_text, 
            semantic_data, created_at, deleted, page_count_virt, type_tags,
            sender, doc_date, amount, tags
        FROM virtual_documents
        """
        if not include_deleted:
            sql += " WHERE deleted = 0"

        cursor = self.conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [VirtualDocument.from_row(row) for row in rows]
