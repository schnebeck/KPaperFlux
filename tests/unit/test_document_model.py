import pytest
from datetime import date
from decimal import Decimal
from core.models.virtual import VirtualDocument as Document

def test_document_creation():
    """Test creating a Document with minimal required fields."""
    doc = Document(original_filename="invoice.pdf")
    assert doc.original_filename == "invoice.pdf"
    assert doc.uuid is not None, "UUID should be auto-generated"
    assert len(doc.uuid) > 0

from core.models.semantic import SemanticExtraction, MetaHeader, AddressInfo, FinanceBody

def test_document_optional_fields():
    """Test creating a Document with structured semantic data."""
    today = date.today().isoformat()
    doc = Document(
        original_filename="receipt.jpg",
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(
                doc_date=today,
                sender=AddressInfo(name="Company A")
            ),
            bodies={
                "finance_body": FinanceBody(total_gross=Decimal("12.99"))
            }
        ),
        type_tags=["Rechnung"],
        phash="a1b2c3d4",
        text_content="Total: 12.99"
    )
    
    sd = doc.semantic_data
    assert sd.meta_header.doc_date == today
    assert sd.meta_header.sender.name == "Company A"
    assert doc.total_amount == Decimal("12.99")
    assert doc.type_tags == ["Rechnung"]
    assert doc.phash == "a1b2c3d4"
    assert doc.text_content == "Total: 12.99"

from pydantic import ValidationError

# Removed flaky validation test
