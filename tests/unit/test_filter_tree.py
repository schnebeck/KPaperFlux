import pytest
import json
from core.filter_tree import FilterTree, FilterNode, NodeType

def test_tree_initialization():
    tree = FilterTree()
    assert tree.root is not None
    assert tree.root.node_type == NodeType.FOLDER
    assert tree.root.children == []

def test_add_nodes():
    tree = FilterTree()
    
    # Add Folder
    folder = tree.add_folder(tree.root, "Finance")
    assert folder.name == "Finance"
    assert folder.node_type == NodeType.FOLDER
    assert len(tree.root.children) == 1
    
    # Add Filter
    rule = {"operator": "AND", "conditions": []}
    limit_filter = tree.add_filter(folder, "High Value", rule)
    assert limit_filter.name == "High Value"
    assert limit_filter.node_type == NodeType.FILTER
    assert limit_filter.data == rule
    assert limit_filter.parent == folder
    
    # Add Snapshot
    uuids = ["u1", "u2"]
    snapshot = tree.add_snapshot(folder, "Q1 Submission", uuids)
    assert snapshot.node_type == NodeType.SNAPSHOT
    assert snapshot.data["uuids"] == uuids
    
    assert len(folder.children) == 2

def test_serialization():
    tree = FilterTree()
    folder = tree.add_folder(tree.root, "Docs")
    tree.add_filter(folder, "My Filter", {"op": "test"})
    
    json_str = tree.to_json()
    data = json.loads(json_str)
    
    assert data["root"]["children"][0]["name"] == "Docs"
    assert data["root"]["children"][0]["children"][0]["name"] == "My Filter"
    assert data["root"]["children"][0]["children"][0]["type"] == "filter"

def test_load_from_json():
    raw_data = {
        "favorites": [],
        "root": {
            "type": "folder",
            "children": [
                 {"type": "filter", "name": "Loaded Filter", "data": {}}
            ]
        }
    }
    
    tree = FilterTree()
    tree.load(raw_data)
    
    assert len(tree.root.children) == 1
    assert tree.root.children[0].name == "Loaded Filter"

def test_move_node():
    tree = FilterTree()
    folder1 = tree.add_folder(tree.root, "Folder 1")
    folder2 = tree.add_folder(tree.root, "Folder 2")
    item = tree.add_filter(folder1, "Item", {})
    
    assert item in folder1.children
    assert item not in folder2.children
    
    # Move
    tree.move_node(item, folder2)
    
    assert item not in folder1.children
    assert item in folder2.children
    assert item.parent == folder2
