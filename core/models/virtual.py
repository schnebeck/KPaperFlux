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
    Maps to 'semantic_entities' table.
    """
    entity_uuid: str
    source_mapping: List[SourceReference] = field(default_factory=list)
    type_tags: List[str] = field(default_factory=list)
    
    # Semantic Data
    semantic_data: Dict[str, Any] = field(default_factory=dict)
    
    # Core CDM Fields (Fast Access)
    doc_date: Optional[date] = None
    sender_name: Optional[str] = None
    doc_type: str = "unknown"
    
    # Meta
    status: str = "NEW"
    created_at: Optional[str] = None
    deleted: bool = False
    
    # Runtime only (not stored directly in entity table, but assembled)
    # text_content: str = "" 
    
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
    
    def get_tags_json(self) -> str:
        return json.dumps(self.type_tags)
        
    @classmethod
    def from_row(cls, row: tuple) -> 'VirtualDocument':
        """
        Parse from semantic_entities row.
        Row expected: entity_uuid, source_mapping, type_tags, semantic_data, doc_date, sender_name, doc_type, status, created_at
        """
        # We need to know the schema index exactly.
        # This is a helper, usually caller extracts columns.
        pass
