import uuid
from typing import Optional
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field

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
    doc_type: Optional[str] = None
    
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
    
    page_count: Optional[int] = None
    created_at: Optional[str] = None # ISO format
    
    # Duplicate detection fingerprints
    phash: Optional[str] = None
    text_content: Optional[str] = None
    
    # Phase 29: Dynamic Data
    extra_data: Optional[dict] = None
