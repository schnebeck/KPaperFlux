import json
import uuid
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator
from core.models.semantic import SemanticExtraction

# --- Central Logging Setup ---
logger = logging.getLogger("KPaperFlux.Model")


class SourceReference(BaseModel):
    """
    Points to a specific segment within a physical file.
    Part of the source_mapping for a VirtualDocument.
    """
    model_config = ConfigDict(populate_by_name=True)

    file_uuid: str
    pages: List[int]
    rotation: int = 0


class VirtualPage(BaseModel):
    """
    Represents a single logical page in a VirtualDocument.
    Assembled from a physical source at runtime.
    """
    model_config = ConfigDict(populate_by_name=True)

    page_number: int  # Logical page number (1-based)
    text_content: str  # Extracted and normalized text
    source_file_uuid: str  # The physical file ID it originates from
    source_page_index: int  # The 1-based physical page index
    image_path: Optional[str] = None  # Path to a rendered image preview


class VirtualDocument(BaseModel):
    """
    Core Domain Model for a Logical Document (VirtualDocument).
    Unifies the previous Document and VirtualDocument models.
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True, validate_assignment=True)



    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_filename: Optional[str] = None
    source_mapping: List[SourceReference] = Field(default_factory=list)
    status: str = "NEW"
    export_filename: Optional[str] = None
    last_used: Optional[str] = None
    is_immutable: bool = False
    locked: bool = False  # Alias for is_immutable
    thumbnail_path: Optional[str] = None
    cached_full_text: str = ""
    
    # Metadata & Tags
    type_tags: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    
    # Semantic Data (V2)
    semantic_data: Optional[SemanticExtraction] = None
    extra_data: Optional[Dict[str, Any]] = None
    
    # Lifecycle
    created_at: Optional[str] = Field(default_factory=lambda: datetime.now().isoformat())
    last_processed_at: Optional[str] = None
    deleted: bool = False
    
    # System Managed Dates
    deleted_at: Optional[str] = None
    locked_at: Optional[str] = None
    exported_at: Optional[str] = None

    # Runtime / Technical
    file_path: Optional[str] = None
    page_count: Optional[int] = None

    page_count_virt: int = 0
    phash: Optional[str] = None
    text_content: Optional[str] = None

    def add_source(self, file_uuid: str, pages: List[int], rotation: int = 0) -> None:
        """Appends a physical file segment."""
        self.source_mapping.append(SourceReference(file_uuid=file_uuid, pages=pages, rotation=rotation))

    def resolve_content(self, loader_callback: Callable[[str], Any]) -> str:
        """Lazy resolution of full text content."""
        full_text_parts: List[str] = []
        for ref in self.source_mapping:
            phys_data = loader_callback(ref.file_uuid)
            if not phys_data:
                continue

            # Handle both object and dict
            raw_data = getattr(phys_data, 'raw_ocr_data', None)
            if raw_data is None and isinstance(phys_data, dict):
                raw_data = phys_data.get('raw_ocr_data')
            
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError):
                    raw_data = {}

            if isinstance(raw_data, dict):
                for page_idx in ref.pages:
                    full_text_parts.append(raw_data.get(str(page_idx), ""))

        self.cached_full_text = "\n".join(full_text_parts)
        return self.cached_full_text

    def to_source_mapping_json(self) -> str:
        """Serializes mapping to JSON string."""
        return json.dumps([s.model_dump() for s in self.source_mapping])

    @property
    def effective_type(self) -> str:
        """Helper to get the primary classification."""
        return self.type_tags[0] if self.type_tags else "OTHER"

    @property
    def total_amount(self) -> Optional[Union[Decimal, float]]:
        """Helper to access financial totals across different semantic bodies."""
        if self.semantic_data:
            return self.semantic_data.get_financial_value("amount")
        return None

    @property
    def sender_name(self) -> Optional[str]:
        """Human readable sender name/company."""
        return self.semantic_data.sender_summary if self.semantic_data else None

    @property
    def recipient_name(self) -> Optional[str]:
        """Human readable recipient name/company."""
        return self.semantic_data.recipient_summary if self.semantic_data else None

    @property
    def doc_date(self) -> Optional[str]:
        """Normalized document date."""
        return self.semantic_data.document_date if self.semantic_data else None

    @property
    def doc_number(self) -> Optional[str]:
        """Extracted document/invoice number."""
        return self.semantic_data.document_number if self.semantic_data else None



    @property
    def total_gross(self) -> Optional[Union[Decimal, float]]:
        return self.semantic_data.get_financial_value("total_gross") if self.semantic_data else None

    @property
    def total_net(self) -> Optional[Union[Decimal, float]]:
        return self.semantic_data.get_financial_value("total_net") if self.semantic_data else None

    @property
    def total_tax(self) -> Optional[Union[Decimal, float]]:
        return self.semantic_data.get_financial_value("total_tax") if self.semantic_data else None

    @property
    def currency(self) -> Optional[str]:
        return self.semantic_data.get_financial_value("currency") if self.semantic_data else None

    @property
    def iban(self) -> Optional[str]:
        if self.semantic_data and self.semantic_data.meta_header and self.semantic_data.meta_header.sender:
            return self.semantic_data.meta_header.sender.iban
        return None


    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: Any) -> List[str]:
        """Normalizes tag input from various formats."""
        if v is None: return []
        if isinstance(v, str):
            if v.startswith("["):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list): return [str(t) for t in parsed]
                except json.JSONDecodeError:
                    pass # Not a JSON list, treat as comma-separated string
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, list): return [str(t) for t in v]
        return []

    @field_validator("type_tags", mode="before")
    @classmethod
    def normalize_list_fields(cls, v: Any) -> List[str]:
        """Normalizes list fields like type_tags."""
        if v is None: return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list): return [str(t) for t in parsed]
            except json.JSONDecodeError:
                pass # Not a JSON, treat as raw string
            return [v]
        if isinstance(v, list): return [str(t) for t in v if t]
        return []

    @classmethod
    def from_row(cls, row: Union[Tuple[Any, ...], Dict[str, Any]]) -> 'VirtualDocument':
        """
        Parses a database row and hydrates a VirtualDocument instance.
        Supports both tuple results (from LogicalRepository) and dictionary-like rows.
        """
        if not row:
            return None

        # Convert tuple to dict if needed (Mapping indexes to LogicalRepository.get_by_uuid SQL)
        if isinstance(row, (tuple, list)) and not hasattr(row, 'keys'):
            data = {
                "uuid": row[0],
                "source_mapping": row[1],
                "status": row[2],
                "export_filename": row[3],
                "last_used": row[4],
                "last_processed_at": row[5],
                "is_immutable": bool(row[6]),
                "thumbnail_path": row[7],
                "cached_full_text": row[8],
                "semantic_data": row[9],
                "created_at": row[10],
                "deleted": bool(row[11]),
                "page_count_virt": row[12],
                "type_tags": row[13],
                "tags": row[14],
                "deleted_at": row[15],
                "locked_at": row[16],
                "exported_at": row[17]
            }
        elif hasattr(row, 'keys'): # Handle sqlite3.Row or dict
            data = dict(row)
        else:
            data = row

        # Handle JSON strings
        def safe_json(val, default):
            if isinstance(val, str) and (val.startswith('{') or val.startswith('[')):
                try:
                    return json.loads(val)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON corruption in DB for doc {data.get('uuid')}: {e}")
                    return default
            return val or default

        source_mapping = safe_json(data.get("source_mapping"), [])
        semantic_data = safe_json(data.get("semantic_data"), {})
        type_tags = safe_json(data.get("type_tags"), [])
        tags = safe_json(data.get("tags"), [])

        return cls(
            uuid=data["uuid"],
            original_filename=data.get("export_filename"),
            source_mapping=source_mapping,
            status=data.get("status", "NEW"),
            export_filename=data.get("export_filename"),
            last_used=data.get("last_used"),
            is_immutable=data.get("is_immutable", False),
            locked_at=data.get("locked_at"),
            thumbnail_path=data.get("thumbnail_path"),
            cached_full_text=data.get("cached_full_text", ""),
            type_tags=type_tags,
            tags=tags,
            semantic_data=semantic_data,
            created_at=data.get("created_at"),
            last_processed_at=data.get("last_processed_at"),
            deleted=data.get("deleted", False),
            deleted_at=data.get("deleted_at"),
            exported_at=data.get("exported_at"),
            page_count_virt=data.get("page_count_virt", 0)
        )
