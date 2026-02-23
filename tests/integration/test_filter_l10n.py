import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTranslator, QLocale
from gui.widgets.filter_condition import FilterConditionWidget
from core.filter_token_registry import FilterTokenRegistry
from core.semantic_translator import SemanticTranslator
import sys
import os

@pytest.fixture
def app():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app

def test_filter_condition_l10n_ui(app):
    """
    Verify that FilterConditionWidget resolves tokens to localized labels
    based on the current application translator.
    """
    # 1. English (Default)
    widget = FilterConditionWidget()
    
    # Set to 'doc_date' token
    widget.set_condition({"field": "doc_date", "op": "equals", "value": "2023-01-01"})
    
    # Verify button text in English
    assert widget.btn_field_selector.text() == "Date"
    
    # 2. Simulate German Translation
    # In a real app, MainWindow loads the .qm file. 
    # Here we mock the behavior by loading the qm if possible, 
    # or just verifying that retranslate_ui calls the translator.
    
    translator = QTranslator()
    qm_path = "resources/l10n/de/gui_strings.qm"
    if os.path.exists(qm_path):
        translator.load(qm_path)
        app.installTranslator(translator)
        
        # Trigger retranslation
        widget.retranslate_ui()
        
        # Verify button text in German
        # Based on my grep, it's 'Datum'
        assert widget.btn_field_selector.text() == "Datum"
        
        # Cleanup
        app.removeTranslator(translator)
    else:
        # If QM is missing, we at least verify that it still shows the key or English
        widget.retranslate_ui()
        assert widget.btn_field_selector.text() == "Date"

def test_filter_condition_persistence_agnostic(app):
    """
    Verify that get_condition ALWAYS returns the token, regardless of UI label.
    """
    widget = FilterConditionWidget()
    
    # Set UI to something (manually or via menu)
    # We use the token internally
    widget._set_field("doc_date", "Some Localized Label")
    
    cond = widget.get_condition()
    assert cond["field"] == "doc_date" # MUST be the token
    
    # Even if we change the display name
    widget.field_name = "Quittungsdatum"
    cond = widget.get_condition()
    assert cond["field"] == "doc_date"
