import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from datetime import date
from gui.document_list import DocumentListWidget
from core.database import DatabaseManager
from core.document import Document

@pytest.fixture
def db_manager():
    """Create a temporary in-memory database for testing."""
    manager = DatabaseManager(":memory:")
    manager.init_db()
    return manager

@pytest.fixture
def doc_list_widget(db_manager, qapp):
    # Ensure QApp exists (qapp fixture does this)
    widget = DocumentListWidget(db_manager)
    return widget

def test_refresh_preserves_basic_filter(doc_list_widget, db_manager):
    # Setup Data
    doc1 = Document(uuid="u1", original_filename="doc1.pdf", doc_date="2023-01-01", amount=10.0, tags="tag1")
    doc2 = Document(uuid="u2", original_filename="doc2.pdf", doc_date="2023-02-01", amount=20.0, tags="tag2")
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    
    doc_list_widget.refresh_list()
    assert doc_list_widget.tree.topLevelItemCount() == 2
    
    # 1. Apply Basic Filter (Tag)
    criteria = {'tags': 'tag1'}
    doc_list_widget.apply_filter(criteria)
    
    # Verify Filtering
    visible_count = 0
    for i in range(doc_list_widget.tree.topLevelItemCount()):
        if not doc_list_widget.tree.topLevelItem(i).isHidden():
            visible_count += 1
            
    assert visible_count == 1
    assert doc_list_widget.current_filter == criteria
    
    # 2. Refresh List
    doc_list_widget.refresh_list()
    
    # Verify Filter Persisted
    assert doc_list_widget.tree.topLevelItemCount() == 2 # Total
    
    visible_after_refresh = 0
    for i in range(doc_list_widget.tree.topLevelItemCount()):
        if not doc_list_widget.tree.topLevelItem(i).isHidden():
            visible_after_refresh += 1
            
    assert visible_after_refresh == 1, "Filter should still be active after refresh"
    assert not doc_list_widget.tree.topLevelItem(0).isHidden() # u1 (tag1) should be visible
    # Note: order matches insertion if not sorted, doc1 is first usually
    
def test_refresh_preserves_advanced_filter(doc_list_widget, db_manager):
    # Setup Data
    doc1 = Document(uuid="u1", original_filename="match.pdf", amount=100)
    doc2 = Document(uuid="u2", original_filename="nomatch.pdf", amount=50)
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    
    doc_list_widget.refresh_list()
    
    # 1. Apply Advanced Filter (SQL/JSON logic simulation)
    # Mocking search_documents_advanced to return only doc1
    # Actually checking if logic persists the query object and calls DB
    
    # Query structure matching DatabaseManager._build_advanced_sql
    query = {
        "operator": "AND",
        "conditions": [
            {"field": "amount", "op": "gte", "value": 80}
        ]
    }
    doc_list_widget.apply_advanced_filter(query)
    
    assert doc_list_widget.current_advanced_query == query
    assert doc_list_widget.tree.topLevelItemCount() == 1 # Only u1
    
    # 2. Refresh List
    doc_list_widget.refresh_list()
    
    assert doc_list_widget.tree.topLevelItemCount() == 1
    assert doc_list_widget.documents_cache["u1"].original_filename == "match.pdf"
