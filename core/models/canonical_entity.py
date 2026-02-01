"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/models/canonical_entity.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Defines the canonical data models for structured document 
                information. Uses Pydantic for validation and serialization 
                of various domain components like parties, invoices, taxes, 
                and logistics.
------------------------------------------------------------------------------
"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class DocType(str, Enum):
    """Enumeration of recognized document types across different domains."""
    # 1. Trade & Commerce
    QUOTE = "QUOTE"
    ORDER = "ORDER"
    ORDER_CONFIRMATION = "ORDER_CONFIRMATION"
    DELIVERY_NOTE = "DELIVERY_NOTE"
    INVOICE = "INVOICE"
    CREDIT_NOTE = "CREDIT_NOTE"
    RECEIPT = "RECEIPT"
    DUNNING = "DUNNING"

    # 2. Finance & Tax
    BANK_STATEMENT = "BANK_STATEMENT"
    TAX_ASSESSMENT = "TAX_ASSESSMENT"
    EXPENSE_REPORT = "EXPENSE_REPORT"
    UTILITY_BILL = "UTILITY_BILL"

    # 3. Legal & HR
    CONTRACT = "CONTRACT"
    INSURANCE_POLICY = "INSURANCE_POLICY"
    PAYSLIP = "PAYSLIP"
    LEGAL_CORRESPONDENCE = "LEGAL_CORRESPONDENCE"
    OFFICIAL_LETTER = "OFFICIAL_LETTER"

    # 4. Life & Misc
    CERTIFICATE = "CERTIFICATE"
    MEDICAL_DOCUMENT = "MEDICAL_DOCUMENT"
    VEHICLE_REGISTRATION = "VEHICLE_REGISTRATION"
    APPLICATION = "APPLICATION"
    NOTE = "NOTE"
    OTHER = "OTHER"


class Party(BaseModel):
    """Represents a legal entity or person (sender/recipient)."""
    name: Optional[str] = None
    address: Optional[str] = None
    id: Optional[str] = None  # Customer ID, Tax ID, etc.
    company: Optional[str] = None
    street: Optional[str] = None
    zip_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None


class Parties(BaseModel):
    """Wraps sender and recipient parties."""
    sender: Optional[Party] = None
    recipient: Optional[Party] = None


class LogisticsData(BaseModel):
    """Model for shipping and delivery information."""
    delivery_date_expected: Optional[date] = None
    tracking_number: Optional[str] = None
    shipping_provider: Optional[str] = None
    incoterms: Optional[str] = None
    gross_weight_kg: Optional[float] = None
    package_count: Optional[int] = None


class BankStatementData(BaseModel):
    """Model for bank statement headers."""
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    currency: str = "EUR"


class LegalMetaData(BaseModel):
    """Model for legal document headers and deadlines."""
    file_reference_sender: Optional[str] = None
    file_reference_recipient: Optional[str] = None
    court_name: Optional[str] = None
    chamber: Optional[str] = None
    response_required: bool = False
    response_deadline: Optional[date] = None
    hearing_date: Optional[datetime] = None
    subject: Optional[str] = None
    intent: Optional[str] = None
    claimed_amount: Optional[float] = None


class TaxAssessmentData(BaseModel):
    """Model for tax assessment specific fields."""
    tax_year: Optional[str] = None
    tax_number: Optional[str] = None
    tax_type: Optional[str] = None
    is_provisional: bool = False
    total_tax_fixed: Optional[float] = None
    prepayments_made: Optional[float] = None
    refund_or_payment: Optional[float] = None
    payment_due_date: Optional[date] = None


