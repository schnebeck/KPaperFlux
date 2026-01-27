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
            uuid, phash, file_path, original_filename, 
            file_size, page_count_phys, raw_ocr_data, created_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?
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
            file.created_at
        )
        
        with self.conn:
            self.conn.execute(sql, values)
            return 1 # Simplified return

    def get_by_uuid(self, uuid: str) -> Optional[PhysicalFile]:
        """Fetch by UUID."""
        # Order: uuid, phash, file_path, original_filename, file_size, raw_ocr_data, created_at, page_count_phys
        sql = "SELECT uuid, phash, file_path, original_filename, file_size, raw_ocr_data, created_at, page_count_phys FROM physical_files WHERE uuid = ?"
        cursor = self.conn.cursor()
        cursor.execute(sql, (uuid,))
        row = cursor.fetchone()
        if row:
            return PhysicalFile.from_row(row)
        return None

    def get_by_phash(self, phash: str) -> Optional[PhysicalFile]:
        """Fetch by perceptual hash (deduplication)."""
        sql = "SELECT uuid, phash, file_path, original_filename, file_size, raw_ocr_data, created_at, page_count_phys FROM physical_files WHERE phash = ?"
        cursor = self.conn.cursor()
        cursor.execute(sql, (phash,))
        row = cursor.fetchone()
        if row:
            return PhysicalFile.from_row(row)
        return None
        
    def increment_ref_count(self, uuid: str):
        """Atomic increment? (No longer in schema, for reference only)"""
        pass

    def get_all(self) -> list[PhysicalFile]:
        """Fetch all physical files."""
        sql = "SELECT uuid, phash, file_path, original_filename, file_size, raw_ocr_data, created_at, page_count_phys FROM physical_files"
        cursor = self.conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [PhysicalFile.from_row(row) for row in rows]

    def delete(self, uuid: str):
        """Hard delete of a physical file record."""
        with self.conn:
             self.conn.execute("DELETE FROM physical_files WHERE uuid = ?", (uuid,))
