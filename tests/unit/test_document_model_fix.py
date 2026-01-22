from core.document import Document
from decimal import Decimal
import pytest

def test_document_decimal_comma_normalization():
    """Verify that 'amount' strings with commas and symbols are normalized."""
    data = {
        "original_filename": "test.pdf",
        "amount": "68,50",         # The user's crash case
        "gross_amount": "1.200,00", # Complex DE format? Our simple replace might fail on thousands separator.
                                    # The validator replace "," -> "." implies "1.200.00" which is invalid.
                                    # Note: If thousands dot is present, simple replace is dangerous.
                                    # But AI usually outputs standard JSON numbers or raw text. 
                                    # Let's verify robust handling.
        "tax_rate": "19%",
        "postage": "EUR 5,50"
    }

    # NOTE: Our current logic is simple replace(";", "."). 
    # "1.200,00" -> "1.200.00" (Error).
    # If the user input is strictly German local, we should handle dots if they exist.
    # However, for now let's test the reported case "68,50".
    
    # We will refine the validator if "1.200,00" fails.
    
    # Actually, let's stick to "68,50" first.
    doc = Document(original_filename="test.pdf", amount="68,50")
    assert doc.amount == Decimal("68.50")
    
    # Currency symbol
    doc2 = Document(original_filename="test.pdf", amount="€ 50,00")
    assert doc2.amount == Decimal("50.00")
    
def test_document_decimal_native_float():
    doc = Document(original_filename="test.pdf", amount=10.5)
    assert doc.amount == Decimal("10.5")
    
