
import pytest
from core.metadata_normalizer import MetadataNormalizer
from core.semantic_translator import SemanticTranslator
from PyQt6.QtCore import QCoreApplication
import sys

# Ensure QApp exists for tr()
@pytest.fixture(scope="session")
def qapp():
    if not QCoreApplication.instance():
        app = QCoreApplication(sys.argv)
        yield app
    else:
        yield QCoreApplication.instance()

def test_metadata_normalizer_config_loading():
    """Verify that the normalizer loads the new Invoice fields."""
    config = MetadataNormalizer.get_config()
    assert "types" in config
    assert "Invoice" in config["types"]
    
    invoice_def = config["types"]["Invoice"]
    fields = {f["id"]: f for f in invoice_def["fields"]}
    
    # Check for new fields
    assert "tax_amount" in fields
    assert "tax_rate" in fields
    assert "iban" in fields
    assert "cost_center" in fields
    assert "incoterms" in fields
    
    # Check strategies
    tax_field = fields["tax_amount"]
    strategies = {s["type"]: s for s in tax_field["strategies"]}
    assert "json_path" in strategies
    assert strategies["json_path"]["path"] == "summary.tax_amount"
    assert "fuzzy_key" in strategies
    assert "MwSt" in strategies["fuzzy_key"]["aliases"]

def test_semantic_translator_keys(qapp):
    """Verify that the translator handles the new keys."""
    translator = SemanticTranslator.instance()
    
    # Check new keys
    assert translator.translate("field_tax_amount") == "Tax Amount"  # Default English
    assert translator.translate("field_iban") == "IBAN"
    assert translator.translate("field_incoterms") == "Incoterms"
    
    # Check fallback
    assert translator.translate("unknown_key") == "unknown_key"
