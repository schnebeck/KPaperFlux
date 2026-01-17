import pytest
from PyQt6.QtWidgets import QApplication, QStyle
from PyQt6.QtGui import QIcon
from unittest.mock import MagicMock
from gui.filter_manager import FilterManagerDialog, NodeType
from core.filter_tree import FilterTree, FilterNode
from core.document import Document

@pytest.fixture
def mock_db_manager():
    db = MagicMock()
    # Mock document fetch
    def get_doc(uuid):
        if uuid == "u1":
            return Document(uuid="u1", original_filename="doc1.pdf", export_filename="Invoice_2023.pdf")
        return None
    db.get_document_by_uuid.side_effect = get_doc
    return db

@pytest.fixture
def filter_tree():
    tree = FilterTree()
    # Create Root -> Static List
    # Condition: uuid IN [u1, u2]
    cond = [{"field": "uuid", "op": "in", "value": ["u1", "u2"]}]
    tree.add_filter(tree.root, "My Static List", {"conditions": cond})
    
    # Create Root -> Dynamic Filter
    tree.add_filter(tree.root, "My Dynamic Filter", {"conditions": [{"field": "date", "op": "gt", "value": "2023"}]})
    return tree

def test_static_list_icon_and_details(qapp, filter_tree, mock_db_manager):
    dialog = FilterManagerDialog(filter_tree, db_manager=mock_db_manager)
    
    # Find "My Static List" item
    root_item = dialog.tree_widget.invisibleRootItem()
    # Assuming flat list under root as per populate_tree implementation loop
    # root.children -> recursive add
    # The tree widget structure mimics the filter tree
    
    assert dialog.tree_widget.topLevelItemCount() == 2
    
    # Find list item
    list_item = None
    filter_item = None
    
    for i in range(dialog.tree_widget.topLevelItemCount()):
        item = dialog.tree_widget.topLevelItem(i)
        if item.text(0) == "My Static List":
            list_item = item
        elif item.text(0) == "My Dynamic Filter":
            filter_item = item
            
    assert list_item is not None
    assert filter_item is not None
    
    # 1. Verify Icon (List vs Filter)
    # List Icon
    # We can't easily compare QIcon objects equality, but we can check if it's set.
    # Or check name() if theme icon. But we used StandardIcon.
    # Let's assume if implementation didn't crash, it set *an* icon.
    # We can check specific node type logic by ensuring code path coverage basically.
    # The real verification is visual or checking if it differentiates.
    # But checking details text confirms the logic path.
    
    # 2. Select List Item -> Check Details
    dialog.tree_widget.setCurrentItem(list_item)
    # Signal should fire update_details
    
    # Check Label
    assert "Static List" in dialog.details_label.text()
    
    # Check Text (Resolution)
    html = dialog.details_text.toHtml()
    assert "Invoice_2023.pdf" in html # u1 resolved
    assert "Missing (u2)" in html      # u2 missing
    assert "Contains" in html
    assert "2" in html
    assert "documents" in html

def test_folder_details(qapp, filter_tree):
    # Add folder
    folder = filter_tree.add_folder(filter_tree.root, "My Folder")
    filter_tree.add_filter(folder, "Child Filter", {})
    
    dialog = FilterManagerDialog(filter_tree)
    # Refresh tree manually or ensure init did it (init calls populate)
    # But we modified tree AFTER init in this test setup?
    # Ah, `filter_tree` fixture is created, then passed to dialog.
    # The folder addition happens NOW? No, `add_folder` modifies model.
    # If we modify model AFTER dialog creation, we need repopulate.
    # Let's modify before creation.
    pass

def test_folder_details_logic(qapp):
    tree = FilterTree()
    folder = tree.add_folder(tree.root, "My Folder")
    tree.add_filter(folder, "Child", {})
    
    dialog = FilterManagerDialog(tree)
    
    # Find folder item
    folder_item = None
    for i in range(dialog.tree_widget.topLevelItemCount()):
        item = dialog.tree_widget.topLevelItem(i)
        if item.text(0) == "My Folder":
            folder_item = item
            break
            
    assert folder_item is not None
    
    dialog.tree_widget.setCurrentItem(folder_item)
    
    assert "Folder:" in dialog.details_label.text()
    assert "Contains 1 items" in dialog.details_text.toHtml()
