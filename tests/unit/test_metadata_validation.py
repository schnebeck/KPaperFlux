"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_metadata_validation.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Unit tests for metadata normalization and validation,
                specifically focusing on IBAN and BIC cleaning.
------------------------------------------------------------------------------
"""

import pytest
from core.models.semantic import SemanticExtraction, MetaHeader, AddressInfo

def test_iban_bic_normalization():
    """Test that IBAN and BIC are cleaned from spaces and formatted correctly."""
    
    # Arange: Create a semantic extraction with messy bank data
    sender = AddressInfo(
        name="Test Corp",
        iban="DE12 3456 7890 1234 5678 90",
        bic="ABC DEF GH XXX",
        bank_name="Test Bank"
    )
    header = MetaHeader(sender=sender)
    extraction = SemanticExtraction(meta_header=header)
    
    # Act: Normalize (we expect this function to exist or be called during validation)
    # For now, we will implement this logic in a validator or property
    
    # ASSERT before implementation (will fail if not implemented)
    assert extraction.meta_header.sender.iban == "DE12345678901234567890"
    assert extraction.meta_header.sender.bic == "ABCDEFGHXXX"
    assert extraction.meta_header.sender.bank_name == "Test Bank"

def test_iban_checksum_validation():
    """Test that invalid IBANs are detected (optional/future proofing)."""
    # This might be a separate utility or part of the model validation
    pass
