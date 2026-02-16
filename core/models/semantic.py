from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator

class AddressInfo(BaseModel):
    """Standardized address and contact block."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    company: Optional[str] = None
    name: Optional[str] = None
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
    vat_id: Optional[str] = None

    @field_validator("iban", "bic", mode="before")
    @classmethod
    def normalize_banking(cls, v: Any) -> Any:
        if isinstance(v, str):
            # Remove all spaces and special chars, uppercase it
            return "".join(v.split()).upper()
        return v

class DocumentReference(BaseModel):
    """External ID or reference found in the document (e.g. Project ID, Order ID)."""
    model_config = ConfigDict(populate_by_name=True)
    ref_type: str = Field(..., description="e.g. CUSTOMER_ID, ORDER_NUMBER, PROJECT_ID")
    ref_value: str = Field(..., description="The actual ID value")

class MetaHeader(BaseModel):
    """Document header with sender, recipient and metadata."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    sender: Optional[AddressInfo] = Field(default_factory=AddressInfo)
    recipient: Optional[AddressInfo] = Field(default_factory=AddressInfo)
    doc_date: Optional[str] = None
    doc_number: Optional[str] = None
    language: str = "de"
    references: List[DocumentReference] = Field(default_factory=list, description="IDs for semantic linking")

class LineItem(BaseModel):
    """Single line item (BT-126 to BT-155)."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore") # Allow AI to context-dump in Items
    pos: Optional[str] = Field(None, alias="BT-126")
    description: Optional[str] = Field(None, alias="BT-153")
    quantity: Optional[Decimal] = Field(None, alias="BT-129")
    unit: Optional[str] = Field("C62", alias="BT-130")
    unit_price: Optional[Decimal] = Field(None, alias="BT-146")
    total_price: Optional[Decimal] = Field(None, alias="BT-131")
    tax_rate: Optional[Decimal] = Field(None, alias="BT-152")
    article_number: Optional[str] = Field(None, alias="BT-155")

class TaxBreakdownRow(BaseModel):
    """Breakdown per tax rate (BT-116 to BT-121)."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    tax_basis_amount: Decimal = Field(..., alias="BT-116")
    tax_amount: Decimal = Field(..., alias="BT-117")
    tax_rate: Decimal = Field(..., alias="BT-119")
    tax_category: str = Field("S", alias="BT-118")

class MonetarySummation(BaseModel):
    """Final totals (BT-106 to BT-115)."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    line_total_amount: Optional[Decimal] = Field(None, alias="BT-106")
    charge_total_amount: Optional[Decimal] = Field(None, alias="BT-107")
    allowance_total_amount: Optional[Decimal] = Field(None, alias="BT-108")
    tax_basis_total_amount: Optional[Decimal] = Field(None, alias="BT-109")
    tax_total_amount: Optional[Decimal] = Field(None, alias="BT-110")
    grand_total_amount: Optional[Decimal] = Field(None, alias="BT-112")
    due_payable_amount: Optional[Decimal] = Field(None, alias="BT-115")

class FinanceBody(BaseModel):
    """Enforce strict ZUGFeRD 2.2 / EN 16931 alignment."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
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
    accounting_reference: Optional[str] = Field(None, alias="BT-19")
    payment_terms: Optional[str] = Field(None, alias="BT-20")
    payment_accounts: List[AddressInfo] = Field(default_factory=list)
    line_items: List[LineItem] = Field(default_factory=list, alias="IncludedSupplyChainTradeLineItem")
    monetary_summation: Optional[MonetarySummation] = Field(default_factory=MonetarySummation, alias="SpecifiedTradeSettlementMonetarySummation")
    tax_breakdown: List[TaxBreakdownRow] = Field(default_factory=list, alias="ApplicableTradeTax")

class NoticePeriod(BaseModel):
    """Strictly structured notice period for legal evaluation."""
    model_config = ConfigDict(populate_by_name=True)
    value: Optional[int] = Field(None, description="Numerical value (e.g. 3, 14)")
    unit: Optional[str] = Field(None, description="MUST be: DAYS, WEEKS, MONTHS, YEARS")
    anchor_type: Optional[str] = Field(None, description="MUST be: START_OF, END_OF, ANY_TIME")
    anchor_scope: Optional[str] = Field(None, description="MUST be: WEEK, MONTH, QUARTER, HALF_YEAR, YEAR")
    original_text: Optional[str] = Field(None, description="Raw extracted text for verification")

