
import pytest
from gui.batch_tag_dialog import BatchTagDialog
from gui.main_window import MainWindow
from core.database import DatabaseManager
from core.document import Document
from PyQt6.QtWidgets import QDialog
from unittest.mock import MagicMock, patch

def test_batch_tag_dialog_parsing(qtbot):
    dialog = BatchTagDialog()
    qtbot.addWidget(dialog)
    
    dialog.txt_add.setText(" tax , 2024,  ")
    dialog.txt_remove.setText("old  ,  unused")
    
    add, remove = dialog.get_data()
    assert add == ["tax", "2024"]
    assert remove == ["old", "unused"]

@pytest.fixture
def db_for_tags(tmp_path):
    db_path = tmp_path / "tag_test.db"
    db = DatabaseManager(str(db_path))
    db.init_db()
    
    # Doc 1: Has "old", "keep"
    db.insert_document(Document(uuid="1", original_filename="a.pdf", tags="old, keep"))
    # Doc 2: Has "keep"
    db.insert_document(Document(uuid="2", original_filename="b.pdf", tags="keep"))
    
    return db

def test_manage_tags_logic(qtbot, db_for_tags):
    # Mock MainWindow with DB Manager
    # We can test logic without full GUI if we extract logic or mock dialog
    
    # Let's instantiate MainWindow but mock parts
    mw = MainWindow(pipeline=None, db_manager=db_for_tags)
    mw.list_widget = MagicMock()
    
    # Mock BatchTagDialog exec to return True and data
    with patch('gui.batch_tag_dialog.BatchTagDialog') as MockDialog:
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_data.return_value = (["new", "tax"], ["old"])
        
        # Call slot with both UUIDs
        with patch('gui.main_window.QMessageBox'):
             mw.manage_tags_slot(["1", "2"])
        
        # Verify DB updates
        doc1 = db_for_tags.get_document_by_uuid("1")
        tags1 = [t.strip() for t in doc1.tags.split(",")]
        # Should have: keep, new, tax. Removed: old.
        assert "old" not in tags1
        assert "keep" in tags1
        assert "new" in tags1
        assert "tax" in tags1
        
        doc2 = db_for_tags.get_document_by_uuid("2")
        tags2 = [t.strip() for t in doc2.tags.split(",")]
        # Should have: keep, new, tax. (Old wasn't there)
        assert "keep" in tags2
        assert "new" in tags2
        assert "tax" in tags2
        
        # Verify list refresh called
        assert mw.list_widget.refresh_list.called
