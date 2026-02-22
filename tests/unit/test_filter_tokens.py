import pytest
from core.filter_token_registry import FilterTokenRegistry
from core.semantic_translator import SemanticTranslator
from PyQt6.QtWidgets import QApplication
import sys

# Need a QApplication for QObject.tr
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

def test_token_registry_singleton():
    reg1 = FilterTokenRegistry.instance()
    reg2 = FilterTokenRegistry.instance()
    assert reg1 is reg2

def test_standard_tokens_exist():
    registry = FilterTokenRegistry.instance()
    tokens = registry.get_all_tokens()
    assert len(tokens) > 0
    
    # Check some specific tokens
    doc_date = registry.get_token("doc_date")
    assert doc_date is not None
    assert doc_date.category == "basis"
    assert doc_date.label_key == "field_doc_date"

def test_token_translation():
    translator = SemanticTranslator.instance()
    label = translator.translate("field_doc_date")
    # Default is English in the code
    assert label == "Document Date"
    
def test_category_filtering():
    registry = FilterTokenRegistry.instance()
    basis_tokens = registry.get_tokens_by_category("basis")
    assert len(basis_tokens) > 0
    for t in basis_tokens:
        assert t.category == "basis"

def test_beautify_key():
    translator = SemanticTranslator.instance()
    # Case 1: Known translation (stripping prefix)
    assert translator.beautify_key("semantic:doc_date") == "Document Date"
    # Case 2: Technical segment mapping
    assert translator.beautify_key("semantic:bodies.finance_body") == "Contents > Financial Data"
    # Case 3: Fallback (Titulize)
    assert translator.beautify_key("something_custom") == "Something Custom"
    # Case 4: Deep nesting
    assert translator.beautify_key("a.b.c") == "A > B > C"
