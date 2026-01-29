import uuid
import json
from enum import Enum
from typing import List, Optional, Dict, Any

class NodeType(str, Enum):
    FOLDER = "folder"
    FILTER = "filter"
    SNAPSHOT = "snapshot"
    TRASH = "trash"
    VIEW = "view"

class FilterNode:
    def __init__(self, name: str, node_type: NodeType, data: Dict[str, Any] = None, parent: 'FilterNode' = None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.node_type = node_type
        self.data = data or {}
        self.children: List['FilterNode'] = []
        self.parent = parent
        
        # Phase 106: Rule Extension
        self.tags_to_add: List[str] = []
        self.tags_to_remove: List[str] = []
        self.auto_apply: bool = False
        self.is_enabled: bool = True
        
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "type": self.node_type.value,
            "data": self.data,
            "tags_to_add": self.tags_to_add,
            "tags_to_remove": self.tags_to_remove,
            "auto_apply": self.auto_apply,
            "is_enabled": self.is_enabled,
            "children": [child.to_dict() for child in self.children]
        }
        
    def add_child(self, node: 'FilterNode'):
        node.parent = self
        self.children.append(node)
        
    def remove_child(self, node: 'FilterNode'):
        if node in self.children:
            self.children.remove(node)
            node.parent = None

class FilterTree:
    def __init__(self):
        self.root = FilterNode("Root", NodeType.FOLDER)
        self.favorites: List[str] = [] # List of node UUIDs
        
    def add_folder(self, parent: FilterNode, name: str) -> FilterNode:
        folder = FilterNode(name, NodeType.FOLDER, parent=parent)
        parent.add_child(folder)
        return folder
        
    def add_filter(self, parent: FilterNode, name: str, rule: Dict) -> FilterNode:
        node = FilterNode(name, NodeType.FILTER, data=rule, parent=parent)
        parent.add_child(node)
        return node
        
    def add_snapshot(self, parent: FilterNode, name: str, uuids: List[str]) -> FilterNode:
        data = {"uuids": uuids}
        node = FilterNode(name, NodeType.SNAPSHOT, data=data, parent=parent)
        parent.add_child(node)
        return node
        
    def add_trash(self, parent: FilterNode) -> FilterNode:
        node = FilterNode("Trash", NodeType.TRASH, parent=parent)
        parent.add_child(node)
        return node
        
    def move_node(self, node: FilterNode, new_parent: FilterNode):
        if node.node_type == NodeType.TRASH:
             raise ValueError("Trash cannot be moved.")
        if node.parent:
            node.parent.remove_child(node)
        new_parent.add_child(node)
        
    def search(self, query: str) -> List[FilterNode]:
        """
        Search for nodes matching the query string (case-insensitive).
        Returns a flat list of matching nodes.
        """
        results = []
        if not query:
            return results
            
        q = query.lower()
        
        def _recurse(node: FilterNode):
            # Check current node (skip Root usually, but check children)
            if node.parent and q in node.name.lower(): # Skip root
                 results.append(node)
                 
            for child in node.children:
                _recurse(child)
                
        # Start from root's children, or check root if needed?
        # Root is virtual usually. Let's recurse from root.
        _recurse(self.root)
        return results

    def to_json(self) -> str:
        data = {
            "favorites": self.favorites,
            "root": self.root.to_dict()
        }
        return json.dumps(data, indent=2)
        
    def load(self, data: Dict):
        self.favorites = data.get("favorites", [])
        root_data = data.get("root", {})
        
        # Reconstruct tree recursive
        self.root = self._parse_node(root_data)
        
    def _parse_node(self, data: Dict, parent: FilterNode = None) -> FilterNode:
        name = data.get("name", "Root")
        node_type = NodeType(data.get("type", "folder"))
        node_data = data.get("data", {})
        
        # Handle "uuid" if loading existing, or generate new?
        # Ideally persist UUID.
        
        node = FilterNode(name, node_type, data=node_data, parent=parent)
        if "id" in data:
            node.id = data["id"]
        
        # Rule Fields
        node.tags_to_add = data.get("tags_to_add", [])
        node.tags_to_remove = data.get("tags_to_remove", [])
        node.auto_apply = bool(data.get("auto_apply", False))
        node.is_enabled = bool(data.get("is_enabled", True))
            
        for child_data in data.get("children", []):
            child_node = self._parse_node(child_data, parent=node)
            node.children.append(child_node)
            
        return node
        
    def get_all_filters(self) -> List[FilterNode]:
        """Returns a flat list of all FILTER nodes in the tree."""
        results = []
        def _recurse(node):
            if node.node_type == NodeType.FILTER:
                results.append(node)
            for child in node.children:
                _recurse(child)
        _recurse(self.root)
        return results

    def get_active_rules(self, only_auto: bool = False) -> List[FilterNode]:
        """Returns all nodes that have tagging actions and are enabled."""
        results = []
        def _recurse(node):
            if node.node_type == NodeType.FILTER and node.is_enabled:
                # A filter is a rule if it has tags to add/remove
                if node.tags_to_add or node.tags_to_remove:
                    if not only_auto or node.auto_apply:
                        results.append(node)
            for child in node.children:
                _recurse(child)
        _recurse(self.root)
        return results

    def find_node_by_id(self, node_id: str) -> Optional[FilterNode]:
        """Find a node by its UUID."""
        def _recurse(node):
            if node.id == node_id:
                return node
            for child in node.children:
                found = _recurse(child)
                if found: return found
            return None
        return _recurse(self.root)
