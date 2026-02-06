import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from datetime import date
from decimal import Decimal
from gui.document_list import DocumentListWidget
from core.database import DatabaseManager
from core.models.virtual import VirtualDocument as Document
from core.models.semantic import SemanticExtraction, MetaHeader, AddressInfo, FinanceBody, MonetarySummation

@pytest.fixture
def db_manager():
    """Create a temporary in-memory database for testing."""
    manager = DatabaseManager(":memory:")
    manager.init_db()
    return manager

@pytest.fixture
def doc_list_widget(db_manager, qtbot):
    widget = DocumentListWidget(db_manager)
    qtbot.addWidget(widget)
    return widget

def get_visible_count(widget):
    count = 0
    for i in range(widget.tree.topLevelItemCount()):
        if not widget.tree.topLevelItem(i).isHidden():
            count += 1
    return count

def test_refresh_preserves_basic_filter(doc_list_widget, db_manager):
    """Verifies that simple tag filters are preserved when the list is refreshed."""
    # Setup Data using exact ZUGFeRD structure
    doc1 = Document(
        uuid="u1", 
        original_filename="doc1.pdf", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(doc_date="2023-01-01"),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("10.0"))
                )
            }
        ),
        tags=["tag1"]
    )
    doc2 = Document(
        uuid="u2", 
        original_filename="doc2.pdf", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(doc_date="2023-02-01"),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("20.0"))
                )
            }
        ),
        tags=["tag2"]
    )
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    
    doc_list_widget.refresh_list()
    assert get_visible_count(doc_list_widget) == 2
    
    # 1. Apply Basic Filter (Tag)
    criteria = {'tags': 'tag1'}
    doc_list_widget.apply_filter(criteria)
    
    # Verify Filtering
    assert get_visible_count(doc_list_widget) == 1
    assert doc_list_widget.current_filter == criteria
    
    # 2. Refresh List
    doc_list_widget.refresh_list()
    
    # Verify Filter Persisted
    assert get_visible_count(doc_list_widget) == 1
    # u1 should be the one visible
    item = doc_list_widget.tree.topLevelItem(0)
    # Since doc2 is hidden, only doc1 is visible. 
    # But populate_tree might have reordered. 
    # Check all visible items.
    visible_uuids = [doc_list_widget.tree.topLevelItem(i).data(1, Qt.ItemDataRole.UserRole) 
                     for i in range(doc_list_widget.tree.topLevelItemCount()) 
                     if not doc_list_widget.tree.topLevelItem(i).isHidden()]
    assert "u1" in visible_uuids
    assert "u2" not in visible_uuids
    
def test_refresh_preserves_advanced_filter(doc_list_widget, db_manager):
    """Verifies that complex JSON/ZUGFeRD filters are preserved when the list is refreshed."""
    # Setup Data
    # Note: Using float instead of Decimal to avoid serialization edge cases in tests
    # although Pydantic mode='json' should handle it.
    doc1 = Document(
        uuid="u1", 
        original_filename="match.pdf", 
        type_tags=["INVOICE"],
        semantic_data=SemanticExtraction(
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("100.0"))
                )
            }
        )
    )
    doc2 = Document(
        uuid="u2", 
        original_filename="nomatch.pdf", 
        type_tags=["INVOICE"],
        semantic_data=SemanticExtraction(
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("50.0"))
                )
            }
        )
    )
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    
    doc_list_widget.refresh_list()
    assert get_visible_count(doc_list_widget) == 2
    
    # 1. Apply Advanced Filter
    # In DatabaseManager._map_field_to_sql('amount'):
    # CAST(json_extract(semantic_data, '$.bodies.finance_body.monetary_summation.grand_total_amount') AS REAL)
    
    query = {
        "operator": "AND",
        "conditions": [
            {"field": "amount", "op": "gte", "value": 80.0}
        ]
    }
    doc_list_widget.apply_advanced_filter(query)
    
    assert doc_list_widget.current_advanced_query == query
    # If the SQL works, it should return 1 document (u1)
    # The count in logs was 0 previously. Let's see if float helps or if it was something else.
    # Actually, if it's 0, it means the search_documents_advanced(query) returned empty.
    
    assert get_visible_count(doc_list_widget) == 1 
    
    # 2. Refresh List
    doc_list_widget.refresh_list()
    
    assert get_visible_count(doc_list_widget) == 1
    assert doc_list_widget.documents_cache["u1"].original_filename == "match.pdf"
