"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/gui/test_dynamic_tabs.py
Version:        1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Gemini 3pro
Description:    Test suite for universal dynamic tab visibility in MetadataEditor.
------------------------------------------------------------------------------
"""
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from gui.metadata_editor import MetadataEditorWidget
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, WorkflowInfo

@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])

@pytest.fixture
def editor(qtbot):
    widget = MetadataEditorWidget(db_manager=MagicMock())
    qtbot.addWidget(widget)
    return widget

def test_minimal_tabs_visibility(qtbot, editor):
    """Verify that only core tabs are visible for a minimal document."""
    doc = VirtualDocument(uuid="doc-min")
    # Setting sender name via nested extraction model (sender_name property is read-only)
    doc.semantic_data = SemanticExtraction()
    doc.semantic_data.meta_header.sender.name = "Min Sender"
    
    editor.display_document(doc)
    
    # 0: General, 1: Analysis should be visible
    assert editor.tab_widget.isTabVisible(0)
    assert editor.tab_widget.isTabVisible(1)
    
    # Others should be hidden
    assert not editor.tab_widget.isTabVisible(2) # Payment
    assert not editor.tab_widget.isTabVisible(3) # Subscriptions
    assert not editor.tab_widget.isTabVisible(4) # Stamps
    assert not editor.tab_widget.isTabVisible(5) # Semantic Table

def test_payment_tab_visibility(qtbot, editor):
    """Verify payment tab appears for invoices or bank data."""
    doc = VirtualDocument(uuid="doc-pay")
    doc.type_tags = ["INVOICE"]
    doc.semantic_data = SemanticExtraction()
    
    editor.display_document(doc)
    assert editor.tab_widget.isTabVisible(2)
    
    # Non-invoice with IBAN
    doc2 = VirtualDocument(uuid="doc-iban")
    doc2.semantic_data = SemanticExtraction()
    doc2.semantic_data.meta_header.sender.iban = "DE123456789"
    
    editor.display_document(doc2)
    assert editor.tab_widget.isTabVisible(2)

def test_subscription_tab_visibility(qtbot, editor):
    """Verify subscription tab appears for contracts or recurring data."""
    doc = VirtualDocument(uuid="doc-sub")
    doc.type_tags = ["CONTRACT"]
    doc.semantic_data = SemanticExtraction()
    
    editor.display_document(doc)
    assert editor.tab_widget.isTabVisible(3)
    
    # Recurring flag
    doc2 = VirtualDocument(uuid="doc-rec")
    doc2.semantic_data = SemanticExtraction()
    doc2.semantic_data.bodies["subscription_info"] = {"is_recurring": True}
    
    editor.display_document(doc2)
    assert editor.tab_widget.isTabVisible(3)

def test_stamps_tab_visibility(qtbot, editor):
    """Verify stamps tab appears if stamps are present."""
    doc = VirtualDocument(uuid="doc-stamps")
    doc.semantic_data = SemanticExtraction(
        visual_audit={"layer_stamps": [{"type": "STAMP", "text": "Paid"}]}
    )
    
    editor.display_document(doc)
    assert editor.tab_widget.isTabVisible(4)
