import pytest
import json
from decimal import Decimal
from PyQt6.QtWidgets import QDialog, QMessageBox
from gui.advanced_filter import AdvancedFilterWidget
from gui.filter_manager import FilterManagerDialog
from core.filter_tree import FilterTree, NodeType
from unittest.mock import MagicMock, patch

@pytest.fixture
def filter_tree():
    return FilterTree()

@pytest.fixture
def advanced_widget(qtbot, filter_tree):
    # Mock DB manager
    mock_db = MagicMock()
    # Provide some basic metadata so field selectors work
    mock_db.get_available_extra_keys.return_value = ["monetary_summation.grand_total_amount"]
    mock_db.get_available_tags.return_value = ["INVOICE", "PRIVATE"]
    
    widget = AdvancedFilterWidget(db_manager=mock_db, filter_tree=filter_tree)
    qtbot.addWidget(widget)
    widget.load_known_filters()
    return widget

def test_save_zugferd_filter_to_tree(advanced_widget, filter_tree):
    """
    Test intentionality: Ensuring exact ZUGFeRD paths can be saved and retrieved.
    """
    # 1. Add Condition
    advanced_widget.add_condition()
    row = advanced_widget.root_group.children_widgets[0]
    
    # We use the exact standardized path
    zugferd_path = "monetary_summation.grand_total_amount"
    row._set_field(zugferd_path, "Grand Total")
    row.input_text.setText("100.50")
    
    # 2. Mock QInputDialog to return "Invoice High Value"
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=("Invoice High Value", True)):
        advanced_widget.save_current_filter()
        
    # 3. Verify added to Tree with exact structure
    assert len(filter_tree.root.children) == 1
    node = filter_tree.root.children[0]
    assert node.name == "Invoice High Value"
    
    # Check that the saved query uses the professional path
    query = node.data
    condition = query['conditions'][0]
    assert condition['field'] == zugferd_path
    assert condition['value'] == "100.50"

def test_browse_all_integration(advanced_widget, filter_tree):
    """Verifies that the Filter Manager correctly interacts with the Advanced Filter."""
    # Setup: Add a professional filter
    filter_tree.add_filter(filter_tree.root, "Professional Filter", {
        "operator": "AND",
        "conditions": [{"field": "monetary_summation.grand_total_amount", "op": "gt", "value": "100"}]
    })
    advanced_widget.load_known_filters()
    
    # Trigger "Browse All..." (last item in combo)
    idx = advanced_widget.combo_filters.count() - 1
    
    with patch('gui.advanced_filter.FilterManagerDialog') as MockDialog:
        mock_instance = MockDialog.return_value
        mock_instance.exec.return_value = QDialog.DialogCode.Accepted
        
        # Simulate selecting "Browse All..."
        advanced_widget.combo_filters.setCurrentIndex(idx)
        
        mock_instance.exec.assert_called_once()
        # Verify combo reset to 0 (neutral state)
        assert advanced_widget.combo_filters.currentIndex() == 0

def test_manager_dialog_ui_sync(filter_tree, qtbot):
    """Tests that the Manager Dialog reflects the exact Tree structure."""
    dlg = FilterManagerDialog(filter_tree)
    qtbot.addWidget(dlg)
    
    # Add standardized structures to tree
    folder = filter_tree.add_folder(filter_tree.root, "Finance")
    filter_tree.add_filter(folder, "High Net", {
        "conditions": [{"field": "monetary_summation.tax_basis_total_amount", "op": "gt", "value": "500"}]
    })
    
    dlg.populate_tree()
    
    root_item = dlg.tree_widget.invisibleRootItem()
    assert root_item.childCount() == 1
    finance_item = root_item.child(0)
    assert finance_item.text(0) == "Finance"
    assert finance_item.childCount() == 1
    assert finance_item.child(0).text(0) == "High Net"

def test_filter_dirty_indicator_with_standard_paths(advanced_widget, filter_tree):
    """Ensures modify detection works with exact schema paths."""
    rule = {
        "operator": "AND",
        "conditions": [{"field": "monetary_summation.grand_total_amount", "op": "equals", "value": "50"}]
    }
    node = filter_tree.add_filter(filter_tree.root, "Exact 50", rule)
    advanced_widget.load_known_filters()
    
    # Load the filter
    idx = advanced_widget.combo_filters.findText("Exact 50")
    advanced_widget.combo_filters.setCurrentIndex(idx)
    advanced_widget.loaded_filter_node = node
    
    # 1. Initially clean
    assert not advanced_widget.combo_filters.itemText(idx).endswith(" *")
    
    # 2. Modify value
    row = advanced_widget.root_group.children_widgets[0]
    row.input_text.setText("60")
    
    # 3. Should show dirty indicator
    assert advanced_widget.combo_filters.itemText(idx).endswith(" *")
    assert advanced_widget.btn_revert.isEnabled()

def test_revert_standard_path_filter(advanced_widget, filter_tree):
    """Verifies that reverting restores the exact standardized paths."""
    rule = {
        "operator": "AND",
        "conditions": [{"field": "monetary_summation.tax_total_amount", "op": "gt", "value": "0"}]
    }
    node = filter_tree.add_filter(filter_tree.root, "Has Tax", rule)
    advanced_widget.load_known_filters()
    
    # Load and modify
    advanced_widget._on_manager_selected(node)
    row = advanced_widget.root_group.children_widgets[0]
    row.input_text.setText("10")
    
    assert len(advanced_widget.root_group.children_widgets) == 1
    assert row.input_text.text() == "10"
    
    # Revert
    advanced_widget.btn_revert.click()
    
    # Check restoration
    reverted_row = advanced_widget.root_group.children_widgets[0]
    assert reverted_row.field_key == "monetary_summation.tax_total_amount"
    assert reverted_row.input_text.text() == "0"
    assert not advanced_widget.btn_revert.isEnabled()

def test_delete_filter_integration(advanced_widget, filter_tree):
    """Tests the full deletion cycle from the Advanced Filter UI."""
    filter_tree.add_filter(filter_tree.root, "Trash Me", {})
    advanced_widget.load_known_filters()
    
    idx = advanced_widget.combo_filters.findText("Trash Me")
    advanced_widget.combo_filters.setCurrentIndex(idx)
    node = advanced_widget.combo_filters.currentData()
    
    with patch('gui.advanced_filter.show_selectable_message_box', return_value=QMessageBox.StandardButton.Yes):
        advanced_widget._delete_node(node)
        
    assert len(filter_tree.root.children) == 0
    assert advanced_widget.combo_filters.findText("Trash Me") == -1
