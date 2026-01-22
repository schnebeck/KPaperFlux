import uuid
from typing import Optional, List, Union
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
import json

class Document(BaseModel):
    """
    Core domain model for a document in KPaperFlux.
    Uses Pydantic for validation and serialization.
    """
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_filename: str
    
    # Metadata extracted by AI or user
    doc_date: Optional[date] = None
    sender: Optional[str] = None
    amount: Optional[Decimal] = None
    
    # Phase 45: Extended Finance
    gross_amount: Optional[Decimal] = None
    postage: Optional[Decimal] = None
    packaging: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    currency: Optional[str] = None

    doc_type: Optional[Union[List[str], str]] = Field(default_factory=list)
    locked: bool = False
    deleted: bool = False # Phase 90: Trash Bin
    
    @field_validator('doc_type')
    @classmethod
    def normalize_doc_type(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            # Attempt to parse JSON list (e.g. '["Invoice"]')
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except:
                pass
            # Fallback: Treat as single string -> list
            return [v]
        return v
    
    @field_validator('amount', 'gross_amount', 'postage', 'packaging', 'tax_rate', mode='before')
    @classmethod
    def normalize_decimals(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float, Decimal)):
            return v
        if isinstance(v, str):
            # Handle localized strings "68,50" -> "68.50"
            v = v.replace(",", ".")
            # Handle currency symbols if mistakenly included
            v = v.replace("€", "").replace("$", "").strip()
            # Handle empty string
            if not v:
                return None
            try:
                return Decimal(v)
            except:
                return None
        return v
    
    # Extended Metadata (Phase 3)
    # sender_address might be used as "raw" address or specific fields below
    sender_address: Optional[str] = None 
    iban: Optional[str] = None
    phone: Optional[str] = None
    tags: Optional[str] = None
    
    # Phase 8: Extended Details
    recipient_company: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_street: Optional[str] = None
    recipient_zip: Optional[str] = None
    recipient_city: Optional[str] = None
    recipient_country: Optional[str] = None
    
    sender_company: Optional[str] = None
    sender_name: Optional[str] = None
    sender_street: Optional[str] = None
    sender_zip: Optional[str] = None
    sender_city: Optional[str] = None
    sender_country: Optional[str] = None

    # Transient / Runtime (not stored in DB metadata table usually)
    file_path: Optional[str] = None
    export_filename: Optional[str] = None
    
    page_count: Optional[int] = None
    created_at: Optional[str] = None # ISO format
    last_processed_at: Optional[str] = None # ISO format
    
    # Duplicate detection fingerprints
    phash: Optional[str] = None
    text_content: Optional[str] = None
    

    # Phase 29: Dynamic Data
    extra_data: Optional[dict] = None
    
    # Phase 70: Semantic Document Structure
    semantic_data: Optional[dict] = None

    # Phase 80: Indexer / Virtual Columns (Read-only, populated from DB)
    v_sender: Optional[str] = None
    v_doc_date: Optional[str] = None # ISO Date stored as String in DB (Generated Column)
    v_amount: Optional[float] = None # REAL in DB
