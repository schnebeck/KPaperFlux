import pytest
from PyQt6.QtWidgets import QApplication
from unittest.mock import MagicMock, patch
from gui.main_window import MainWindow
from core.document import Document
from gui.dialogs.save_list_dialog import SaveListDialog
from PyQt6.QtCore import Qt

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_available_extra_keys.return_value = []
    # Setup mock documents
    docs = [
        Document(uuid="u1", original_filename="doc1.pdf"),
        Document(uuid="u2", original_filename="doc2.pdf"),
        Document(uuid="u3", original_filename="doc3.pdf")
    ]
    db.get_all_documents.return_value = docs
    db.search_documents.return_value = docs
    db.get_document_by_uuid.side_effect = lambda u: next((d for d in docs if d.uuid == u), None)
    return db

@pytest.fixture
def main_window(mock_db, qapp, tmp_path):
    # Patch Config to return tmp vault path
    with patch('core.config.AppConfig.get_vault_path', return_value=str(tmp_path)):
        # Patch FilterTree persistence to avoid writing to actual cwd
        with patch('gui.main_window.FilterTree') as MockTree:
             # We want a real-ish FilterTree behavior for add_filter, so maybe we use real object if possible?
             # Or just Mock the tree behavior.
             # If we use real MainWindow, it instantiates FilterTree.
             # Let's mock the internal tree of window.
             window = MainWindow()
             window.db_manager = mock_db
             # Re-init list widget to use mock db if needed (it does in __init__)
             # Actually __init__ called init_ui -> DocumentListWidget(db_manager)
             # But we passed no db_manager to constructor, wait.
             # MainWindow() constructor doesn't take db_manager. It creates it or takes it?
             # MainWindow() usually creates DatabaseManager().
             # We should patch DatabaseManager class.
             pass
             
    # Better approach: 
    with patch('gui.main_window.DatabaseManager', return_value=mock_db):
        window = MainWindow(db_manager=mock_db)
        # Force list refresh
        window.list_widget.refresh_list()
        yield window
        window.close()

def test_save_list_selection(main_window):
    # Select u1 and u2
    window = main_window
    list_widget = window.list_widget
    
    # Verify populate
    assert list_widget.tree.topLevelItemCount() == 3
    
    # Select
    list_widget.select_rows_by_uuids(["u1", "u2"])
    
    # Mock Dialog
    with patch('gui.document_list.SaveListDialog') as MockDlg:
        instance = MockDlg.return_value
        instance.exec.return_value = True
        instance.get_data.return_value = ("Test List", True) # Name, SelectionOnly=True
        
        # Trigger Save
        list_widget.save_as_list()
        
        # Check if Signal emitted -> Connected to save_static_list
        # Check FilterTree
        # We need to verify window.filter_tree.add_filter called
        # window.filter_tree is likely a Mock or Real?
        # In this test setup, it depends on what MainWindow.__init__ did.
        # It creates FilterTree().
        # We can inspect window.filter_tree content if real.
        
        # If we didn't mock FilterTree class specifically, it is real (using default empty tree?)
        # Let's just inspect the tree nodes.
        root = window.filter_tree.root
        children = root.children
        # Find "Test List"
        node = next((n for n in children if n.name == "Test List"), None)
        assert node is not None
        
        # Check Condition
        conds = node.data['conditions']
        assert len(conds) == 1
        c = conds[0]
        assert c['field'] == 'uuid'
        assert c['operator'] == 'in'
        assert set(c['value']) == {"u1", "u2"}

def test_save_list_all(main_window):
    # Filter list to show only u3 (simulate search/filter)
    # But for simplicity, just assume all 3 visible and selection is None.
    window = main_window
    list_widget = window.list_widget
    list_widget.tree.clearSelection()
    
    with patch('gui.document_list.SaveListDialog') as MockDlg:
        instance = MockDlg.return_value
        instance.exec.return_value = True
        instance.get_data.return_value = ("All Visible", False) # Name, SelectionOnly=False
        
        list_widget.save_as_list()
        
        root = window.filter_tree.root
        children = root.children
        node = next((n for n in children if n.name == "All Visible"), None)
        assert node is not None
        
        c = node.data['conditions'][0]
        assert c['operator'] == 'in'
        # Should contain u1, u2, u3 (all visible)
        assert set(c['value']) == {"u1", "u2", "u3"}
