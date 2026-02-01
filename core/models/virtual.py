"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/models/virtual.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Data models for logical virtual documents. Represents the 
                business-level entity that can span multiple physical files 
                and pages. Includes metadata tracking and content resolution.
------------------------------------------------------------------------------
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class SourceReference:
    """
    Points to a specific segment within a physical file.
    Part of the source_mapping for a VirtualDocument.
    """
    file_uuid: str
    pages: List[int]  # 1-based page indices in the physical file
    rotation: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the reference to a dictionary."""
        return asdict(self)


@dataclass
class VirtualPage:
    """
    Represents a single logical page in a VirtualDocument.
    Assembled from a physical source at runtime.
    """
    page_number: int  # Logical page number (1-based)
    text_content: str  # Extracted and normalized text
    source_file_uuid: str  # The physical file ID it originates from
    source_page_index: int  # The 1-based physical page index
    image_path: Optional[str] = None  # Path to a rendered image preview


@dataclass
class VirtualDocument:
    """
    Represents the logical business document (Mutable Entity).
    Maps to 'virtual_documents' table columns.
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
    type_tags: List[str] = field(default_factory=list)  # System-defined doc types
    tags: List[str] = field(default_factory=list)  # User-defined tags

    # System Managed Dates
    deleted_at: Optional[str] = None
    locked_at: Optional[str] = None
    exported_at: Optional[str] = None

    # Filter Columns (Cached metadata for fast filtering/sorting)

    # Runtime properties
    page_count_virt: int = 0

    def add_source(self, file_uuid: str, pages: List[int], rotation: int = 0) -> None:
        """
        Appends a physical file segment to this virtual document.

        Args:
            file_uuid: The physical file UUID.
            pages: List of page numbers (1-based).
            rotation: Visual rotation applied to these pages.
        """
        self.source_mapping.append(SourceReference(file_uuid, pages, rotation))

    def resolve_content(self, loader_callback: Callable[[str], Any]) -> str:
        """
        Lazy resolution of full text content by iterating through source mapping.

        Args:
            loader_callback: A function that retrieves physical file data by UUID.

        Returns:
            The joined text content of all referenced pages.
        """
        full_text_parts: List[str] = []
        for ref in self.source_mapping:
            phys_data = loader_callback(ref.file_uuid)
            if not phys_data:
                continue

            # Handle both object attributes and direct dictionary access
            raw_data = getattr(phys_data, 'raw_ocr_data', phys_data)
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError):
                    raw_data = {}

            if isinstance(raw_data, dict):
                for page_idx in ref.pages:
                    full_text_parts.append(raw_data.get(str(page_idx), ""))

        return "\n".join(full_text_parts)

    def to_source_mapping_json(self) -> str:
        """Serializes the source mapping list to a JSON string."""
        return json.dumps([s.to_dict() for s in self.source_mapping])

    @classmethod
    def from_row(cls, row: Tuple[Any, ...]) -> 'VirtualDocument':
        """
        Parses a database row from the virtual_documents table.

        Args:
            row: Generic tuple from SQLite query results.

        Returns:
            A populated VirtualDocument instance.
        """
        source_mapping = []
        if len(row) > 1 and row[1]:
            try:
                data = json.loads(row[1])
                source_mapping = [SourceReference(**r) for r in data]
            except (json.JSONDecodeError, TypeError):
                pass

        semantic_data = None
        if len(row) > 9 and row[9]:
            try:
                semantic_data = json.loads(row[9])
            except (json.JSONDecodeError, TypeError):
                pass

        type_tags = []
        if len(row) > 13 and row[13]:
            try:
                type_tags = json.loads(row[13])
            except (json.JSONDecodeError, TypeError):
                pass

        tags = []
        if len(row) > 17 and row[17]:
            try:
                tags = json.loads(row[17])
            except (json.JSONDecodeError, TypeError):
                pass

        # Helper for safer JSON loading
        def safe_json(val):
            if not val: return None
            try: return json.loads(val)
            except: return None

        raw_source = safe_json(row["source_mapping"]) or []
        source_mapping = []
        for r in raw_source:
            if isinstance(r, dict):
                source_mapping.append(SourceReference(**r))
            else:
                source_mapping.append(r)

        return cls(
            uuid=str(row["uuid"]),
            source_mapping=source_mapping,
            status=str(row["status"]),
            export_filename=str(row["export_filename"]) if row["export_filename"] else None,
            last_used=str(row["last_used"]) if row["last_used"] else None,
            last_processed_at=str(row["last_processed_at"]) if row["last_processed_at"] else None,
            is_immutable=bool(row["is_immutable"]),
            thumbnail_path=str(row["thumbnail_path"]) if "thumbnail_path" in row.keys() and row["thumbnail_path"] else None,
            cached_full_text=str(row["cached_full_text"]) if "cached_full_text" in row.keys() and row["cached_full_text"] else "",
            semantic_data=safe_json(row["semantic_data"] if "semantic_data" in row.keys() else None),
            created_at=str(row["created_at"]) if "created_at" in row.keys() and row["created_at"] else None,
            deleted=bool(row["deleted"]) if "deleted" in row.keys() else False,
            page_count_virt=int(row["page_count_virt"]) if "page_count_virt" in row.keys() and row["page_count_virt"] else 0,
            type_tags=safe_json(row["type_tags"] if "type_tags" in row.keys() else None) or [],
            tags=safe_json(row["tags"] if "tags" in row.keys() else None) or [],
            deleted_at=str(row["deleted_at"]) if "deleted_at" in row.keys() and row["deleted_at"] else None,
            locked_at=str(row["locked_at"]) if "locked_at" in row.keys() and row["locked_at"] else None,
            exported_at=str(row["exported_at"]) if "exported_at" in row.keys() and row["exported_at"] else None,
        )
