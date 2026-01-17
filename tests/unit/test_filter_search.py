import pytest
from core.filter_tree import FilterTree, NodeType

@pytest.fixture
def populated_tree():
    tree = FilterTree()
    finance = tree.add_folder(tree.root, "Finance")
    tax = tree.add_folder(finance, "Tax 2023")
    
    # Matches "Tax"
    tree.add_filter(tax, "Tax Return", {})
    
    # Matches "Invoice"
    tree.add_filter(finance, "Invoice A", {})
    
    # Matches "Tax" (in name)
    tree.add_filter(tree.root, "Tax General", {})
    
    return tree

def test_search_finds_nodes(populated_tree):
    # Search for "Tax"
    results = populated_tree.search("Tax")
    
    names = [n.name for n in results]
    assert "Tax 2023" in names # Folder match
    assert "Tax Return" in names # Child of matching folder? No, child matching query.
    assert "Tax General" in names # Direct match
    assert "Invoice A" not in names # No match
    
def test_search_case_insensitive(populated_tree):
    results = populated_tree.search("invoice")
    names = [n.name for n in results]
    assert "Invoice A" in names

def test_search_empty(populated_tree):
    results = populated_tree.search("NonExistent")
    assert len(results) == 0
