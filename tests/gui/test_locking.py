import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget
from unittest.mock import MagicMock, patch
from core.document import Document
from gui.main_window import MainWindow
from gui.document_list import DocumentListWidget
from gui.metadata_editor import MetadataEditorWidget
import datetime

@pytest.fixture
def mock_db():
    db = MagicMock()
    # Mock insert/update
    db.insert_document.return_value = 1
    db.update_document_metadata.return_value = True
    return db

@pytest.fixture
def main_window(mock_db, qtbot):
    # Pass mock_db to constructor if supported, else inject
    # MainWindow(db_manager=mock_db)
    window = MainWindow(db_manager=mock_db)
    qtbot.addWidget(window)
    return window

def test_locking_ui_and_persistence(main_window, mock_db, qtbot):
    """Verify Locking UI check, persistence, and effect on widgets."""
    # 1. Setup Document
    doc = Document(
        uuid="lock-test-1",
        original_filename="test.pdf",
        doc_date=datetime.date(2025, 1, 1),
        locked=False
    )
    mock_db.get_document_by_uuid.return_value = doc
    
    # 2. Display in Editor
    editor = main_window.editor_widget
    editor.display_document(doc)
    
    # Verify initial state
    assert editor.chk_locked.isChecked() == False
    assert editor.tab_widget.isEnabled() == True
    
    # 3. Lock it via UI (Clicking mimics user action and triggers on_lock_clicked)
    # Connect signal spy to metadata_saved
    with qtbot.waitSignal(editor.metadata_saved, timeout=1000):
        editor.chk_locked.click() # This should toggle to True and trigger DB update
    
    # Verify State
    assert editor.chk_locked.isChecked() == True
    assert editor.tab_widget.isEnabled() == False # Should be disabled immediately
    
    # 4. Verify DB Update (Immediate)
    # Check if 'locked': True was passed in updates
    # We expect update_document_metadata to be called
    mock_db.update_document_metadata.assert_called()
    args = mock_db.update_document_metadata.call_args[0]
    uuid, updates = args
    assert uuid == "lock-test-1"
    assert updates["locked"] is True
    
    # 5. Verify Loading Locked Doc
    doc_locked = Document(
        uuid="lock-test-2",
        original_filename="locked.pdf",
        locked=True
    )
    editor.display_document(doc_locked)
    assert editor.chk_locked.isChecked() == True
    assert editor.tab_widget.isEnabled() == False

def test_delete_protection(main_window, mock_db, qtbot):
    """Verify locked documents cannot be deleted."""
    doc_unlocked = Document(uuid="u1", original_filename="u1.pdf", locked=False)
    doc_locked = Document(uuid="l1", original_filename="l1.pdf", locked=True)
    
    # Setup DB Mock for these docs
    docs_map = {"u1": doc_unlocked, "l1": doc_locked}
    mock_db.get_document_by_uuid.side_effect = lambda uuid: docs_map.get(uuid)
    
    # Setup List
    list_widget = main_window.list_widget
    # Populate tree manually or via populate_tree
    list_widget.populate_tree([doc_unlocked, doc_locked])
    
    # Select both
    list_widget.select_rows_by_uuids(["u1", "l1"])
    
    # Create Signal Catcher
    with qtbot.waitSignal(list_widget.delete_requested, timeout=1000) as blocker:
        # Trigger Delete (Simulate Context Menu or Call Direct)
        # Mock QMessageBox to prevent blocking
        with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_msg:
             list_widget.delete_selected_documents(["u1", "l1"])
             
             # Verify Warning
             assert mock_msg.called
             
    # Verify Signal Payload (Should only contain "u1")
    emitted_args = blocker.args[0] # The list of uuids
    assert "u1" in emitted_args
    assert "l1" not in emitted_args
    assert len(emitted_args) == 1

def test_visual_graying(main_window, mock_db, qtbot):
    """Verify locked documents are visually distinct (gray)."""
    doc = Document(uuid="l2", original_filename="gray.pdf", locked=True)
    mock_db.get_document_by_uuid.return_value = doc
    
    list_widget = main_window.list_widget
    list_widget.populate_tree([doc])
    
    item = list_widget.tree.topLevelItem(0)
    
    # Verify Foreground Color
    # We check column 0 or 1
    brush = item.foreground(1)
    # Qt.GlobalColor.gray
    assert brush.color() == Qt.GlobalColor.gray
