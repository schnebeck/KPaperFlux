"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/models/identity.py
Version:        1.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Defines the IdentityProfile data model for representing users
                and business entities. Used for direction classification and 
                address verification via fuzzy matching.
------------------------------------------------------------------------------
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class IdentityProfile(BaseModel):
    """
    Structured Identity Profile used for intelligent direction classification 
    and document validation. Contains names, aliases, and specific identifiers 
    like VAT IDs or IBANs.
    """

    # Official Name of the person or entity
    name: Optional[str] = None

    # Variations or abbreviations of the main name
    aliases: List[str] = Field(default_factory=list)

    # Explicit company details if applicable
    company_name: Optional[str] = None
    company_aliases: List[str] = Field(default_factory=list)

    # Atomic parts of the address (e.g., ["Musterstraße", "12345", "Berlin"])
    address_keywords: List[str] = Field(default_factory=list)

    # Tax identifiers and financial details
    vat_id: Optional[str] = None
    iban: List[str] = Field(default_factory=list)
