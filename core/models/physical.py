"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/models/physical.py
Version:        1.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Data model for physical files stored in the immutable document 
                vault. Tracks file metadata, perceptual hashes, and raw OCR 
                content per page.
------------------------------------------------------------------------------
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass
class PhysicalFile:
    """
    Represents a physical file on disk (Immutable Store).
    Maps to 'physical_files' table columns.
    """
    uuid: str
    original_filename: str
    file_path: str
    phash: Optional[str] = None
    file_size: int = 0
    page_count_phys: int = 0
    raw_ocr_data: Dict[str, str] = field(default_factory=dict)  # Map "page_num" -> "text"
    created_at: Optional[str] = None  # ISO format string

    @classmethod
    def from_row(cls, row: Tuple[Any, ...]) -> 'PhysicalFile':
        """
        Parses a database row into a PhysicalFile object.

        Args:
            row: A tuple containing database column values.
                 Expected indices: 0:uuid, 1:phash, 2:file_path, 
                 3:original_filename, 4:file_size, 5:raw_ocr_data, 
                 6:created_at, 7:page_count_phys.

        Returns:
            A populated PhysicalFile instance.
        """
        ocr_data: Dict[str, str] = {}
        if len(row) > 5 and row[5]:
            try:
                ocr_data = json.loads(row[5])
            except (json.JSONDecodeError, TypeError):
                pass

        return cls(
            uuid=str(row[0]),
            phash=str(row[1]) if row[1] else None,
            file_path=str(row[2]),
            original_filename=str(row[3]),
            file_size=int(row[4]) if row[4] else 0,
            raw_ocr_data=ocr_data,
            created_at=str(row[6]) if row[6] else None,
            page_count_phys=int(row[7]) if len(row) > 7 and row[7] else 0
        )
