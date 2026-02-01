"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/repositories/physical_repo.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Repository for managing persistence of PhysicalFile models in 
                the SQLite database. Handles CRUD operations for immutable 
                source files, phash lookups, and OCR data storage.
------------------------------------------------------------------------------
"""

import json
from typing import Any, List, Optional, Tuple

from core.models.physical import PhysicalFile

from .base import BaseRepository


class PhysicalRepository(BaseRepository):
    """
    Manages access to the 'physical_files' table, providing persistence
    for physical source documents.
    """

    def save(self, file: PhysicalFile) -> bool:
        """
        Inserts or replaces a physical file record in the database.

        Args:
            file: The PhysicalFile instance to persist.

        Returns:
            True if the operation was successful.
        """
        sql = """
        INSERT OR REPLACE INTO physical_files (
            uuid, phash, file_path, original_filename, 
            file_size, page_count_phys, raw_ocr_data, created_at,
            ref_count
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """

        ocr_json = json.dumps(file.raw_ocr_data) if file.raw_ocr_data else None

        values = (
            file.uuid,
            file.phash,
            file.file_path,
            file.original_filename,
            file.file_size,
            file.page_count_phys,
            ocr_json,
            file.created_at,
            file.ref_count
        )

        try:
            with self.conn:
                self.conn.execute(sql, values)
            return True
        except Exception as e:
            print(f"[PhysicalRepo] Save error: {e}")
            return False

    def get_by_uuid(self, uuid: str) -> Optional[PhysicalFile]:
        """
        Retrieves a physical file record by its unique UUID.

        Args:
            uuid: The unique identifier of the physical file.

        Returns:
            A PhysicalFile instance if found, else None.
        """
        sql = """
        SELECT uuid, phash, file_path, original_filename, file_size, 
               raw_ocr_data, created_at, page_count_phys, ref_count
        FROM physical_files 
        WHERE uuid = ?
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (uuid,))
        row = cursor.fetchone()
        if row:
            return PhysicalFile.from_row(row)
        return None

    def get_by_phash(self, phash: str) -> Optional[PhysicalFile]:
        """
        Retrieves a physical file by its perceptual hash (deduplication check).

        Args:
            phash: The perceptual hash string.

        Returns:
            A PhysicalFile instance if found, else None.
        """
        sql = """
        SELECT uuid, phash, file_path, original_filename, file_size, 
               raw_ocr_data, created_at, page_count_phys, ref_count
        FROM physical_files 
        WHERE phash = ?
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (phash,))
        row = cursor.fetchone()
        if row:
            return PhysicalFile.from_row(row)
        return None

    def get_all(self) -> List[PhysicalFile]:
        """
        Fetches all physical file records from the database.

        Returns:
            A list of PhysicalFile instances.
        """
        sql = """
        SELECT uuid, phash, file_path, original_filename, file_size, 
               raw_ocr_data, created_at, page_count_phys, ref_count
        FROM physical_files
        """
        cursor = self.conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [PhysicalFile.from_row(row) for row in rows]

    def delete(self, uuid: str) -> bool:
        """
        Hard deletes a physical file record from the repository.

        Args:
            uuid: The ID of the record to remove.

        Returns:
            True if the deletion was executed without error.
        """
        try:
            with self.conn:
                self.conn.execute("DELETE FROM physical_files WHERE uuid = ?", (uuid,))
            return True
        except Exception as e:
            print(f"[PhysicalRepo] Delete error: {e}")
            return False
