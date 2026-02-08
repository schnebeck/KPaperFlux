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
import logging

# Internal Imports
from core.utils.validation import validate_iban, validate_bic

logger = logging.getLogger("KPaperFlux.Semantic")


class AddressInfo(BaseModel):
    """Structured address information."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    name: Optional[str] = None
    company: Optional[str] = None
    street: Optional[str] = None
    house_number: Optional[str] = None
    zip_code: Optional[str] = Field(None, alias="zip")
    city: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    tax_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def flatten_nested_data(cls, data: Any) -> Any:
        """
        Repairs common AI hallucinations.
        1. Flattens nested blocks (address/contact/identifiers) into the flat root.
        2. Drops any fields not explicitly defined in the model to satisfy extra="forbid".
        """
        if not isinstance(data, dict):
            return data
        
        # --- 1. Flattening ---
        # Address block
        addr = data.pop("address", None)
        if isinstance(addr, dict):
            for k, v in addr.items():
                if k not in data or data[k] is None:
                    data[k] = v
        
        # Contact block
        cont = data.pop("contact", None)
        if isinstance(cont, dict):
            if "phones" in cont and isinstance(cont["phones"], list) and cont["phones"]:
                data["phone"] = cont["phones"][0]
            if "emails" in cont and isinstance(cont["emails"], list) and cont["emails"]:
                data["email"] = cont["emails"][0]
            if "contact_person" in cont and not data.get("name"):
                data["name"] = cont["contact_person"]

        # Identifiers block
        ids = data.pop("identifiers", None)
        if isinstance(ids, dict):
            for k in ["vat_id", "tax_id"]:
                val = ids.get(k)
                if val: data["tax_id"] = val

        # --- 2. Sanitization (Drop everything unknown) ---
        allowed_keys = set(cls.model_fields.keys())
        # Also allow aliases (like 'zip')
        for field_info in cls.model_fields.values():
            if field_info.alias:
                allowed_keys.add(field_info.alias)

        current_keys = list(data.keys())
        for k in current_keys:
            if k not in allowed_keys:
                data.pop(k)

        return data

    @field_validator("iban", "bic", mode="before")
    @classmethod
    def clean_bank_fields(cls, v: Any) -> Optional[str]:
        """Removes spaces and ensures uppercase for IBAN and BIC."""
        if v is None:
            return None
        if not isinstance(v, str):
            return str(v)
        
        # Remove all whitespace
        cleaned = "".join(v.split()).upper()
        
        # Validation (Logging only, don't block hydration)
        if "IBAN" in str(cls): # Poor man's check which field we are in via field name in validator
            pass # field_validator knows the field name if we ask
        
        return cleaned if cleaned else None

    @model_validator(mode="after")
    def validate_bank_integrity(self) -> 'AddressInfo':
        """Optional integrity check for IBAN/BIC."""
        if self.iban and not validate_iban(self.iban):
            logger.warning(f"Invalid IBAN detected for '{self.name or self.company}': {self.iban}")
        if self.bic and not validate_bic(self.bic):
            logger.warning(f"Invalid BIC detected for '{self.name or self.company}': {self.bic}")
        return self


class MetaHeader(BaseModel):
    """General document header information."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    sender: Optional[AddressInfo] = None
    recipient: Optional[AddressInfo] = None
    doc_date: Optional[str] = None
    doc_number: Optional[str] = None
    language: Optional[str] = "en"
    subject_context: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def handle_nested_meta(cls, data: Any) -> Any:
        """Flattens known nested objects in meta_header."""
        if not isinstance(data, dict):
            return data
        
        # Handle "subject_context" if it's sitting outside or weirdly named
        if "subject" in data and not data.get("subject_context"):
            data["subject_context"] = {"raw": data.pop("subject")}
            
        return data


