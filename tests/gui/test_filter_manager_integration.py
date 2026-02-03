import pytest
import json
from PyQt6.QtWidgets import QDialog, QMessageBox, QTreeWidgetItemIterator, QTreeWidgetItem
from gui.advanced_filter import AdvancedFilterWidget
from gui.filter_manager import FilterManagerDialog
from core.filter_tree import FilterTree, NodeType
from unittest.mock import MagicMock, patch

@pytest.fixture
def filter_tree():
    return FilterTree()

@pytest.fixture
def advanced_widget(qapp, filter_tree):
    # Mock DB manager as None is fine for this test
    widget = AdvancedFilterWidget(db_manager=None, filter_tree=filter_tree)
    # Ensure UI loaded
    widget.load_known_filters()
    return widget

def test_save_filter_to_tree(advanced_widget, filter_tree):
    # 1. Add Condition
    advanced_widget.add_condition()
    row = advanced_widget.root_group.children_widgets[0]
    row._set_field("amount", "Amount")
    row.input_text.setText("100")
    
    # 2. Mock QInputDialog to return "My Filter"
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=("My Filter", True)):
        advanced_widget.save_current_filter()
        
    # 3. Verify added to Tree
    assert len(filter_tree.root.children) == 1
    node = filter_tree.root.children[0]
    assert node.name == "My Filter"
    assert node.node_type == NodeType.FILTER
    # node.data is populated from get_query() in save_current_filter
    # Ensure get_query() was called properly
    assert node.data['conditions'][0]['value'] == "100"
    
    # 4. Verify added to Combo
    assert advanced_widget.combo_filters.findText("My Filter") >= 0

def test_browse_all_opens_manager(advanced_widget, filter_tree):
    # Setup: Add a filter to tree so we have something to see
    filter_tree.add_filter(filter_tree.root, "Existing Filter", {})
    advanced_widget.load_known_filters()
    
    # Trigger "Browse All..."
    # Index of Browse All is last
    idx = advanced_widget.combo_filters.count() - 1
    browse_text = advanced_widget.combo_filters.itemText(idx)
    assert "Browse All" in browse_text
    
    # Mock FilterManagerDialog.exec
    with patch('gui.advanced_filter.FilterManagerDialog') as MockDialog:
        mock_instance = MockDialog.return_value
        mock_instance.exec.return_value = QDialog.DialogCode.Accepted
        
        # Simulate selection (currentIndexChanged)
        advanced_widget.combo_filters.setCurrentIndex(idx)
        
        # Verify Dialog instantiated and executed
        # MockDialog was called with (filter_tree, advanced_widget).
        # But maybe with kwargs? 
        # actual: FilterManagerDialog(args..., db_manager=None, parent=widget)
        # So we should match generic or be precise.
        
        args, kwargs = MockDialog.call_args
        assert args[0] == filter_tree
        # Check parent (last arg or kwarg)
        
        mock_instance.exec.assert_called_once()
        
        # Verify combo reset to 0 (Select)
        assert advanced_widget.combo_filters.currentIndex() == 0

def test_manager_dialog_logic(filter_tree, qapp):
    # Test FilterManagerDialog independently
    dlg = FilterManagerDialog(filter_tree)
    
    # Add Item to tree via API, verify UI update
    filter_tree.add_folder(filter_tree.root, "New Folder")
    dlg.populate_tree()
    
    root_item = dlg.tree_widget.invisibleRootItem()
    assert root_item.childCount() == 1
    assert root_item.child(0).text(0) == "New Folder"
    
    # Test Create Folder from Dialog
    # Select root item? Item selection logic needed.
    # Mock QInputDialog for create_folder
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=("Sub Folder", True)):
        # Select "New Folder" item
        dlg.tree_widget.setCurrentItem(root_item.child(0))
        dlg.create_folder()
        
    # Verify Model Updated
    folder_node = filter_tree.root.children[0]
    assert len(folder_node.children) == 1
    assert folder_node.children[0].name == "Sub Folder"
    
    # Verify UI Updated
    assert root_item.child(0).childCount() == 1

