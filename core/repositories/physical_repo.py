from typing import Optional
import json
import sqlite3
from .base import BaseRepository
from core.models.physical import PhysicalFile

class PhysicalRepository(BaseRepository):
    """
    Manages access to 'physical_files' table.
    """
    
    def save(self, file: PhysicalFile) -> int:
        """
        Insert or Update a physical file record.
        """
        sql = """
        INSERT OR REPLACE INTO physical_files (
            file_uuid, original_filename, file_path, phash, 
            file_size, page_count, raw_ocr_data, ref_count, created_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """
        
        ocr_json = json.dumps(file.raw_ocr_data) if file.raw_ocr_data else None
        
        values = (
            file.file_uuid,
            file.original_filename,
            file.file_path,
            file.phash,
            file.file_size,
            file.page_count,
            ocr_json,
            file.ref_count,
            file.created_at
        )
        
        with self.conn:
            cursor = self.conn.execute(sql, values)
            if file.id is None:
                file.id = cursor.lastrowid
            return cursor.lastrowid

    def get_by_uuid(self, params: str) -> Optional[PhysicalFile]:
        """Fetch by UUID."""
        # Using string params directly since method signature usually implies it
        uuid = params
        sql = "SELECT id, file_uuid, original_filename, file_path, phash, file_size, page_count, raw_ocr_data, ref_count, created_at FROM physical_files WHERE file_uuid = ?"
        cursor = self.conn.cursor()
        cursor.execute(sql, (uuid,))
        row = cursor.fetchone()
        if row:
            return PhysicalFile.from_row(row)
        return None

    def get_by_phash(self, phash: str) -> Optional[PhysicalFile]:
        """Fetch by perceptual hash (deduplication)."""
        sql = "SELECT id, file_uuid, original_filename, file_path, phash, file_size, page_count, raw_ocr_data, ref_count, created_at FROM physical_files WHERE phash = ?"
        cursor = self.conn.cursor()
        cursor.execute(sql, (phash,))
        row = cursor.fetchone()
        if row:
            return PhysicalFile.from_row(row)
        return None
        
    def increment_ref_count(self, file_uuid: str):
        """Atomic increment."""
        sql = "UPDATE physical_files SET ref_count = ref_count + 1 WHERE file_uuid = ?"
        with self.conn:
            self.conn.execute(sql, (file_uuid,))
