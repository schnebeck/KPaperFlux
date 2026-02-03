import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QDialog, QMessageBox
from gui.tag_manager import TagManagerDialog
from core.database import DatabaseManager

@pytest.fixture
def mock_db():
    db = MagicMock(spec=DatabaseManager)
    db.get_all_tags_with_counts.return_value = {"tag1": 10, "tag2": 5}
    return db

def test_tag_manager_populate(qtbot, mock_db):
    dlg = TagManagerDialog(mock_db)
    qtbot.addWidget(dlg)
    
    assert dlg.table.rowCount() == 2
    assert dlg.table.item(0, 0).text() == "tag1"
    assert dlg.table.item(1, 0).text() == "tag2"

def test_tag_manager_rename(qtbot, mock_db):
    dlg = TagManagerDialog(mock_db)
    qtbot.addWidget(dlg)
    
    # Select first row
    dlg.table.selectRow(0)
    
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=("new-tag", True)), \
         patch('gui.tag_manager.show_notification'):
        dlg.rename_selected()
        
    mock_db.rename_tag.assert_called_with("tag1", "new-tag")

def test_tag_manager_delete(qtbot, mock_db):
    dlg = TagManagerDialog(mock_db)
    qtbot.addWidget(dlg)
    
    # Select first row
    dlg.table.selectRow(0)
    
    with patch('gui.tag_manager.show_selectable_message_box', return_value=QMessageBox.StandardButton.Yes), \
         patch('gui.tag_manager.show_notification'):
        dlg.delete_selected()
        
    mock_db.delete_tag.assert_called_with("tag1")

def test_tag_manager_merge(qtbot, mock_db):
    dlg = TagManagerDialog(mock_db)
    qtbot.addWidget(dlg)
    
    # Select two rows
    dlg.table.selectAll()
    
    with patch('PyQt6.QtWidgets.QInputDialog.getItem', return_value=("tag1", True)), \
         patch('gui.tag_manager.show_notification'):
        dlg.merge_selected()
        
    mock_db.merge_tags.assert_called()
    args = mock_db.merge_tags.call_args[0]
    assert "tag1" in args[0]
    assert "tag2" in args[0]
    assert args[1] == "tag1"
