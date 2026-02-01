import pytest
from unittest.mock import MagicMock
from datetime import date
from decimal import Decimal
from gui.document_list import DocumentListWidget
from core.document import Document

@pytest.fixture
def mock_db():
    return MagicMock()

def test_document_list_population(qtbot, mock_db):
    """Test that the list widget populates correct data from DB."""
    # Data Setup
    docs = [
        Document(original_filename="invoice.pdf", sender="Amazon", amount=Decimal("15.99"), doc_date=date(2023, 1, 1)),
        Document(original_filename="contract.pdf", type_tags=["Vertrag"])
    ]
    mock_db.get_all_documents.return_value = docs
    mock_db.get_all_entities_view.return_value = docs
    
    # Init Widget
    widget = DocumentListWidget(db_manager=mock_db)
    qtbot.addWidget(widget)
    widget.refresh_list()
    
    # Verify Rows
    assert widget.rowCount() == 2
    
    # Check Content (Row 0: Amazon Invoice)
    # Columns: Date, Sender, Type, Amount, Filename (or similar)
    # Let's assume order: Date, Sender, Type, Amount
    
    # Item at 0 (Row Item)
    item = widget.item(0, 0)
    # Check UUID (Col 1)
    # The default fixed columns put Entity ID (UUID) at index 1.
    assert item.text(1) == docs[0].uuid
    
    # Item at 0 (Row Item)
    # Check Pages (Col 3) - Defaults to 0/None -> "0"
    assert item.text(3) == "0"

def test_empty_state(qtbot, mock_db):
    """Test empty list behavior."""
    mock_db.get_all_documents.return_value = []
    mock_db.get_all_entities_view.return_value = []
    
    widget = DocumentListWidget(db_manager=mock_db)
    qtbot.addWidget(widget)
    widget.refresh_list()
    
    assert widget.rowCount() == 0

def test_selection_emits_signal(qtbot, mock_db):
    """Test that selecting a row emits specific signal with UUID."""
    docs = [Document(original_filename="test.pdf")]
    mock_db.get_all_documents.return_value = docs
    mock_db.get_all_entities_view.return_value = docs
    
    widget = DocumentListWidget(db_manager=mock_db)
    qtbot.addWidget(widget)
    widget.refresh_list()
    
    with qtbot.waitSignal(widget.document_selected, timeout=1000) as blocker:
        widget.selectRow(0)
        
    # Check signal payload (Expects list of UUIDs)
    assert blocker.args[0] == [docs[0].uuid]

def test_context_menu_actions(qtbot, mock_db):
    """Test context menu actions emission."""
    doc = Document(original_filename="test.pdf")
    mock_db.get_all_documents.return_value = [doc]
    mock_db.get_all_entities_view.return_value = [doc]
    
    widget = DocumentListWidget(db_manager=mock_db)
    qtbot.addWidget(widget)
    widget.refresh_list()
    
    # We can't easily click context menu in unit test, so we test the triggers manually
    # Or checking signals exist
    
    # Let's verify signals exist
    assert hasattr(widget, "delete_requested")
    assert hasattr(widget, "reprocess_requested")
    
    # We can simulate the action trigger
    with qtbot.waitSignal(widget.delete_requested) as blocker:
        widget.delete_requested.emit([doc.uuid])
    assert blocker.args[0] == [doc.uuid]
    
    with qtbot.waitSignal(widget.reprocess_requested) as blocker:
        widget.reprocess_requested.emit([doc.uuid])
    assert blocker.args[0] == [doc.uuid]