def test_quick_delete(advanced_widget, filter_tree):
    # Setup
    filter_tree.add_filter(filter_tree.root, "To Delete", {})
    advanced_widget.load_known_filters()
    
    # Select it
    idx = advanced_widget.combo_filters.findText("To Delete")
    advanced_widget.combo_filters.setCurrentIndex(idx)
    
    # Get node
    node = advanced_widget.combo_filters.currentData()
    assert node.name == "To Delete"
    
    # Simulate Delete (bypass menu exec, call logic directly)
    # Mock confirmation dialog
    with patch('gui.advanced_filter.show_selectable_message_box', return_value=QMessageBox.StandardButton.Yes):
        advanced_widget._delete_node(node)
        
    # Verify Removed from Tree
    assert len(filter_tree.root.children) == 0
    
    # Verify Removed from Combo
    assert advanced_widget.combo_filters.findText("To Delete") == -1
    assert advanced_widget.combo_filters.currentIndex() == 0 # Reset to Select

def test_persistence_callback(filter_tree, qapp):
    # Mock Save Callback
    mock_save = MagicMock()
    
    widget = AdvancedFilterWidget(
        db_manager=None, 
        filter_tree=filter_tree, 
        save_callback=mock_save
    )
    
    # 1. Save Filter -> Should Trigger
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=("SavedFilter", True)):
        widget.add_condition() 
        # Set dummy values
        row = widget.root_group.children_widgets[0]
        # Just ensure save condition is met (rows exist)
        
        widget.save_current_filter()
        
    mock_save.assert_called()
    call_count_after_save = mock_save.call_count
    
    # 2. Open Manager (Close) -> Should Trigger
    with patch('gui.advanced_filter.FilterManagerDialog') as MockDialog:
        mock_instance = MockDialog.return_value
        mock_instance.exec.return_value = QDialog.DialogCode.Accepted
        widget.open_filter_manager()
        
    assert mock_save.call_count > call_count_after_save

def test_drag_drop_persistence(filter_tree, qapp):
    # Setup: Root -> Folder A, Filter B
    folder = filter_tree.add_folder(filter_tree.root, "Folder A")
    node_b = filter_tree.add_filter(filter_tree.root, "Filter B", {})
    
    # Init Dialog
    dlg = FilterManagerDialog(filter_tree)
    
    # Mock Drag Drop Event
    # We simulate the signal emission manually or call on_item_dropped directly
    # Because simulating QDropEvent is complex.
    
    # 1. Get Items
    root_item = dlg.tree_widget.invisibleRootItem()
    # Items order depends on recursion. Usually Root -> Folder A, Filter B.
    # Find items by text
    item_folder = None
    item_b = None
    
    # Helper to find items
    def find_item_recursive(parent):
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.text(0) == "Folder A":
                nonlocal item_folder
                item_folder = child
            elif child.text(0) == "Filter B":
                nonlocal item_b
                item_b = child
            find_item_recursive(child)
            
    find_item_recursive(root_item)
    assert item_folder is not None
    assert item_b is not None
    
    # 2. Simulate Drop (B onto A)
    dlg.on_item_dropped(item_b, item_folder)
    
    # 3. Verify Model Updated
    assert node_b.parent == folder
    assert node_b in folder.children
    assert node_b not in filter_tree.root.children
    
    # 4. Verify UI Updated (repopulated)
    # Re-find items
    item_folder = None
    item_b = None
    find_item_recursive(root_item)
    
    # B should be child of A
    assert item_b.parent() == item_folder

