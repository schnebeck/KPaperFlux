import pytest
from unittest.mock import MagicMock, patch
from gui.main_window import MainWindow
from core.models.virtual import VirtualDocument as Document
from gui.dialogs.save_list_dialog import SaveListDialog
from PyQt6.QtWidgets import QApplication

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_available_extra_keys.return_value = []
    # Setup mock documents
    docs = [
        Document(uuid="u1", original_filename="doc1.pdf"),
        Document(uuid="u2", original_filename="doc2.pdf")
    ]
    db.get_all_documents.return_value = docs
    db.search_documents.return_value = docs
    # Fix: Ensure get_document_by_uuid returns the actual doc object, not a Mock
    def get_by_uuid(u):
        return next((d for d in docs if d.uuid == u), None)
    db.get_document_by_uuid.side_effect = get_by_uuid
    db.get_all_entities_view.return_value = docs # Support Stage 0 ListView
    return db

@pytest.fixture
def main_window(mock_db, qapp, tmp_path):
    with patch('core.config.AppConfig.get_vault_path', return_value=str(tmp_path)):
         with patch('gui.main_window.DatabaseManager', return_value=mock_db):
            # Patch FilterTree to use memory or temp file
            # MainWindow initializes FilterTree. 
            # We want to verify that saving updates the tree, and reloading reads it.
            # But the FilterTree internal save uses file path.
            # MainWindow sets path in __init__
            window = MainWindow(db_manager=mock_db)
            window.filter_config_path = tmp_path / "filter_tree_test.json"
            # Ensure it starts with empty tree or reloads
            window.load_filter_tree()
            
            window.list_widget.refresh_list()
            yield window
            window.close()

def test_save_and_verify_ui_operator(main_window):
    window = main_window
    list_widget = window.list_widget
    
    # 1. Select Rows
    list_widget.select_rows_by_uuids(["u1", "u2"])
    
    # 2. Save As List
    with patch('gui.document_list.SaveListDialog') as MockDlg:
        instance = MockDlg.return_value
        instance.exec.return_value = True
        instance.get_data.return_value = ("IntegrationTestList", True)
        
        list_widget.save_as_list()
        
    # 3. Verify FilterTree has it
    root = window.filter_tree.root
    node = next((n for n in root.children if n.name == "IntegrationTestList"), None)
    assert node is not None
    assert node.data['conditions'][0]['op'] == 'in'
    
    # 4. Load it into Advanced Filter Widget
    # The combo box should have been updated by load_known_filters which calls populate
    # We select it in the combo box.
    adv_widget = window.advanced_filter
    combo = adv_widget.combo_filters
    
    # Find item
    idx = combo.findText("IntegrationTestList")
    assert idx >= 0, "Saved filter not found in combo box"
    
    # Select it -> Triggers load_from_object
    combo.setCurrentIndex(idx)
    
    # 5. Verify UI State
    # Should have 1 row
    rows = adv_widget.root_group.children_widgets
    assert len(rows) == 1
    row = rows[0]
    
    # Field: UUID
    assert row.btn_field_selector.text() == "UUID"
    
    # Operator: In List (key='in')
    # If this fails (equals 'contains'), then finding 'in' failed
    assert row.combo_op.currentData() == 'in', f"Operator displayed as {row.combo_op.currentData()}, expected 'in'"
    
    # Value
    assert "u1" in row.input_text.text()
    assert "u2" in row.input_text.text()
