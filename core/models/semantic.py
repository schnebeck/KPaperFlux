"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/models/semantic.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Pydantic models of the semantic layer: meta header, EN 16931
                finance and other bodies, workflows, engine review state.
------------------------------------------------------------------------------
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, ValidationError, computed_field, field_validator

from core.logger import get_logger

logger = get_logger("models.semantic")

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

class SubscriptionInfo(BaseModel):
    """Details for recurring payments and subscriptions."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    is_recurring: bool = Field(False, description="True if the document is part of a subscription")
    frequency: Optional[str] = Field(None, description="MUST be: DAILY, WEEKLY, MONTHLY, QUARTERLY, YEARLY, ONCE")
    service_period_start: Optional[str] = Field(None, description="Start of service period (YYYY-MM-DD)")
    service_period_end: Optional[str] = Field(None, description="End of service period (YYYY-MM-DD)")
    next_billing_date: Optional[str] = Field(None, description="Predicted next billing date (YYYY-MM-DD)")

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
    current_step_entered_at: Optional[str] = None
    """ISO 8601 timestamp of when the document entered ``current_step``.
    Set automatically by ``apply_transition()``.  Used to compute
    ``DAYS_IN_STATE`` for timed workflow conditions without relying on the
    (fragile) last history-entry timestamp."""
    history: List[WorkflowLog] = Field(default_factory=list)

    def apply_transition(self, action: str, next_state: str, user: Optional[str] = "USER", comment: Optional[str] = None) -> None:
        self.history.append(WorkflowLog(
            action=f"TRANSITION: {action} ({self.current_step} -> {next_state})",
            user=user,
            comment=comment
        ))
        self.current_step = next_state
        self.current_step_entered_at = datetime.now().isoformat()
    
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

class StatementTransaction(BaseModel):
    """One booking of a bank or credit card statement (produced by the FluxSense engine)."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    booking_date: Optional[str] = None
    value_date: Optional[str] = None
    description: Optional[str] = None
    counterparty: Optional[str] = None
    counterparty_iban: Optional[str] = None
    reference: Optional[str] = None
    transaction_type: Optional[str] = None
    amount: Optional[Decimal] = Field(None, description="Signed: negative = debit, positive = credit")
    balance: Optional[Decimal] = None
    currency: Optional[str] = None
    source_page: Optional[int] = Field(None, description="1-based page of the analyzed PDF")


