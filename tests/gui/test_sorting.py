
import pytest
import datetime
from decimal import Decimal
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import QTreeWidget
from unittest.mock import MagicMock
from gui.document_list import DocumentListWidget, SortableTreeWidgetItem
from core.database import DatabaseManager, Document

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
    # Create docs with dates that would sort wrongly as strings:
    # "02.01.2024" (Newer, starts with 0) vs "15.01.2023" (Older, starts with 1).
    # Alphabetically: "02..." < "15...".
    # Chronologically: 2023 < 2024.
    
    doc1 = Document(uuid="1", doc_date=datetime.date(2024, 1, 2), original_filename="Newer.pdf") # 02.01.2024
    doc2 = Document(uuid="2", doc_date=datetime.date(2023, 1, 15), original_filename="Older.pdf") # 15.01.2023
    
    mock_db.search_documents.return_value = [doc1, doc2]
    mock_db.get_all_documents.return_value = [doc1, doc2] # Fallback
    
    document_list.refresh_list()
    
    tree = document_list.tree
    
    # Check Col 1 (Date)
    # Check initial texts
    item0 = tree.topLevelItem(0)
    item1 = tree.topLevelItem(1)
    
    # Verify we populated the tree
    assert tree.topLevelItemCount() == 2
    
    # Sort Ascending (Oldest First)
    tree.sortItems(1, Qt.SortOrder.AscendingOrder)
    
    # Expected: 2023 (Older) then 2024 (Newer)
    first_item = tree.topLevelItem(0)
    second_item = tree.topLevelItem(1)
    
    # Check UUIDs stored in UserRole of Col 0
    assert first_item.data(0, Qt.ItemDataRole.UserRole) == "2" # Older
    assert second_item.data(0, Qt.ItemDataRole.UserRole) == "1" # Newer
    
    # Sort Descending (Newest First)
    tree.sortItems(1, Qt.SortOrder.DescendingOrder)
    
    first_item = tree.topLevelItem(0)
    assert first_item.data(0, Qt.ItemDataRole.UserRole) == "1" # Newer

def test_number_sorting(document_list, mock_db):
    """Verify numeric columns sort numerically."""
    # Amount is Col 5.
    # "10.00" vs "2.00"
    # String sort: "10.00" < "2.00".
    # Numeric sort: 2.00 < 10.00.
    
    doc1 = Document(uuid="A", amount=Decimal("10.00"), original_filename="a.pdf")
    doc2 = Document(uuid="B", amount=Decimal("2.00"), original_filename="b.pdf")
    
    mock_db.search_documents.return_value = [doc1, doc2]
    
    document_list.refresh_list()
    tree = document_list.tree
    
    # Sort Ascending (Smallest First)
    tree.sortItems(5, Qt.SortOrder.AscendingOrder)
    
    first_item = tree.topLevelItem(0)
    assert first_item.data(0, Qt.ItemDataRole.UserRole) == "B" # 2.00
    
    second_item = tree.topLevelItem(1)
    assert second_item.data(0, Qt.ItemDataRole.UserRole) == "A" # 10.00