class LineItem(BaseModel):
    """Represents a single position (BT-126 to BT-161 in EN 16931)."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    
    pos: Optional[str] = Field(None, alias="BT-126")
    description: Optional[str] = Field(None, alias="BT-153")
    quantity: Optional[Decimal] = Field(None, alias="BT-129")
    unit: Optional[str] = Field("C62", alias="BT-130") # C62 is "one" (stk)
    
    unit_price: Optional[Decimal] = Field(None, alias="BT-146")
    total_price: Optional[Decimal] = Field(None, alias="BT-131") # Net line total
    tax_rate: Optional[Decimal] = Field(None, alias="BT-152")
    
    # Technical Fields
    article_number: Optional[str] = Field(None, alias="BT-155")

    @model_validator(mode="before")
    @classmethod
    def autofix_zugferd_item(cls, data: Any) -> Any:
        if not isinstance(data, dict): return data
        # Map ZUGFeRD XML-style keys to our BT-aliases or direct keys
        mapping = {
            "IncludedSupplyChainTradeLineItem": "IncludedSupplyChainTradeLineItem", # recursive flattening hint
            "pos_no": "pos",
            "item_name": "description",
            "billed_quantity": "quantity",
            "net_price": "unit_price",
            "line_total": "total_price",
            "net_amount": "total_price",
            "tax_percent": "tax_rate"
        }
        for old, new in mapping.items():
            if old in data:
                val = data.pop(old)
                if new in cls.model_fields and (new not in data or data[new] is None):
                    data[new] = val
        
        # Cleanup
        allowed = set(cls.model_fields.keys())
        for k in list(data.keys()):
            if k not in allowed: data.pop(k)
        return data


class TaxBreakdownRow(BaseModel):
    """Breakdown per tax rate (BT-116 to BT-121 in EN 16931)."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    tax_basis_amount: Decimal = Field(..., alias="BT-116")
    tax_amount: Decimal = Field(..., alias="BT-117")
    tax_rate: Decimal = Field(..., alias="BT-119")
    tax_category: str = Field("S", alias="BT-118") # S=Standard

    @model_validator(mode="before")
    @classmethod
    def autofix_tax_row(cls, data: Any) -> Any:
        """Maps ZUGFeRD XML-style keys to our BT-aliases or direct keys."""
        if not isinstance(data, dict): return data
        mapping = {
            "BasisAmount": "tax_basis_amount",
            "tax_basis": "tax_basis_amount",
            "tax_basis_amount": "tax_basis_amount",
            "CalculatedAmount": "tax_amount",
            "tax_amount": "tax_amount",
            "RateApplicablePercent": "tax_rate",
            "tax_rate": "tax_rate",
            "tax_percent": "tax_rate",
            "CategoryCode": "tax_category",
            "tax_category": "tax_category"
        }
        for old, new in mapping.items():
            if old in data:
                val = data.pop(old)
                if new in cls.model_fields and (new not in data or data[new] is None):
                    data[new] = val
        
        # Cleanup
        allowed = set(cls.model_fields.keys())
        for k in list(data.keys()):
            if k not in allowed: data.pop(k)
        return data


class MonetarySummation(BaseModel):
    """Final totals (BT-106 to BT-115)."""
    model_config = ConfigDict(populate_by_name=True)
    line_total_amount: Optional[Decimal] = Field(None, alias="BT-106")
    charge_total_amount: Optional[Decimal] = Field(None, alias="BT-107") # Total charges
    allowance_total_amount: Optional[Decimal] = Field(None, alias="BT-108") # Total discounts
    tax_basis_total_amount: Optional[Decimal] = Field(None, alias="BT-109") # Net sum
    tax_total_amount: Optional[Decimal] = Field(None, alias="BT-110") # Total tax
    grand_total_amount: Optional[Decimal] = Field(None, alias="BT-112") # Gross sum
    due_payable_amount: Optional[Decimal] = Field(None, alias="BT-115") # Final amount to pay

    @model_validator(mode="before")
    @classmethod
    def autofix_totals(cls, data: Any) -> Any:
        if not isinstance(data, dict): return data
        mapping = {
            "line_total": "line_total_amount",
            "net_total": "tax_basis_total_amount",
            "total_net": "tax_basis_total_amount",
            "total_tax": "tax_total_amount",
            "total_gross": "grand_total_amount",
            "gross_total": "grand_total_amount",
            "due_amount": "due_payable_amount"
        }
        for old, new in mapping.items():
            if old in data:
                val = data.pop(old)
                if new in cls.model_fields and (new not in data or data[new] is None):
                    data[new] = val
        return data