class InvoiceData(BaseModel):
    """Model for financial data (Invoices/Receipts)."""
    invoice_number: Optional[str] = None
    order_number: Optional[str] = None
    payment_terms: Optional[str] = None
    due_date: Optional[date] = None
    tax_amounts: List[Dict[str, Any]] = Field(default_factory=list)
    net_amount: Optional[float] = None
    gross_amount: Optional[float] = None
    currency: str = "EUR"

    @field_validator('net_amount', 'gross_amount', mode='before')
    @classmethod
    def parse_flexible_float(cls, v: Any) -> Optional[float]:
        """Handles localized strings and currency symbols in numeric inputs."""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            clean = v.replace("€", "").replace("$", "").replace("£", "").strip()
            if "," in clean and "." in clean:
                if clean.rfind(",") > clean.rfind("."):
                    clean = clean.replace(".", "").replace(",", ".")
                else:
                    clean = clean.replace(",", "")
            elif "," in clean:
                clean = clean.replace(",", ".")

            try:
                return float(clean)
            except (ValueError, TypeError):
                return None
        return None

    @field_validator('tax_amounts', mode='before')
    @classmethod
    def parse_tax_list(cls, v: Any) -> List[Dict[str, Any]]:
        """Handles various AI response formats for tax line items."""
        if v is None:
            return []
        if not isinstance(v, list):
            return []

        cleaned = []
        for x in v:
            if isinstance(x, dict):
                cleaned.append(x)
            elif isinstance(x, str):
                val = cls.parse_flexible_float(x)
                if val is not None:
                    cleaned.append({"amount": val, "rate": 0.0})
        return cleaned


class LineItem(BaseModel):
    """Represents a single position in a table (e.g., Invoice Item)."""
    pos: Optional[int] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    quantity_unit: Optional[str] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    quantity_delivered: Optional[float] = None
    quantity_open: Optional[float] = None
    batch_number: Optional[str] = None


class VehicleData(BaseModel):
    """Model for vehicle-related information."""
    vin: Optional[str] = None
    license_plate: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    first_registration_date: Optional[date] = None
    owner: Optional[str] = None


class MedicalData(BaseModel):
    """Model for medical documents and prescriptions."""
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    diagnosis_code: Optional[str] = None
    treatment_date: Optional[date] = None
    medication_list: List[str] = Field(default_factory=list)


class InsuranceData(BaseModel):
    """Model for insurance policies."""
    insurance_number: Optional[str] = None
    insurance_type: Optional[str] = None
    coverage_amount: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class UtilityData(BaseModel):
    """Model for consumption/utility bills (Electricity, Gas, etc.)."""
    meter_id: Optional[str] = None
    consumption_kwh: Optional[float] = None
    consumption_m3: Optional[float] = None
    reading_date: Optional[date] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class ExpenseData(BaseModel):
    """Model for travel expense reports."""
    employee_id: Optional[str] = None
    cost_center: Optional[str] = None
    trip_start: Optional[datetime] = None
    trip_end: Optional[datetime] = None
    total_reimbursable: Optional[float] = None


class BankTransaction(BaseModel):
    """Model for a single transaction on a bank statement."""
    date: Optional[date] = None
    valuta: Optional[date] = None
    counterparty_name: Optional[str] = None
    purpose: Optional[str] = None
    amount: Optional[float] = None
    transaction_type: Optional[str] = None


class ContractData(BaseModel):
    """Model for contractual agreements."""
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    cancellation_period: Optional[str] = None
    next_termination_date: Optional[date] = None
    contract_partner: Optional[str] = None
    contract_number: Optional[str] = None


class CanonicalEntity(BaseModel):
    """
    Main container for a canonicalized document entity.
    Aggregates all extracted and normalized metadata.
    """
    entity_type: DocType
    doc_id: Optional[str] = None
    doc_date: Optional[date] = None
    parties: Parties = Field(default_factory=Parties)
    tags_and_flags: List[str] = Field(default_factory=list)

    # Specific data blocks based on entity_type
    specific_data: Dict[str, Any] = Field(default_factory=dict)

    # Polymorphic list data (LineItems or BankTransactions)
    list_data: List[Dict[str, Any]] = Field(default_factory=list)

    # Provenance information
    source_doc_uuid: str
    page_range: List[int] = Field(default_factory=list)

    # Stamp/Forensic data
    stamps: List[Dict[str, Any]] = Field(default_factory=list)

    # Multi-tenant / Role context
    direction: Optional[str] = None  # "INCOMING" or "OUTGOING"
