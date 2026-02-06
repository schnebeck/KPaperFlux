
import pytest
import datetime
from decimal import Decimal
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import QTreeWidget
from unittest.mock import MagicMock
from gui.document_list import DocumentListWidget, SortableTreeWidgetItem
from core.database import DatabaseManager, Document
from core.models.semantic import SemanticExtraction, MetaHeader, FinanceBody, AddressInfo, MonetarySummation

@pytest.fixture
def mock_db():
    db = MagicMock(spec=DatabaseManager)
    db.get_available_extra_keys.return_value = []
    return db

@pytest.fixture
def document_list(qtbot, mock_db):
    widget = DocumentListWidget(mock_db, pipeline=None)
    qtbot.addWidget(widget)
    return widget

def test_date_sorting(document_list, mock_db):
    """Verify that dates sort chronologically, not alphabetically."""
    # Data Setup
    doc1 = Document(
        uuid="1", 
        original_filename="Newer.pdf",
        semantic_data=SemanticExtraction(meta_header=MetaHeader(doc_date="2024-01-02"))
    ) # 02.01.2024
    doc2 = Document(
        uuid="2", 
        original_filename="Older.pdf",
        semantic_data=SemanticExtraction(meta_header=MetaHeader(doc_date="2023-01-15"))
    ) # 15.01.2023
    
    mock_db.get_all_entities_view.return_value = [doc1, doc2]
    
    # Explicitly enable Date column
    document_list.dynamic_columns = ["doc_date"]
    document_list.update_headers()
    
    document_list.refresh_list()
    tree = document_list.tree
    
    # Discovery phase
    header_labels = [tree.headerItem().text(i) for i in range(tree.columnCount())]
    def get_col(label): return header_labels.index(label)
    
    col_date = get_col("Date")
    col_uuid = get_col("Entity ID")
    
    # Verify we populated the tree
    assert tree.topLevelItemCount() == 2
    
    # Sort Ascending (Oldest First)
    tree.sortItems(col_date, Qt.SortOrder.AscendingOrder)
    
    # Expected: 2023 (Older) then 2024 (Newer)
    assert tree.topLevelItem(0).text(col_uuid) == "2" # Older
    assert tree.topLevelItem(1).text(col_uuid) == "1" # Newer
    
    # Sort Descending (Newest First)
    tree.sortItems(col_date, Qt.SortOrder.DescendingOrder)
    assert tree.topLevelItem(0).text(col_uuid) == "1" # Newer

def test_number_sorting(document_list, mock_db):
    """Verify numeric columns sort numerically."""
    doc1 = Document(
        uuid="A", 
        original_filename="a.pdf",
        semantic_data=SemanticExtraction(
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("10.00"))
                )
            }
        )
    )
    doc2 = Document(
        uuid="B", 
        original_filename="b.pdf",
        semantic_data=SemanticExtraction(
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("2.00"))
                )
            }
        )
    )
    
    mock_db.get_all_entities_view.return_value = [doc1, doc2]
    
    # Explicitly enable Amount column (total_amount property)
    document_list.dynamic_columns = ["total_amount"]
    document_list.update_headers()
    
    document_list.refresh_list()
    tree = document_list.tree
    
    # Discovery phase
    header_labels = [tree.headerItem().text(i) for i in range(tree.columnCount())]
    def get_col(label): return header_labels.index(label)
    
    col_amount = get_col("Amount")
    col_uuid = get_col("Entity ID")
    
    # Sort Ascending (Smallest First)
    tree.sortItems(col_amount, Qt.SortOrder.AscendingOrder)
    
    assert tree.topLevelItem(0).text(col_uuid) == "B" # 2.00
    assert tree.topLevelItem(1).text(col_uuid) == "A" # 10.00