class FinanceBody(BaseModel):
    """
    EN 16931 / ZUGFeRD 2.2 aligned Financial Body.
    Focuses on Trade Transactions (Invoices/Receipts).
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    
    # --- BT-1 to BT-26 (Header Level) ---
    invoice_number: Optional[str] = Field(None, alias="BT-1")
    invoice_date: Optional[str] = Field(None, alias="BT-2")
    due_date: Optional[str] = Field(None, alias="BT-9")
    currency: str = Field("EUR", alias="BT-5")
    payment_reference: Optional[str] = Field(None, alias="BT-83")
    order_number: Optional[str] = Field(None, alias="BT-13")
    order_date: Optional[str] = Field(None, alias="BT-14")
    service_date: Optional[str] = Field(None, alias="BT-7")
    customer_id: Optional[str] = Field(None, alias="BT-46")
    buyer_reference: Optional[str] = Field(None, alias="BT-10")
    project_reference: Optional[str] = Field(None, alias="BT-11")
    accounting_reference: Optional[str] = Field(None, alias="BT-19") # Kostenstelle
    payment_terms: Optional[str] = Field(None, alias="BT-20") # Skonto / Bedingungen
    payment_accounts: List[AddressInfo] = Field(default_factory=list)
    
    # --- Supply Chain Trade Transaction ---
    line_items: List[LineItem] = Field(default_factory=list, alias="IncludedSupplyChainTradeLineItem")
    
    # --- Totals & Settlement ---
    monetary_summation: Optional[MonetarySummation] = Field(default_factory=MonetarySummation, alias="SpecifiedTradeSettlementMonetarySummation")
    tax_breakdown: List[TaxBreakdownRow] = Field(default_factory=list, alias="ApplicableTradeTax")
    tax_details: Dict[str, Decimal] = Field(default_factory=dict)
    
    @model_validator(mode="before")
    @classmethod
    def handle_zugferd_nesting(cls, data: Any) -> Any:
        """Flattens complex XML-translated structures into our flat model."""
        if not isinstance(data, dict): return data
        
        # Catch deeply nested ZUGFeRD XML-JSON conversions or AI hallucinations
        if "SupplyChainTradeTransaction" in data:
            trans = data.pop("SupplyChainTradeTransaction")
            if isinstance(trans, dict):
                if "IncludedSupplyChainTradeLineItem" in trans:
                    data["line_items"] = trans["IncludedSupplyChainTradeLineItem"]
                
                settlement = trans.get("ApplicableTradeSettlement")
                if isinstance(settlement, dict):
                    if "SpecifiedTradeSettlementMonetarySummation" in settlement:
                        data["monetary_summation"] = settlement["SpecifiedTradeSettlementMonetarySummation"]
                    if "ApplicableTradeTax" in settlement:
                        data["tax_breakdown"] = settlement["ApplicableTradeTax"]
            
        return data


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
    playbook_id: Optional[str] = None
    current_step: str = "NEW"
    history: List[WorkflowLog] = Field(default_factory=list)

    def apply_transition(self, action: str, next_state: str, user: Optional[str] = "USER", comment: Optional[str] = None):
        """Applies a state change and logs it."""
        from core.models.semantic import WorkflowLog # Late import to avoid edge cases in hydration
        self.history.append(WorkflowLog(
            action=f"TRANSITION: {action} ({self.current_step} -> {next_state})",
            user=user,
            comment=comment
        ))
        self.current_step = next_state
    
    # Specific Workflows
    pkv_eligible: bool = False
    pkv_status: Optional[str] = None  # e.g. "PENDING", "SUBMITTED", "REIMBURSED"
    signature_detected: bool = False


class SemanticExtraction(BaseModel):
    """Root structure for AI-extracted semantic data."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    meta_header: Optional[MetaHeader] = Field(default_factory=MetaHeader)
    bodies: Dict[str, Any] = Field(default_factory=dict)
    workflow: Optional[WorkflowInfo] = Field(default_factory=WorkflowInfo)
    
    repaired_text: Optional[str] = None
    type_tags: List[str] = Field(default_factory=list)
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
        """Access financial values using exact schema paths (EN 16931)."""
        # 1. Search in structured bodies
        for b in self.bodies.values():
            # Check if field contains a dot for nested access
            if "." in field:
                parts = field.split(".")
                curr = b
                for p in parts:
                    if isinstance(curr, dict):
                        curr = curr.get(p)
                    else:
                        curr = getattr(curr, p, None)
                    if curr is None: break
                if curr is not None: return curr
            else:
                # Direct attribute access
                val = getattr(b, field, None) if not isinstance(b, dict) else b.get(field)
                if val is not None:
                    return val
                    
        return None

