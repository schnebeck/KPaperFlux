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
    uuid: str
    original_filename: str
    file_path: str
    phash: Optional[str] = None
    file_size: int = 0
    page_count_phys: int = 0
    raw_ocr_data: Optional[Dict[str, str]] = field(default_factory=dict) # Map page_num -> text
    created_at: Optional[str] = None # ISO format

    @classmethod
    def from_row(cls, row: tuple) -> 'PhysicalFile':
        """Parse database row into object."""
        # Row expected index-wise: 
        # 0:uuid, 1:phash, 2:file_path, 3:original_filename, 4:file_size, 
        # 5:raw_ocr_data, 6:created_at, 7:page_count_phys
        
        ocr_data = {}
        if row[5]:
            try:
                ocr_data = json.loads(row[5])
            except:
                pass
                
        return cls(
            uuid=row[0],
            phash=row[1],
            file_path=row[2],
            original_filename=row[3],
            file_size=row[4] or 0,
            raw_ocr_data=ocr_data,
            created_at=row[6],
            page_count_phys=row[7] or 0
        )
