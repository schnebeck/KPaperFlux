
import pytest
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import QTableWidget
from gui.filter_widget import FilterWidget
from gui.document_list import DocumentListWidget
from core.database import DatabaseManager
from core.document import Document

@pytest.fixture
def db_manager(tmp_path):
    db_path = tmp_path / "test.db"
    db = DatabaseManager(str(db_path))
    db.init_db()
    return db

@pytest.fixture
def filled_db(db_manager):
    # Insert dummy docs
    doc1 = Document(uuid="uuid-1", original_filename="doc1.pdf", doc_date="2023-01-01", type_tags=["Invoice"], tags=["paid"])
    doc2 = Document(uuid="uuid-2", original_filename="doc2.pdf", doc_date="2023-06-01", type_tags=["Receipt"], tags=["food"])
    doc3 = Document(uuid="uuid-3", original_filename="doc3.pdf", doc_date="2024-01-01", type_tags=["Invoice"], tags=["unpaid"])
    
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    db_manager.insert_document(doc3)
    return db_manager

def test_filter_widget_signal(qtbot):
    widget = FilterWidget()
    qtbot.addWidget(widget)
    
    with qtbot.waitSignal(widget.filter_changed) as blocker:
        widget.enable_date.setChecked(True)
        widget.date_from.setDate(QDate(2023, 1, 1))
        widget.date_to.setDate(QDate(2023, 12, 31))
        widget.emit_filter()
        
    criteria = blocker.args[0]
    assert criteria['date_from'] == "2023-01-01"
    
def test_document_list_filtering(qtbot, filled_db):
    widget = DocumentListWidget(filled_db)
    qtbot.addWidget(widget)
    widget.refresh_list()
    
    assert widget.tree.topLevelItemCount() == 3
    assert not widget.tree.topLevelItem(0).isHidden()
    assert not widget.tree.topLevelItem(1).isHidden()
    assert not widget.tree.topLevelItem(2).isHidden()
    
    # Filter by Date (2023 only)
    criteria = {'date_from': '2023-01-01', 'date_to': '2023-12-31'}
    widget.apply_filter(criteria)
    
    # Rows: 0 (2023-01-01), 1 (2023-06-01), 2 (2024-01-01)
    # Row 2 should be hidden
    hidden_count = 0
    for r in range(3):
        if widget.tree.topLevelItem(r).isHidden():
             hidden_count += 1
             
    assert hidden_count == 1 # Doc 3 hidden
    
    # Filter by Type (Invoice)
    criteria = {'type': 'Invoice'}
    widget.apply_filter(criteria)
    
    # Doc 1 (Invoice), Doc 2 (Receipt), Doc 3 (Invoice)
    # Doc 2 should be hidden. (Note: Previous hidden state cleared? No, apply_filter loops all rows and resets)
    # apply_filter logic sets setRowHidden(row, not show). So it resets previous state.
    
    # Check
    # row 0: Invoice -> Show
    # row 1: Receipt -> Hide
    # row 2: Invoice -> Show
    
    # Note: row indices might correspond to sorted order? Sorting is disabled/enabled.
    # refresh_list populates row 0, 1, 2 in order of get_all_documents (usually insertion or query order).
    # Assuming order preserved for test.
    
    item0 = widget.tree.topLevelItem(0).text(6) # Type Tags
    item1 = widget.tree.topLevelItem(1).text(6)
    
    # Ensure items match assumption
    assert "Invoice" in item0
    assert widget.tree.topLevelItem(0).isHidden() == False
    
    assert "Receipt" in item1
    assert widget.tree.topLevelItem(1).isHidden() == True
    
    # Filter by Tags ("paid")
    criteria = {'tags': 'paid'}
    widget.apply_filter(criteria)
    
    # Doc 1 -> paid -> Show
    # Doc 2 -> food -> Hide
    # Doc 3 -> unpaid -> Show (unpaid contains paid)
    
    assert widget.tree.topLevelItem(0).isHidden() == False
    assert widget.tree.topLevelItem(1).isHidden() == True
    assert widget.tree.topLevelItem(2).isHidden() == False
