
import pytest
from gui.batch_tag_dialog import BatchTagDialog
from gui.main_window import MainWindow
from core.database import DatabaseManager
from core.document import Document
from PyQt6.QtWidgets import QDialog
from unittest.mock import MagicMock, patch

def test_batch_tag_dialog_parsing(qtbot):
    dialog = BatchTagDialog(available_tags=["tax", "2024", "old", "unused"], common_tags=["old", "unused"])
    qtbot.addWidget(dialog)
    
    # Logic: 
    # combo_common manages "checked" items for all. 
    # Start: "old", "unused" are checked.
    # We want to Add: "tax", "2024" -> So Check them.
    # We want to Remove: "old", "unused" -> So Uncheck them.
    
    dialog.combo_common.setCheckedItems(["tax", "2024"]) # old/unused NOT included -> removed
    
    # extra_remove is additional force remove
    dialog.extra_remove.setText("") 
    
    add, remove = dialog.get_data()
    # Added: In New (tax, 2024) - Old (old, unused) = tax, 2024
    assert set(add) == {"tax", "2024"}
    # Removed: In Old (old, unused) - New (tax, 2024) = old, unused
    assert set(remove) == {"old", "unused"}

@pytest.fixture
def db_for_tags(tmp_path):
    db_path = tmp_path / "tag_test.db"
    db = DatabaseManager(str(db_path))
    db.init_db()
    
    # Doc 1: Has "old", "keep"
    db.insert_document(Document(uuid="1", original_filename="a.pdf", tags=["old", "keep"]))
    # Doc 2: Has "keep"
    db.insert_document(Document(uuid="2", original_filename="b.pdf", tags=["keep"]))
    
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
        # Check User tags list
        tags1 = doc1.tags
        # Should have: keep, new, tax. Removed: old.
        assert "old" not in tags1
        assert "keep" in tags1
        assert "new" in tags1
        assert "tax" in tags1
        
        doc2 = db_for_tags.get_document_by_uuid("2")
        tags2 = doc2.tags
        # Should have: keep, new, tax. (Old wasn't there)
        assert "keep" in tags2
        assert "new" in tags2
        assert "tax" in tags2
        
        # Verify list refresh called
        assert mw.list_widget.refresh_list.called
