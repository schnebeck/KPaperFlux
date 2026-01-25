from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import date
import json

@dataclass
class SourceReference:
    """
    Points to a specific section of a physical file.
    """
    file_uuid: str
    pages: List[int] # 1-based page indices
    rotation: int = 0
    
    def to_dict(self):
        return asdict(self)

@dataclass
class VirtualPage:
    """
    Represents a single page in a VirtualDocument.
    It is assembled from a physical source at runtime.
    """
    page_number: int            # Logical page number (1-based)
    text_content: str           # Extracted text
    source_file_uuid: str       # Physical file ID
    source_page_index: int      # Physical page index (1-based)
    image_path: Optional[str] = None # Path to rendered image (optional)

@dataclass
class VirtualDocument:
    """
    Represents the logical business document (Mutable Entity).
    Maps to 'virtual_documents' table.
    """
    uuid: str
    source_mapping: List[SourceReference] = field(default_factory=list)
    status: str = "NEW"
    export_filename: Optional[str] = None
    last_used: Optional[str] = None
    is_immutable: bool = False
    thumbnail_path: Optional[str] = None
    cached_full_text: str = ""
    semantic_data: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    last_processed_at: Optional[str] = None
    deleted: bool = False
    
    # Runtime properties (SQLite Generated)
    page_count_virt: int = 0
    
    def add_source(self, file_uuid: str, pages: List[int], rotation: int = 0):
        self.source_mapping.append(SourceReference(file_uuid, pages, rotation))
        
    def resolve_content(self, loader_callback) -> str:
        """
        Lazy load text content using the provided callback.
        :param loader_callback: Function that accepts (file_uuid) and returns PhysicalFile/Dict with 'raw_ocr_data'.
        """
        full_text_parts = []
        for ref in self.source_mapping:
            phys_data = loader_callback(ref.file_uuid)
            if not phys_data:
                continue
            
            # abstract access to raw_ocr_data (could be dict or object)
            raw_data = getattr(phys_data, 'raw_ocr_data', phys_data)
            if isinstance(raw_data, str):
                 try: raw_data = json.loads(raw_data)
                 except: raw_data = {}
            
            if isinstance(raw_data, dict):
                for page_idx in ref.pages:
                    full_text_parts.append(raw_data.get(str(page_idx), ""))
        
        return "\n".join(full_text_parts)

    def to_source_mapping(self) -> str:
        """Serialize source mapping to JSON for database storage."""
        return json.dumps([s.to_dict() for s in self.source_mapping])
        
    def get_mapping_json(self) -> str:
        return self.to_source_mapping()
    
    @classmethod
    def from_row(cls, row: tuple) -> 'VirtualDocument':
        """
        Parse from virtual_documents row.
        Indices: 0:uuid, 1:source_mapping, 2:status, 3:export_filename, 4:last_used, 
                 5:last_processed_at, 6:is_immutable, 7:thumbnail_path, 8:cached_full_text,
                 9:semantic_data, 10:created_at, 11:deleted, 12:page_count_virt
        """
        source_mapping = []
        if row[1]:
            try:
                data = json.loads(row[1])
                source_mapping = [SourceReference(**r) for r in data]
            except:
                pass
                
        semantic_data = None
        if row[9]:
             try: semantic_data = json.loads(row[9])
             except: pass
             
        return cls(
            uuid=row[0],
            source_mapping=source_mapping,
            status=row[2],
            export_filename=row[3],
            last_used=row[4],
            last_processed_at=row[5],
            is_immutable=bool(row[6]),
            thumbnail_path=row[7],
            cached_full_text=row[8] or "",
            semantic_data=semantic_data,
            created_at=row[10],
            deleted=bool(row[11]),
            page_count_virt=row[12] or 0
        )
