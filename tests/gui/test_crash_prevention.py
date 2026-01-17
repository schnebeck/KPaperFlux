import pytest
from unittest.mock import MagicMock
from PyQt6.QtCore import Qt
from gui.document_list import DocumentListWidget
from core.database import DatabaseManager
from core.document import Document
from decimal import Decimal

@pytest.fixture
def mock_db():
    db = MagicMock(spec=DatabaseManager)
    
    # Mock get_all_documents to return a valid document
    doc = Document(
        uuid="test-uuid",
        original_filename="test.pdf",
        amount=Decimal("10.00"),
        tax_rate=Decimal("19.0"),
        gross_amount=Decimal("11.90")
    )
    db.get_all_documents.return_value = [doc]
    db.search_documents.return_value = [doc]
    
    # Mock extra keys
    db.get_available_extra_keys.return_value = ["stamps.cost_center"]
    
    return db

def test_document_list_signal_signature(qtbot, mock_db):
    """
    Verify that document_count_changed emits (int, int).
    This prevents the TypeError: MainWindow.update_status_bar() missing 1 required positional argument
    """
    widget = DocumentListWidget(mock_db)
    qtbot.addWidget(widget)
    
    with qtbot.waitSignal(widget.document_count_changed, check_params_cb=lambda v, t: isinstance(v, int) and isinstance(t, int)) as blocker:
        widget.refresh_list()
        
    assert blocker.signal_triggered, "Signal not triggered with correct signature (int, int)"

def test_search_documents_columns(mock_db):
    """
    Verify that search_documents returns valid Document objects and doesn't crash on column mismatch.
    This simulates the 'Search Error: no such column: tax_id' fix.
    """
    # Create a REAL DatabaseManager (in-memory) to test SQL validity
    real_db = DatabaseManager(":memory:")
    real_db.init_db()
    
    # Insert a dummy document
    doc = Document(
        original_filename="test.pdf",
        text_content="invoice",
        amount=Decimal("100.00"),
        tax_rate=Decimal("19.00")
    )
    real_db.insert_document(doc)
    
    # Perform Search
    results = real_db.search_documents(text_query="invoice")
    
    assert len(results) == 1
    assert results[0].original_filename == "test.pdf"
    assert results[0].tax_rate == Decimal("19.00")
    
    real_db.close()

def test_mainwindow_compatibility(mock_db, qtbot):
    """
    Verify methods required by MainWindow are present.
    Regression test for AttributeError: 'DocumentListWidget' object has no attribute 'rowCount'
    """
    widget = DocumentListWidget(mock_db)
    qtbot.addWidget(widget)
    
    # MainWindow usage: self.list_widget.rowCount()
    assert hasattr(widget, 'rowCount'), "Missing rowCount() method required by MainWindow"
    assert widget.rowCount() == 1
    
    # MainWindow usage: self.list_widget.selectedItems()
    assert hasattr(widget, 'selectedItems'), "Missing selectedItems() method required by MainWindow"
    assert widget.selectedItems() == []

def test_column_widths(mock_db, qtbot):
    """
    Verify that columns have reasonable widths (> 0) after initialization.
    Regression test for 'Squashed Columns' issue.
    """
    widget = DocumentListWidget(mock_db)
    qtbot.addWidget(widget)
    
    header = widget.tree.header()
    col_count = widget.tree.columnCount()
    
    # Check visible columns (e.g. 0-6)
    for i in range(7):
        if not header.isSectionHidden(i):
            assert header.sectionSize(i) > 0, f"Column {i} has 0 width (Squashed)"

def test_mainwindow_extended_compatibility(mock_db, qtbot):
    """
    Verify additional compatibility methods required by MainWindow.
    Regression for selectRow and item(row, col).
    """
    widget = DocumentListWidget(mock_db)
    qtbot.addWidget(widget)
    
    # Wait for refresh
    assert widget.rowCount() == 1
    
    # Test selectRow
    assert hasattr(widget, 'selectRow'), "Missing selectRow() method"
    widget.selectRow(0)
    assert len(widget.selectedItems()) == 1
    
    # Test item(row, col)
    assert hasattr(widget, 'item'), "Missing item() method"
    item = widget.item(0, 0)
    assert item is not None
    assert item.isSelected() # verified by selectRow above
