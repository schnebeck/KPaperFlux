"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/models/types.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Centralized enumeration and type definitions.
------------------------------------------------------------------------------
"""

from enum import Enum


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
