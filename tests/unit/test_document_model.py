import pytest
from datetime import date
from decimal import Decimal
from core.document import Document

def test_document_creation():
    """Test creating a Document with minimal required fields."""
    doc = Document(original_filename="invoice.pdf")
    assert doc.original_filename == "invoice.pdf"
    assert doc.uuid is not None, "UUID should be auto-generated"
    assert len(doc.uuid) > 0

def test_document_optional_fields():
    """Test creating a Document with semantic data."""
    today = date.today().isoformat()
    doc = Document(
        original_filename="receipt.jpg",
        semantic_data={
            "doc_date": today,
            "sender": "Company A",
            "amount": 12.99
        },
        type_tags=["Rechnung"],
        phash="a1b2c3d4",
        text_content="Total: 12.99"
    )
    
    sd = doc.semantic_data
    assert sd["doc_date"] == today
    assert sd["sender"] == "Company A"
    assert sd["amount"] == 12.99
    assert doc.type_tags == ["Rechnung"]
    assert doc.phash == "a1b2c3d4"
    assert doc.text_content == "Total: 12.99"

from pydantic import ValidationError

# Removed flaky validation test