class LegalBody(BaseModel):
    """Enhanced data model for contracts and legal documents."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    document_title: Optional[str] = None
    contract_id: Optional[str] = None
    issuer: Optional[str] = None
    beneficiary: Optional[str] = None
    subject_reference: Optional[str] = None
    statements: List[str] = Field(default_factory=list)
    compliance_standards: List[str] = Field(default_factory=list)
    effective_date: Optional[str] = None
    termination_date: Optional[str] = None
    valid_until: Optional[str] = None
    notice_period: Optional[NoticePeriod] = Field(default_factory=NoticePeriod)
    renewal_clause: Optional[str] = None
    contract_type: Optional[str] = None
    parties: List[str] = Field(default_factory=list)

class WorkflowLog(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    action: str
    user: Optional[str] = "SYSTEM"
    comment: Optional[str] = None

class WorkflowInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    is_verified: bool = False
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    rule_id: Optional[str] = None
    current_step: str = "NEW"
    history: List[WorkflowLog] = Field(default_factory=list)

    def apply_transition(self, action: str, next_state: str, user: Optional[str] = "USER", comment: Optional[str] = None):
        self.history.append(WorkflowLog(
            action=f"TRANSITION: {action} ({self.current_step} -> {next_state})",
            user=user,
            comment=comment
        ))
        self.current_step = next_state
    
    pkv_eligible: bool = False
    pkv_status: Optional[str] = None 
    signature_detected: bool = False

class VisualAuditResult(BaseModel):
    """Structured result of Stage 1.5 Forensic Audit."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid", validate_assignment=True)
    audit_summary: Optional[Dict[str, Any]] = Field(default_factory=dict)
    layer_stamps: List[Dict[str, Any]] = Field(default_factory=list)
    signatures: Optional[Dict[str, Any]] = None
    integrity: Optional[Dict[str, Any]] = Field(default_factory=dict)
    arbiter_decision: Optional[Dict[str, Any]] = Field(default_factory=dict)
    meta_mode: Optional[str] = None

class SemanticExtraction(BaseModel):
    """The central extraction model. Strict but informative."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid", validate_assignment=True)
    meta_header: Optional[MetaHeader] = Field(default_factory=MetaHeader)
    bodies: Dict[str, Any] = Field(default_factory=dict)
    workflow: Optional[WorkflowInfo] = Field(default_factory=WorkflowInfo)
    repaired_text: Optional[str] = None
    type_tags: List[str] = Field(default_factory=list)
    direction: Optional[str] = "INBOUND"
    tenant_context: Optional[str] = "PRIVATE"
    ai_confidence: float = Field(1.0, description="Confidence score for the overall extraction (0.0 - 1.0)")
    visual_audit: Optional[VisualAuditResult] = None

    @field_validator("bodies", mode="after")
    @classmethod
    def parse_bodies(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        mapping = {"finance_body": FinanceBody, "legal_body": LegalBody}
        parsed = {}
        for key, value in v.items():
            if key in mapping and isinstance(value, dict):
                try:
                    parsed[key] = mapping[key](**value)
                except Exception:
                    parsed[key] = value
            else:
                parsed[key] = value
        return parsed

    @property
    def sender_summary(self) -> Optional[str]:
        if self.meta_header and self.meta_header.sender:
            return self.meta_header.sender.company or self.meta_header.sender.name
        return None

    @property
    def recipient_summary(self) -> Optional[str]:
        if self.meta_header and self.meta_header.recipient:
            return self.meta_header.recipient.company or self.meta_header.recipient.name
        return None

    @property
    def document_date(self) -> Optional[str]:
        return self.meta_header.doc_date if self.meta_header else None

    @property
    def document_number(self) -> Optional[str]:
        return self.meta_header.doc_number if self.meta_header else None

    def get_financial_value(self, field: str) -> Any:
        for b in self.bodies.values():
            if "." in field:
                parts = field.split(".")
                curr = b
                for p in parts:
                    if isinstance(curr, dict): curr = curr.get(p)
                    else: curr = getattr(curr, p, None)
                    if curr is None: break
                if curr is not None: return curr
            else:
                val = getattr(b, field, None) if not isinstance(b, dict) else b.get(field)
                if val is not None: return val
        return None
