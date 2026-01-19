
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import date, datetime
from enum import Enum

# --- Enums ---
class DocType(str, Enum):
    # 1. Trade & Commerce
    QUOTE = "QUOTE" # Angebot
    ORDER = "ORDER" # Bestellung
    ORDER_CONFIRMATION = "ORDER_CONFIRMATION" # Auftragsbestätigung
    DELIVERY_NOTE = "DELIVERY_NOTE" # Lieferschein
    INVOICE = "INVOICE" # Rechnung
    CREDIT_NOTE = "CREDIT_NOTE" # Gutschrift
    RECEIPT = "RECEIPT" # Quittung / Kassenbon
    DUNNING = "DUNNING" # Mahnung
    
    # 2. Finance & Tax
    BANK_STATEMENT = "BANK_STATEMENT" # Kontoauszug
    TAX_ASSESSMENT = "TAX_ASSESSMENT" # Steuerbescheid
    EXPENSE_REPORT = "EXPENSE_REPORT" # Reisekosten / Spesen
    UTILITY_BILL = "UTILITY_BILL" # Versorgerrechnung (Strom/Gas/Wasser)
    
    # 3. Legal & HR
    CONTRACT = "CONTRACT" # Vertrag
    INSURANCE_POLICY = "INSURANCE_POLICY" # Versicherungspolice
    PAYSLIP = "PAYSLIP" # Gehaltsabrechnung
    LEGAL_CORRESPONDENCE = "LEGAL_CORRESPONDENCE" # Anwalt / Notar / Gericht
    OFFICIAL_LETTER = "OFFICIAL_LETTER" # Behördenschreiben / Amt
    
    # 4. Life & Misc
    CERTIFICATE = "CERTIFICATE" # Zeugnis / Urkunde
    MEDICAL_DOCUMENT = "MEDICAL_DOCUMENT" # Arzt / Rezept
    VEHICLE_REGISTRATION = "VEHICLE_REGISTRATION" # KFZ-Schein / Brief
    APPLICATION = "APPLICATION" # Antrag / Formular
    NOTE = "NOTE" # Notiz
    OTHER = "OTHER" # Fallback

# --- Core Components ---
class Party(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    id: Optional[str] = None # Customer ID, Tax ID, etc.
    company: Optional[str] = None
    street: Optional[str] = None
    zip_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None

class Parties(BaseModel):
    sender: Optional[Party] = None
    recipient: Optional[Party] = None

# --- Specific Data Blocks ---

class LogisticsData(BaseModel):
    delivery_date_expected: Optional[date] = None
    tracking_number: Optional[str] = None
    shipping_provider: Optional[str] = None
    incoterms: Optional[str] = None
    gross_weight_kg: Optional[float] = None
    package_count: Optional[int] = None

class BankStatementData(BaseModel):
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    currency: str = "EUR"

class LegalMetaData(BaseModel):
    file_reference_sender: Optional[str] = None
    file_reference_recipient: Optional[str] = None
    court_name: Optional[str] = None
    chamber: Optional[str] = None
    response_required: bool = False
    response_deadline: Optional[date] = None
    hearing_date: Optional[datetime] = None
    subject: Optional[str] = None
    intent: Optional[str] = None # Klage/Bescheid etc
    claimed_amount: Optional[float] = None

class TaxAssessmentData(BaseModel):
    tax_year: Optional[str] = None
    tax_number: Optional[str] = None
    tax_type: Optional[str] = None
    is_provisional: bool = False
    total_tax_fixed: Optional[float] = None
    prepayments_made: Optional[float] = None
    refund_or_payment: Optional[float] = None # Negative = Refund
    payment_due_date: Optional[date] = None

class InvoiceData(BaseModel):
    invoice_number: Optional[str] = None
    order_number: Optional[str] = None
    payment_terms: Optional[str] = None
    due_date: Optional[date] = None
    tax_amounts: List[Dict[str, float]] = [] # {"rate": 19, "amount": 100}
    net_amount: Optional[float] = None
    gross_amount: Optional[float] = None
    currency: str = "EUR"

# --- List Items ---

class LineItem(BaseModel):
    pos: Optional[int] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    quantity_unit: Optional[str] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    # Logistics additions
    quantity_delivered: Optional[float] = None
    quantity_open: Optional[float] = None
    batch_number: Optional[str] = None

# --- New Specific Data Blocks ---

class VehicleData(BaseModel):
    vin: Optional[str] = None # FIN
    license_plate: Optional[str] = None # Kennzeichen
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    first_registration_date: Optional[date] = None
    owner: Optional[str] = None

class MedicalData(BaseModel):
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    diagnosis_code: Optional[str] = None # ICD-10
    treatment_date: Optional[date] = None
    medication_list: List[str] = []

class InsuranceData(BaseModel):
    insurance_number: Optional[str] = None # Versicherungsscheinnummer
    insurance_type: Optional[str] = None # Haftpflicht, Hausrat...
    coverage_amount: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class UtilityData(BaseModel):
    meter_id: Optional[str] = None
    consumption_kwh: Optional[float] = None
    consumption_m3: Optional[float] = None
    reading_date: Optional[date] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None

class ExpenseData(BaseModel):
    employee_id: Optional[str] = None
    cost_center: Optional[str] = None
    trip_start: Optional[datetime] = None
    trip_end: Optional[datetime] = None
    total_reimbursable: Optional[float] = None

class BankTransaction(BaseModel):
    date: Optional[date] = None
    valuta: Optional[date] = None
    counterparty_name: Optional[str] = None
    purpose: Optional[str] = None
    amount: Optional[float] = None
    transaction_type: Optional[str] = None

class ContractData(BaseModel):
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    cancellation_period: Optional[str] = None # e.g. "3 months to year end"
    next_termination_date: Optional[date] = None
    contract_partner: Optional[str] = None
    contract_number: Optional[str] = None



# --- Main Wrapper ---

class CanonicalEntity(BaseModel):
    doc_type: DocType
    doc_id: Optional[str] = None
    doc_date: Optional[date] = None
    parties: Parties = Field(default_factory=Parties)
    tags_and_flags: List[str] = []
    
    # Polymorphic Specific Data (Union usually harder in simple JSON, we use optional blocks)
    # Ideally use Pydantic Discriminator, but for simple storage:
    specific_data: Dict[str, Any] = {} 
    
    # Polymorphic List Data
    list_data: List[Dict[str, Any]] = [] # Items or Transactions

    # Source Link
    source_doc_uuid: str 
    page_range: List[int] = [] # [0, 1]
