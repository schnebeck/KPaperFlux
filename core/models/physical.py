"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/models/physical.py
Version:        2.0.0
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
    ref_count: int = 0

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
        if "raw_ocr_data" in row.keys() and row["raw_ocr_data"]:
            try:
                ocr_data = json.loads(row["raw_ocr_data"])
            except (json.JSONDecodeError, TypeError):
                pass

        return cls(
            uuid=str(row["uuid"]),
            phash=str(row["phash"]) if row["phash"] else None,
            file_path=str(row["file_path"]),
            original_filename=str(row["original_filename"]),
            file_size=int(row["file_size"]) if row["file_size"] else 0,
            raw_ocr_data=ocr_data,
            created_at=str(row["created_at"]) if row["created_at"] else None,
            page_count_phys=int(row["page_count_phys"]) if "page_count_phys" in row.keys() and row["page_count_phys"] else 0,
            ref_count=int(row["ref_count"]) if "ref_count" in row.keys() else 0
        )
