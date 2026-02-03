
import pytest
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import QTableWidget
from gui.filter_widget import FilterWidget
from gui.document_list import DocumentListWidget
from core.database import DatabaseManager
from core.models.virtual import VirtualDocument as Document
from core.models.semantic import SemanticExtraction, MetaHeader

@pytest.fixture
def db_manager(tmp_path):
    db_path = tmp_path / "test.db"
    db = DatabaseManager(str(db_path))
    db.init_db()
    return db

@pytest.fixture
def filled_db(db_manager):
    # Insert dummy docs
    doc1 = Document(
        uuid="uuid-1", 
        original_filename="doc1.pdf", 
        semantic_data=SemanticExtraction(meta_header=MetaHeader(doc_date="2023-01-01")),
        type_tags=["Invoice"], 
        tags=["paid"]
    )
    doc2 = Document(
        uuid="uuid-2", 
        original_filename="doc2.pdf", 
        semantic_data=SemanticExtraction(meta_header=MetaHeader(doc_date="2023-06-01")),
        type_tags=["Receipt"], 
        tags=["food"]
    )
    doc3 = Document(
        uuid="uuid-3", 
        original_filename="doc3.pdf", 
        semantic_data=SemanticExtraction(meta_header=MetaHeader(doc_date="2024-01-01")),
        type_tags=["Invoice"], 
        tags=["unpaid"]
    )
    
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
    
    # Discovery phase
    header_labels = [widget.tree.headerItem().text(i) for i in range(widget.tree.columnCount())]
    def get_col(label): return header_labels.index(label)
    
    def get_row_by_uuid(uuid):
        for i in range(widget.tree.topLevelItemCount()):
            if widget.tree.topLevelItem(i).data(1, Qt.ItemDataRole.UserRole) == uuid:
                return widget.tree.topLevelItem(i)
        return None

    col_type = get_col("Type Tags")
    
    assert widget.tree.topLevelItemCount() == 3
    
    # 1. Date Filter (2023 only)
    # doc1 (2023-01-01), doc2 (2023-06-01), doc3 (2024-01-01)
    criteria = {'date_from': '2023-01-01', 'date_to': '2023-12-31'}
    widget.apply_filter(criteria)
    
    assert get_row_by_uuid("uuid-1").isHidden() == False
    assert get_row_by_uuid("uuid-2").isHidden() == False
    assert get_row_by_uuid("uuid-3").isHidden() == True
    
    # 2. Filter by Type (Invoice)
    # doc1 (Invoice), doc2 (Receipt), doc3 (Invoice)
    criteria = {'type': 'Invoice'}
    widget.apply_filter(criteria)
    
    assert "Invoice" in get_row_by_uuid("uuid-1").text(col_type)
    assert get_row_by_uuid("uuid-1").isHidden() == False
    assert "Receipt" in get_row_by_uuid("uuid-2").text(col_type)
    assert get_row_by_uuid("uuid-2").isHidden() == True
    assert get_row_by_uuid("uuid-3").isHidden() == False
    
    # 3. Filter by Tags ("paid")
    # doc1 (paid), doc2 (food), doc3 (unpaid) -> unpaid contains paid!
    criteria = {'tags': 'paid'}
    widget.apply_filter(criteria)
    
    assert get_row_by_uuid("uuid-1").isHidden() == False
    assert get_row_by_uuid("uuid-2").isHidden() == True
    assert get_row_by_uuid("uuid-3").isHidden() == False