def test_ux_refinements(filter_tree, qapp):
    # Setup Nested
    folder = filter_tree.add_folder(filter_tree.root, "Deep")
    node_nested = filter_tree.add_filter(folder, "Deep Filter", {'operator': 'AND'})
    
    widget = AdvancedFilterWidget(db_manager=None, filter_tree=filter_tree)
    widget.load_known_filters()
    
    # 1. Verify Node NOT in combo initially (only root children)
    assert widget.combo_filters.findText("Deep Filter") == -1
    
    # 2. Simulate Manager Selection via Full Flow
    # We need to mock FilterManagerDialog to simulate user selecting a node
    with patch('gui.advanced_filter.FilterManagerDialog') as MockDialog:
        instance = MockDialog.return_value
        instance.exec.return_value = QDialog.DialogCode.Accepted
        # Mock signal emission behavior
        # When exec is called, we want to emit filter_selected manually?
        # Or trigger it via side_effect?
        def side_effect_exec():
            # Simulate user selecting node
             widget._on_manager_selected(node_nested)
             return QDialog.DialogCode.Accepted
        instance.exec.side_effect = side_effect_exec
        
        widget.open_filter_manager()
        
    # 3. Verify Combo Sync
    # Should have inserted item at index 1
    assert widget.combo_filters.currentIndex() == 1
    assert "Deep Filter" in widget.combo_filters.currentText()
    # Actual text format is "Deep / Deep Filter" according to test failure
    assert "Deep /" in widget.combo_filters.currentText()
    assert widget.combo_filters.currentData() == node_nested

def test_double_click_load(filter_tree, qapp):
    node = filter_tree.add_filter(filter_tree.root, "ClickMe", {})
    dlg = FilterManagerDialog(filter_tree)
    
    # Simulate Double Click
    # Simplification: Access top level item directly
    item = dlg.tree_widget.topLevelItem(0)
    assert item is not None
    assert item.text(0) == "ClickMe"
    dlg.tree_widget.setCurrentItem(item)
    
    with patch.object(dlg, 'accept') as mock_accept:
         dlg.on_item_double_clicked(item, 0)
         mock_accept.assert_called()

def test_loading_is_clean(filter_tree, qapp):
    node = filter_tree.add_filter(filter_tree.root, "CleanFilter", {})
    widget = AdvancedFilterWidget(db_manager=None, filter_tree=filter_tree)
    
    widget._on_manager_selected(node)
    
    # Check if * is NOT appended (loading should be clean)
    assert not widget.btn_apply.isEnabled()
    idx = widget.combo_filters.currentIndex()
    assert not widget.combo_filters.itemText(idx).endswith(" *")

def test_dirty_indicator_reset(filter_tree, qapp):
    node_a = filter_tree.add_filter(filter_tree.root, "Filter A", {})
    node_b = filter_tree.add_filter(filter_tree.root, "Filter B", {})
    widget = AdvancedFilterWidget(db_manager=None, filter_tree=filter_tree)
    widget.load_known_filters()
    
    # 1. Load A
    idx_a = widget.combo_filters.findText("Filter A")
    widget.combo_filters.setCurrentIndex(idx_a)
    widget.loaded_filter_node = node_a # Manual wiring if signal loop incomplete in test
    
    # 2. Modify A -> *
    widget.add_condition()
    # add_condition triggers _set_dirty
    assert widget.combo_filters.itemText(idx_a).endswith(" *")
    
    # 3. Load B -> A should lose *
    idx_b = widget.combo_filters.findText("Filter B")
    widget.combo_filters.setCurrentIndex(idx_b)
    
    # Logic note: combo change triggers _on_saved_filter_selected
    # which calls load_from_object -> resets dirty of loaded_filter_node (A)
    # then sets loaded_filter_node to B
    
    # Check A
    assert not widget.combo_filters.itemText(idx_a).endswith(" *")
    # Check B (should be clean)
    assert not widget.combo_filters.itemText(idx_b).endswith(" *")

