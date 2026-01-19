
import pytest
from PyQt6.QtWidgets import QHeaderView
from core.filter_tree import NodeType, FilterNode, FilterTree
from gui.document_list import DocumentListWidget
from gui.view_manager import ViewManagerDialog

@pytest.fixture
def doc_list(qapp):
    # Mock DB? Not strictly needed for state test if we mock refresh
    w = DocumentListWidget(db_manager=None)
    w.dynamic_columns = ["ExtraCol"]
    # Mock header state
    w.tree.setColumnCount(5)
    w.tree.header().saveState = lambda: b"mock_state"
    return w

def test_get_view_state(doc_list):
    # Setup
    doc_list.current_advanced_query = {"field": "foo", "value": "bar"}
    
    state = doc_list.get_view_state()
    
    assert state["version"] == 1
    assert state["dynamic_columns"] == ["ExtraCol"]
    assert state["filter"] == {"field": "foo", "value": "bar"}
    # Header state is mocked to return bytes, so hex should be present
    assert isinstance(state["header_state"], str)

def test_set_view_state(doc_list):
    state = {
        "version": 1,
        "dynamic_columns": ["NewCol"],
        "header_state": "", # Skip restore logic test for header mock
        "filter": {"field": "baz", "value": "qux"}
    }
    
    # Mock update_headers
    doc_list.update_headers = lambda: None
    
    filter_data = doc_list.set_view_state(state)
    
    assert doc_list.dynamic_columns == ["NewCol"]
    assert filter_data == {"field": "baz", "value": "qux"}

def test_view_manager_load(qapp):
    tree = FilterTree()
    view_node = FilterNode("Test View", NodeType.VIEW, data={"some": "state"})
    tree.root.add_child(view_node)
    
    dlg = ViewManagerDialog(tree, db_manager=None)
    
    # Verify item in tree
    item = dlg.tree_list.topLevelItem(0)
    assert item.text(0) == "Test View"
    
    # Test Load Signal
    dlg.tree_list.setCurrentItem(item)
    
    # We can manually trigger load
    output = []
    dlg.view_selected.connect(output.append)
    dlg._on_load()
    
    assert len(output) == 1
    assert output[0] == {"some": "state"}
