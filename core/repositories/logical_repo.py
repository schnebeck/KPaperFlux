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

from core.logger import get_logger
logger = get_logger("repositories.logical")

from decimal import Decimal
from pydantic import BaseModel


class EnhancedJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder to handle datetime, date, Decimal, and Pydantic models.
    Ensures that semantic data remains serializable even with complex types.
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, BaseModel):
            return obj.model_dump()
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
        INSERT INTO virtual_documents (
            uuid, source_mapping, status, export_filename, 
            last_used, last_processed_at, is_immutable, thumbnail_path, 
            cached_full_text, semantic_data, created_at, deleted, 
            deleted_at, locked_at, exported_at,
            page_count_virt, type_tags, tags, pdf_class,
            archived, storage_location, ai_confidence, process_id
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT(uuid) DO UPDATE SET
            source_mapping=excluded.source_mapping,
            status=excluded.status,
            export_filename=excluded.export_filename,
            last_used=excluded.last_used,
            last_processed_at=excluded.last_processed_at,
            is_immutable=excluded.is_immutable,
            thumbnail_path=excluded.thumbnail_path,
            cached_full_text=excluded.cached_full_text,
            semantic_data=excluded.semantic_data,
            created_at=excluded.created_at,
            deleted=excluded.deleted,
            deleted_at=excluded.deleted_at,
            locked_at=excluded.locked_at,
            exported_at=excluded.exported_at,
            page_count_virt=excluded.page_count_virt,
            type_tags=excluded.type_tags,
            tags=excluded.tags,
            pdf_class=excluded.pdf_class,
            archived=excluded.archived,
            storage_location=excluded.storage_location,
            ai_confidence=excluded.ai_confidence,
            process_id=excluded.process_id
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
            doc.deleted_at,
            doc.locked_at,
            doc.exported_at,
            total_pages,
            type_tags_json,
            tags_json,
            doc.pdf_class,
            int(doc.archived),
            doc.storage_location,
            doc.ai_confidence,
            doc.process_id
        )

        try:
            with self.conn:
                self.conn.execute(sql, values)
            return True
        except Exception as e:
            logger.error(f"Save error: {e}")
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
            tags, deleted_at, locked_at, exported_at, pdf_class,
            archived, storage_location, ai_confidence, process_id
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
        sql = """
        SELECT
            uuid, source_mapping, status, export_filename, last_used,
            last_processed_at, is_immutable, thumbnail_path, cached_full_text,
            semantic_data, created_at, deleted, page_count_virt, type_tags,
            tags, deleted_at, locked_at, exported_at, pdf_class,
            archived, storage_location, ai_confidence, process_id
        FROM virtual_documents
        WHERE EXISTS (
            SELECT 1 FROM json_each(source_mapping)
            WHERE json_extract(value, '$.file_uuid') = ?
        )
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (file_uuid,))
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
            logger.error(f"Delete error: {e}")
            return False

    def _mark_flag(self, uuid: str, flag_col: str, timestamp_col: str, value: bool) -> bool:
        """Sets a boolean flag column and its corresponding timestamp on a virtual document."""
        now = datetime.now().isoformat() if value else None
        sql = f"UPDATE virtual_documents SET {flag_col} = ?, {timestamp_col} = ? WHERE uuid = ?"
        try:
            with self.conn:
                cursor = self.conn.execute(sql, (int(value), now, uuid))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"mark_{flag_col} error: {e}")
            return False

    def mark_deleted(self, uuid: str, is_deleted: bool = True) -> bool:
        """Soft-deletes or restores a virtual document."""
        return self._mark_flag(uuid, "deleted", "deleted_at", is_deleted)

    def mark_archived(self, uuid: str, is_archived: bool = True) -> bool:
        """Soft-archives or restores a virtual document."""
        return self._mark_flag(uuid, "archived", "exported_at", is_archived)

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
            tags, deleted_at, locked_at, exported_at, pdf_class,
            archived, storage_location, ai_confidence, process_id
        FROM virtual_documents
        """
        if not include_deleted:
            sql += " WHERE deleted = 0"

        cursor = self.conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [VirtualDocument.from_row(row) for row in rows]