class StatementBody(BaseModel):
    """Bank / credit card statement: account, period, balances and bookings."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    statement_type: Optional[str] = Field(None, description="BANK_ACCOUNT | CREDIT_CARD | SAVINGS | DEPOT")
    account_holder: Optional[str] = None
    bank_name: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    account_number: Optional[str] = None
    card_number_masked: Optional[str] = None
    statement_number: Optional[str] = None
    statement_date: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    currency: str = "EUR"
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    total_debits: Optional[Decimal] = None
    total_credits: Optional[Decimal] = None
    debit_count: Optional[int] = None
    credit_count: Optional[int] = None
    credit_limit: Optional[Decimal] = None
    minimum_payment: Optional[Decimal] = None
    payment_due_date: Optional[str] = None
    transactions: List[StatementTransaction] = Field(default_factory=list)

    @field_validator("iban", "bic", mode="before")
    @classmethod
    def normalize_banking(cls, v: Any) -> Any:
        """Removes whitespace from IBAN/BIC and uppercases them."""
        if isinstance(v, str):
            return "".join(v.split()).upper()
        return v


class FieldReviewState(BaseModel):
    """
    Review state of one extracted value as reported by an external analysis
    engine. ``path`` is the dotted path of the value inside the semantic data
    (e.g. ``bodies.finance_body.invoice_number``, ``meta_header.references.0.ref_value``).
    """
    model_config = ConfigDict(extra="ignore")
    path: str
    value: Optional[Any] = None
    kind: Optional[str] = Field(None, description="amount | date | iban | identifier | text | integer | code")
    page: Optional[int] = Field(None, description="1-based page within this document where the value was found")
    bbox: Optional[List[float]] = Field(None, description="Box [x0, y0, x1, y1], 0-1000 normalized")
    evidence: Optional[str] = Field(None, description="Verbatim snippet as printed")
    critical: bool = False
    status: Optional[str] = Field(None, description="Grounding status, e.g. grounded | ungrounded | verified_visual | removed")
    action: Optional[str] = Field(None, description="kept | nulled | replaced | flagged | ...")
    original_value: Optional[Any] = None
    provenance: Optional[str] = Field(None, description="label | geometry | check | model")
    auto_accepted: Optional[bool] = Field(None, description="True: accepted without review; False: needs review; None: not filled")
    review_reasons: List[str] = Field(default_factory=list)
    confirmed_by_user: bool = Field(False, description="The user edited or confirmed this value")
    confirmed_at: Optional[str] = Field(None, description="ISO timestamp of the user's confirmation")

    @property
    def needs_review(self) -> bool:
        """True if the engine flagged this value for human review and the user has not confirmed it yet."""
        return self.auto_accepted is False and not self.confirmed_by_user


class EngineInfo(BaseModel):
    """
    Provenance and review metadata of an extraction produced by an external
    analysis engine (e.g. FluxSense). Stored in ``semantic_data.engine``.
    """
    model_config = ConfigDict(extra="ignore")
    name: str
    version: Optional[str] = None
    schema_version: Optional[str] = None
    prompt_version: Optional[str] = None
    status: str = Field("OK", description="OK | PARTIAL | ERROR (engine run status)")
    analyzed_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    subtype: Optional[str] = None
    classification_confidence: Optional[float] = None
    model_confidence: Optional[float] = Field(None, description="The model's self-assessed extraction confidence")
    analyzed_pages: List[int] = Field(default_factory=list, description="Pages of the analyzed PDF that form this document")
    fields: List[FieldReviewState] = Field(default_factory=list)
    plausibility: Dict[str, Any] = Field(default_factory=dict)
    review: Optional[Dict[str, Any]] = None
    trust: Dict[str, Any] = Field(default_factory=dict)
    zugferd_comparison: Optional[Dict[str, Any]] = None
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    error_code: Optional[str] = Field(None, description="Machine-readable failure reason, e.g. AI_SERVER_UNREACHABLE")
    server_url: Optional[str] = Field(None, description="Server the failed run depended on (for user messages)")
    warnings: List[str] = Field(default_factory=list)
    unvalidated: Dict[str, Any] = Field(default_factory=dict, description="Engine output that failed model validation (kept verbatim)")

    def field_state(self, path: str) -> Optional[FieldReviewState]:
        """
        Returns the review state of one value.

        Args:
            path: Dotted path inside the semantic data.

        Returns:
            The FieldReviewState, or None if the engine reported nothing for it.
        """
        for state in self.fields:
            if state.path == path:
                return state
        return None

    def fields_needing_review(self) -> List["FieldReviewState"]:
        """Returns all values the engine flagged for review that the user has not confirmed."""
        return [state for state in self.fields if state.needs_review]

    @computed_field  # stored with the JSON so lists and filters can query it
    @property
    def review_count(self) -> int:
        """Number of values still needing review."""
        return len(self.fields_needing_review())

    def confirm(self, paths: List[str], when: Optional[str] = None) -> int:
        """
        Marks values as confirmed by the user (edited or explicitly accepted).

        Args:
            paths: Dotted field paths.
            when: ISO timestamp (default: now).

        Returns:
            Number of newly confirmed values.
        """
        stamp = when or datetime.now().isoformat(timespec="seconds")
        wanted = set(paths)
        confirmed = 0
        for state in self.fields:
            if state.path in wanted and not state.confirmed_by_user:
                state.confirmed_by_user = True
                state.confirmed_at = stamp
                confirmed += 1
        return confirmed


class SemanticExtraction(BaseModel):
    """The central extraction model. Strict but informative."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore", validate_assignment=True)
    meta_header: Optional[MetaHeader] = Field(default_factory=MetaHeader)
    bodies: Dict[str, Any] = Field(default_factory=dict)
    workflows: Dict[str, WorkflowInfo] = Field(default_factory=dict)
    repaired_text: Optional[str] = None
    type_tags: List[str] = Field(default_factory=list)
    direction: Optional[str] = "INBOUND"
    tenant_context: Optional[str] = "PRIVATE"
    ai_confidence: float = Field(1.0, description="Confidence score for the overall extraction (0.0 - 1.0)")
    extraction_source: Optional[str] = Field(None, description="Data source: 'AI', 'ZUGFERD_NATIVE', or None")
    visual_audit: Optional[VisualAuditResult] = None
    engine: Optional[EngineInfo] = Field(None, description="Analysis engine provenance and per-field review state")

    @field_validator("engine", mode="before")
    @classmethod
    def tolerant_engine(cls, v: Any) -> Any:
        """Drops malformed engine metadata instead of failing the whole extraction."""
        if v is None or isinstance(v, EngineInfo):
            return v
        if isinstance(v, dict):
            try:
                return EngineInfo.model_validate(v)
            except ValidationError as e:
                logger.warning(f"Ignoring malformed engine metadata: {e.error_count()} validation errors")
                return None
        logger.warning(f"Ignoring engine metadata of type {type(v).__name__}")
        return None

    @field_validator("bodies", mode="after")
    @classmethod
    def parse_bodies(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        mapping = {
            "finance_body": FinanceBody, 
            "legal_body": LegalBody,
            "subscription_info": SubscriptionInfo,
            "statement_body": StatementBody,
        }
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
