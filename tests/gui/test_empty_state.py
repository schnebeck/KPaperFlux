import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from gui.main_window import MainWindow
from gui.document_list import DocumentListWidget
from core.database import DatabaseManager
from core.document import Document
from unittest.mock import MagicMock

@pytest.fixture
def db_manager():
    manager = DatabaseManager(":memory:")
    manager.init_db()
    return manager

@pytest.fixture
def main_window(db_manager, qapp):
    # Mock pipeline for MainWindow
    mw = MainWindow(pipeline=MagicMock(), db_manager=db_manager)
    # Ensure it's shown? No need for offscreen testing usually, just instantiation.
    return mw

def test_viewer_unloads_on_empty_list(main_window, db_manager):
    # 1. Setup Data
    doc = Document(uuid="u1", original_filename="doc1.pdf", tags="keep")
    db_manager.insert_document(doc)
    
    # Reload List
    main_window.list_widget.refresh_list()
    assert main_window.list_widget.rowCount() == 1
    
    # Simulate loading document into viewer
    main_window.pdf_viewer.load_document = MagicMock()
    main_window.pdf_viewer.unload = MagicMock()
    
    # Select document to "load" it
    main_window.list_widget.selectRow(0)
    # In real app, signal triggers load. 
    # But for test, we want to check UNLOAD on FILTER.
    
    # 2. Apply Filter that returns empty
    # Logic: apply_filter -> count_changed -> update_status_bar -> check 0 -> unload
    
    criteria = {'tags': 'non-existent'}
    main_window.list_widget.apply_filter(criteria)
    
    visible_count = 0
    list_widget = main_window.list_widget
    for i in range(list_widget.tree.topLevelItemCount()):
        if not list_widget.tree.topLevelItem(i).isHidden():
            visible_count += 1
            
    assert visible_count == 0
    
    # 3. Verify Unload Call
    main_window.pdf_viewer.unload.assert_called_once()
    
    # 4. Check for Hidden Selection Race
    # Ensure hidden items are NOT selected or signal is NOT emitted
    selected = main_window.list_widget.get_selected_uuids()
    assert not selected, "Should not select hidden items"
    
    # Also verify load_document was NOT called after unload
    # Reset mocks
    main_window.pdf_viewer.load_document.reset_mock()
    
    # Trigger selection persistence logic explicitly if MainWindow does it?
    # MainWindow does it in update_status_bar:
    # if hasattr(self, 'pending_selection')...
    
    # Let's set pending selection to the hidden doc
    main_window.pending_selection = ["u1"]
    
    # Trigger update again (as if filter finished)
    main_window.update_status_bar(0, 1)
    
    # Check if load_document called?
    main_window.pdf_viewer.load_document.assert_not_called()
    assert main_window.pdf_viewer.unload.call_count == 2
