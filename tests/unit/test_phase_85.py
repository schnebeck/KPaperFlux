
import pytest
from unittest.mock import MagicMock
from core.metadata_normalizer import MetadataNormalizer
from core.document import Document

# Mock Data
TYPE_DEF = {
    "types": {
        "Invoice": {
            "fields": [
                {
                    "id": "invoice_number",
                    "strategies": [
                        {"type": "json_path", "path": "summary.invoice_number"}
                    ]
                },
                {
                    "id": "nested_field",
                    "strategies": [
                        {"type": "json_path", "path": "summary.nested.field"}
                    ]
                }
            ]
        }
    }
}

@pytest.fixture
def mock_config(monkeypatch):
    monkeypatch.setattr(MetadataNormalizer, "get_config", lambda: TYPE_DEF)

def test_update_field_simple(mock_config):
    doc = Document(uuid="123", original_filename="test.pdf", doc_type="Invoice")
    doc.semantic_data = {"summary": {"invoice_number": "OLD_123"}}
    
    assert MetadataNormalizer.update_field(doc, "invoice_number", "NEW_456")
    
    # Check Update
    assert doc.semantic_data["summary"]["invoice_number"] == "NEW_456"

def test_update_field_creates_nested_structure(mock_config):
    doc = Document(uuid="123", original_filename="test.pdf", doc_type="Invoice")
    doc.semantic_data = {} # Empty
    
    assert MetadataNormalizer.update_field(doc, "nested_field", "VALUE")
    
    assert "summary" in doc.semantic_data
    assert "nested" in doc.semantic_data["summary"]
    assert doc.semantic_data["summary"]["nested"]["field"] == "VALUE"

def test_update_field_wrong_type(mock_config):
    doc = Document(uuid="123", original_filename="test.pdf", doc_type="Contract") # Not defined
    assert not MetadataNormalizer.update_field(doc, "invoice_number", "X")
    
