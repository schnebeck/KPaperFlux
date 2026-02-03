"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/models/semantic.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Pydantic models for structured semantic data extraction.
                Defines the schema for finance, legal, and meta information.
------------------------------------------------------------------------------
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class AddressInfo(BaseModel):
    """Structured address information."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    name: Optional[str] = None
    company: Optional[str] = None
    street: Optional[str] = None
    zip_code: Optional[str] = Field(None, alias="zip")
    city: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    iban: Optional[str] = None
    tax_id: Optional[str] = None


class MetaHeader(BaseModel):
    """General document header information."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    sender: Optional[AddressInfo] = None
    recipient: Optional[AddressInfo] = None
    doc_date: Optional[str] = None
    doc_number: Optional[str] = None
    language: Optional[str] = "en"


class FinanceBody(BaseModel):
    """Specific data for financial documents (Invoices, Receipts)."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    total_gross: Optional[Decimal] = None
    total_net: Optional[Decimal] = None
    total_tax: Optional[Decimal] = None
    currency: Optional[str] = "EUR"
    payment_method: Optional[str] = None
    due_date: Optional[str] = None
    invoice_number: Optional[str] = None
    order_number: Optional[str] = None
    customer_id: Optional[str] = None
    
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Tax breakdown: { "19%": 19.50, "7%": 2.10 }
    tax_details: Dict[str, Decimal] = Field(default_factory=dict)


class LegalBody(BaseModel):
    """Specific data for contracts and official letters."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    contract_type: Optional[str] = None
    parties: List[str] = Field(default_factory=list)
    effective_date: Optional[str] = None
    termination_date: Optional[str] = None


class WorkflowLog(BaseModel):
    """Event log for workflow transitions."""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    action: str
    user: Optional[str] = "SYSTEM"
    comment: Optional[str] = None


class WorkflowInfo(BaseModel):
    """Tracking state for business processes and human verification."""
    model_config = ConfigDict(populate_by_name=True)
    
    # Human-in-the-loop verification
    is_verified: bool = False
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    
    # Process management
    current_step: str = "NEW"
    history: List[WorkflowLog] = Field(default_factory=list)
    
    # Specific Workflows
    pkv_eligible: bool = False
    pkv_status: Optional[str] = None  # e.g. "PENDING", "SUBMITTED", "REIMBURSED"
    signature_detected: bool = False


class SemanticExtraction(BaseModel):
    """Root structure for AI-extracted semantic data."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    meta_header: Optional[MetaHeader] = Field(default_factory=MetaHeader)
    bodies: Dict[str, Any] = Field(default_factory=dict)
    workflow: Optional[WorkflowInfo] = Field(default_factory=WorkflowInfo)
    
    repaired_text: Optional[str] = None
    entity_types: List[str] = Field(default_factory=list)
    direction: Optional[str] = "INBOUND"
    tenant_context: Optional[str] = "PRIVATE"
    
    # Visual Audit Results
    visual_audit: Optional[Dict[str, Any]] = None

    @field_validator("bodies", mode="after")
    @classmethod
    def parse_bodies(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Attempt to coerce known bodies into Pydantic models."""
        mapping = {
            "finance_body": FinanceBody,
            "ledger_body": FinanceBody,
            "legal_body": LegalBody,
        }
        parsed = {}
        for key, value in v.items():
            if key in mapping and isinstance(value, dict):
                try:
                    parsed[key] = mapping[key](**value)
                except Exception as e:
                    # Log degradation but don't crash
                    import logging
                    logging.getLogger("KPaperFlux.Semantic").warning(f"Body hydration failed for {key}: {e}")
                    parsed[key] = value
            else:
                parsed[key] = value
        return parsed

    @property
    def sender_summary(self) -> Optional[str]:
        """Returns a human-readable summary of the sender."""
        if self.meta_header and self.meta_header.sender:
            val = self.meta_header.sender.company or self.meta_header.sender.name
            if val: return val
        
        return None


    @property
    def recipient_summary(self) -> Optional[str]:
        """Returns a human-readable summary of the recipient."""
        if self.meta_header and self.meta_header.recipient:
            return self.meta_header.recipient.company or self.meta_header.recipient.name
        return None

    @property
    def document_date(self) -> Optional[str]:
        """Shortcut to the document date in meta_header."""
        if self.meta_header and self.meta_header.doc_date:
            return self.meta_header.doc_date
            
        return None


    @property
    def document_number(self) -> Optional[str]:
        """Shortcut to the document number in meta_header."""
        if self.meta_header and self.meta_header.doc_number:
            return self.meta_header.doc_number
            
        return None


    def get_financial_value(self, field: str) -> Any:
        """Access financial totals across different semantic bodies."""
        target_keys = ["amount", "total_gross", "total_net", "total_tax", "currency", "due_date"]
        search_keys = target_keys if field == "amount" else [field]


        # 1. Search in structured bodies
        for b in self.bodies.values():
            for sk in search_keys:
                if isinstance(b, BaseModel):
                    val = getattr(b, sk, None)
                elif isinstance(b, dict):
                    val = b.get(sk)
                else:
                    val = None
                
                if val is not None:
                    return val
                    
        
        return None

