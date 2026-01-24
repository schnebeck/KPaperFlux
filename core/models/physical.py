from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
import json

@dataclass
class PhysicalFile:
    """
    Represents a physical file on disk (Immutable Store).
    Maps to 'physical_files' table.
    """
    file_uuid: str
    original_filename: str
    file_path: str
    phash: Optional[str] = None
    file_size: int = 0
    page_count: int = 0
    raw_ocr_data: Optional[Dict[str, str]] = field(default_factory=dict) # Map page_num -> text
    ref_count: int = 0
    created_at: Optional[str] = None # ISO format
    id: Optional[int] = None

    @classmethod
    def from_row(cls, row: tuple) -> 'PhysicalFile':
        """Parse database row into object."""
        # Row order based on SELECT * query or specific mapping
        # Assuming: id, file_uuid, original_filename, file_path, phash, file_size, page_count, raw_ocr_data, ref_count, created_at
        
        ocr_data = {}
        if row[7]:
            try:
                ocr_data = json.loads(row[7])
            except:
                pass
                
        return cls(
            id=row[0],
            file_uuid=row[1],
            original_filename=row[2],
            file_path=row[3],
            phash=row[4],
            file_size=row[5] or 0,
            page_count=row[6] or 0,
            raw_ocr_data=ocr_data,
            ref_count=row[8] or 0,
            created_at=row[9]
        )
