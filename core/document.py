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
    sender_address: Optional[str] = None
    iban: Optional[str] = None
    phone: Optional[str] = None
    tags: Optional[str] = None
    
    # Duplicate detection fingerprints
    phash: Optional[str] = None
    text_content: Optional[str] = None
