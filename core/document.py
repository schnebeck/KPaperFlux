"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/document.py
Version:        1.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Core domain model for a document in KPaperFlux. Defines the
                schema for document metadata, validation rules, and
                de/serialization using Pydantic.
------------------------------------------------------------------------------
"""

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class Document(BaseModel):
    """
    Core domain model for a document in KPaperFlux.
    Uses Pydantic for validation and serialization.
    """

    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_filename: Optional[str] = None
    status: str = "NEW"
    cached_full_text: Optional[str] = None

    # Metadata extracted by AI or user
    doc_date: Optional[Union[date, str]] = None
    sender: Optional[str] = None
    amount: Optional[Decimal] = None

    # Extended Finance Data
    gross_amount: Optional[Decimal] = None
    postage: Optional[Decimal] = None
    packaging: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    currency: Optional[str] = None

    doc_type: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    type_tags: List[str] = Field(default_factory=list)

    locked: bool = False
    deleted: bool = False

    # Extended Metadata
    sender_address: Optional[str] = None
    iban: Optional[str] = None
    phone: Optional[str] = None

    # Recipient Details
    recipient_company: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_street: Optional[str] = None
    recipient_zip: Optional[str] = None
    recipient_city: Optional[str] = None
    recipient_country: Optional[str] = None

    # Sender Details
    sender_company: Optional[str] = None
    sender_name: Optional[str] = None
    sender_street: Optional[str] = None
    sender_zip: Optional[str] = None
    sender_city: Optional[str] = None
    sender_country: Optional[str] = None

    # Runtime / Storage Metadata
    file_path: Optional[str] = None
    export_filename: Optional[str] = None
    page_count: Optional[int] = None
    created_at: Optional[str] = None
    last_processed_at: Optional[str] = None
    last_used: Optional[str] = None

    # Fingerprints
    phash: Optional[str] = None
    text_content: Optional[str] = None

    # Dynamic & Semantic Data
    extra_data: Optional[Dict[str, Any]] = None
    semantic_data: Optional[Dict[str, Any]] = None

    # Database Virtual Columns (Read-only / Entity View)
    v_sender: Optional[str] = None
    v_doc_date: Optional[str] = None
    v_amount: Optional[float] = None

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: Any) -> List[str]:
        """
        Normalizes tag input from various formats (None, CSV string, JSON list).
        """
        if v is None:
            return []
        if isinstance(v, str):
            if v.startswith("["):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(t) for t in parsed]
                except (json.JSONDecodeError, TypeError):
                    pass
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t) for t in v]
        return []

    @field_validator("doc_type", "type_tags", mode="before")
    @classmethod
    def normalize_list_fields(cls, v: Any) -> List[str]:
        """
        Normalizes list fields like doc_type and type_tags.
        """
        if v is None:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(t) for t in parsed]
            except (json.JSONDecodeError, TypeError):
                pass
            return [v]
        if isinstance(v, list):
            return [str(t) for t in v if t]
        return []

    @field_validator("amount", "gross_amount", "postage", "packaging", "tax_rate", mode="before")
    @classmethod
    def normalize_decimals(cls, v: Any) -> Optional[Decimal]:
        """
        Normalizes decimal inputs from strings (handling commas and currency symbols).
        """
        if v is None:
            return None
        if isinstance(v, (int, float, Decimal)):
            try:
                return Decimal(str(v))
            except (ValueError, TypeError, Decimal.InvalidOperation):
                return None
        if isinstance(v, str):
            # Handle localized strings "68,50" -> "68.50"
            clean = v.replace(",", ".")
            clean = clean.replace("€", "").replace("$", "").replace("£", "").strip()
            if not clean:
                return None
            try:
                return Decimal(clean)
            except (ValueError, TypeError, Decimal.InvalidOperation):
                return None
        return None