def test_save_load_cycle(filter_tree, tmp_path, qapp):
    # This test verifies that MainWindow save/load logic works with a file
    # We mock MainWindow behavior partially
    
    # 1. Simulate Save
    path = tmp_path / "test_filter_tree.json"
    
    # Create structure
    node = filter_tree.add_filter(filter_tree.root, "Persisted Filter", {})
    
    # Manually save using logic similar to MainWindow or mocking MainWindow
    # We can't easily instantiate full MainWindow due to dependencies, 
    # but we can verify the logic if we could import it.
    # Since we can't easily, let's verify FilterTree to_json/load cycle with file I/O
    # which is what MainWindow does.
    
    with open(path, "w") as f:
        f.write(filter_tree.to_json())
        
    assert path.exists()
    
    # 2. Simulate Load (New Tree)
    new_tree = FilterTree()
    with open(path, "r") as f:
        data = json.load(f)
        new_tree.load(data)
        
    assert len(new_tree.root.children) == 1
    assert new_tree.root.children[0].name == "Persisted Filter"
    
    # 3. Verify MainWindow logic (conceptually)
    # If MainWindow.save_filter_tree is called, it writes to filter_config_path.
    # If MainWindow.load_filter_tree is called, it reads from filter_config_path.
    # We verified the I/O part above.
    # The integration relies on closeEvent calling save.
    
    # Since we can't test full app exit, we rely on unit tests for components.
    pass

def test_nested_visibility(filter_tree, qapp):
    # Tests that filters in subfolders appear in Main Combo
    folder = filter_tree.add_folder(filter_tree.root, "My Folder")
    node = filter_tree.add_filter(folder, "Nested Item", {})
    
    widget = AdvancedFilterWidget(db_manager=None, filter_tree=filter_tree)
    widget.load_known_filters()
    
    # "My Folder / Nested Item" should act as filter
    # Check if any item contains "Nested Item"
    found = False
    for i in range(widget.combo_filters.count()):
        text = widget.combo_filters.itemText(i)
        if "Nested Item" in text:
            found = True
            # Verify data
            assert widget.combo_filters.itemData(i) == node
            # Verify folder prefix in text? e.g. "My Folder / Nested Item"
            assert "My Folder /" in text
            break
            
    assert found

def test_clear_all_resets_loaded_node(filter_tree, qapp):
    # Regression: "Clear All" resulted in dirty previous filter
    node = filter_tree.add_filter(filter_tree.root, "Sticky", {})
    widget = AdvancedFilterWidget(db_manager=None, filter_tree=filter_tree)
    widget.load_known_filters()
    
    # 1. Load Filter
    idx = widget.combo_filters.findText("Sticky")
    widget.combo_filters.setCurrentIndex(idx)
    widget.loaded_filter_node = node
    
    # 2. Clear All (via Button logic simulation)
    # Button clear connection: lambda: self.clear_all(reset_combo=True)
    widget.clear_all(reset_combo=True)
    
    # 3. Check clean state
    # loaded_filter_node should be None
    assert widget.loaded_filter_node is None
    
    # 4. Modify (Add Condition)
    widget.add_condition()
    # Should NOT mark "Sticky" as dirty
    assert not widget.combo_filters.itemText(idx).endswith(" *")
    
def test_revert_functionality(filter_tree, qapp):
    node = filter_tree.add_filter(filter_tree.root, "To Revert", {'operator': 'AND', 'conditions': [{'field': 'A', 'value': '1'}]})
    widget = AdvancedFilterWidget(db_manager=None, filter_tree=filter_tree)
    widget.load_known_filters()
    
    # 1. Load Filter
    widget._on_manager_selected(node)
    
    # 2. Assert Initial State
    assert not widget.btn_revert.isEnabled()
    assert len(widget.root_group.children_widgets) == 1
    
    # 3. Modify
    widget.add_condition()
    # Now dirty, Revert should be enabled
    assert widget.btn_revert.isEnabled()
    assert len(widget.root_group.children_widgets) == 2
    assert widget.combo_filters.currentText().endswith(" *")
    
    # 4. Click Revert
    widget.btn_revert.click()
    
    # 5. Assert Reverted State
    assert not widget.btn_revert.isEnabled()
    assert len(widget.root_group.children_widgets) == 1
    assert widget.root_group.children_widgets[0].get_condition()['value'] == '1'
    assert not widget.combo_filters.currentText().endswith(" *")
