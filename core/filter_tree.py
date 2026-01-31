"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/filter_tree.py
Version:        1.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Hierarchical tree structure for managing filters, folders, 
                snapshots, and auto-tagging rules. Provides serialization 
                and search capabilities.
------------------------------------------------------------------------------
"""

import json
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional


class NodeType(str, Enum):
    """Enumeration of possible node types in the filter tree."""
    FOLDER = "folder"
    FILTER = "filter"
    SNAPSHOT = "snapshot"
    TRASH = "trash"
    VIEW = "view"


class FilterNode:
    """
    Represents a single node in the FilterTree.
    Can be a folder or a leaf node (filter, snapshot, etc.).
    """

    def __init__(self, name: str, node_type: NodeType, data: Optional[Dict[str, Any]] = None, parent: Optional['FilterNode'] = None) -> None:
        """
        Initializes a FilterNode.

        Args:
            name: The display name of the node.
            node_type: The type of the node.
            data: Arbitrary data associated with the node (e.g., filter rules).
            parent: The parent node, if any.
        """
        self.id: str = str(uuid.uuid4())
        self.name: str = name
        self.node_type: NodeType = node_type
        self.data: Dict[str, Any] = data or {}
        self.children: List['FilterNode'] = []
        self.parent: Optional['FilterNode'] = parent

        # Phase 106: Rule Extension
        self.tags_to_add: List[str] = []
        self.tags_to_remove: List[str] = []
        self.auto_apply: bool = False
        self.is_enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializes the node and its children to a dictionary.

        Returns:
            A dictionary representation of the node.
        """
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

    def add_child(self, node: 'FilterNode') -> None:
        """
        Adds a child node to this node.

        Args:
            node: The FilterNode to add as a child.
        """
        node.parent = self
        self.children.append(node)

    def remove_child(self, node: 'FilterNode') -> None:
        """
        Removes a child node from this node.

        Args:
            node: The FilterNode to remove.
        """
        if node in self.children:
            self.children.remove(node)
            node.parent = None


class FilterTree:
    """
    Manages a hierarchy of FilterNodes.
    """

    def __init__(self) -> None:
        """Initializes an empty FilterTree with a root folder."""
        self.root: FilterNode = FilterNode("Root", NodeType.FOLDER)
        self.favorites: List[str] = []  # List of node UUIDs

    def add_folder(self, parent: FilterNode, name: str) -> FilterNode:
        """
        Adds a folder node.

        Args:
            parent: The parent node.
            name: Name of the new folder.

        Returns:
            The newly created FilterNode.
        """
        folder = FilterNode(name, NodeType.FOLDER, parent=parent)
        parent.add_child(folder)
        return folder

    def add_filter(self, parent: FilterNode, name: str, rule: Dict[str, Any]) -> FilterNode:
        """
        Adds a filter node.

        Args:
            parent: The parent node.
            name: Name of the filter.
            rule: The filter rule dictionary.

        Returns:
            The newly created FilterNode.
        """
        node = FilterNode(name, NodeType.FILTER, data=rule, parent=parent)
        parent.add_child(node)
        return node

    def add_snapshot(self, parent: FilterNode, name: str, uuids: List[str]) -> FilterNode:
        """
        Adds a snapshot node.

        Args:
            parent: The parent node.
            name: Name of the snapshot.
            uuids: List of document UUIDs in the snapshot.

        Returns:
            The newly created FilterNode.
        """
        data = {"uuids": uuids}
        node = FilterNode(name, NodeType.SNAPSHOT, data=data, parent=parent)
        parent.add_child(node)
        return node

    def add_trash(self, parent: FilterNode) -> FilterNode:
        """
        Adds a trash node.

        Args:
            parent: The parent node.

        Returns:
            The newly created FilterNode.
        """
        node = FilterNode("Trash", NodeType.TRASH, parent=parent)
        parent.add_child(node)
        return node

    def move_node(self, node: FilterNode, new_parent: FilterNode) -> None:
        """
        Moves a node to a new parent.

        Args:
            node: The node to move.
            new_parent: The destination parent node.

        Raises:
            ValueError: If attempting to move the Trash node.
        """
        if node.node_type == NodeType.TRASH:
            raise ValueError("Trash cannot be moved.")
        if node.parent:
            node.parent.remove_child(node)
        new_parent.add_child(node)

    def search(self, query: str) -> List[FilterNode]:
        """
        Search for nodes matching the query string (case-insensitive).
        Returns a flat list of matching nodes.

        Args:
            query: The search query.

        Returns:
            A list of matching FilterNode objects.
        """
        results: List[FilterNode] = []
        if not query:
            return results

        q = query.lower()

        def _recurse(node: FilterNode) -> None:
            # Check current node (skip Root usually, but check children)
            if node.parent and q in node.name.lower():  # Skip root
                results.append(node)

            for child in node.children:
                _recurse(child)

        _recurse(self.root)
        return results

    def to_json(self) -> str:
        """
        Serializes the entire tree to a JSON string.

        Returns:
            A JSON string representing the tree.
        """
        data = {
            "favorites": self.favorites,
            "root": self.root.to_dict()
        }
        return json.dumps(data, indent=2)

    def load(self, data: Dict[str, Any]) -> None:
        """
        Loads the tree from a dictionary.

        Args:
            data: The tree data dictionary.
        """
        self.favorites = data.get("favorites", [])
        root_data = data.get("root", {})

        # Reconstruct tree recursively
        self.root = self._parse_node(root_data)

    def _parse_node(self, data: Dict[str, Any], parent: Optional[FilterNode] = None) -> FilterNode:
        """
        Recursively parses a node dictionary and its children.

        Args:
            data: The node data dictionary.
            parent: The parent node.

        Returns:
            A populated FilterNode object.
        """
        name = data.get("name", "Root")
        node_type = NodeType(data.get("type", "folder"))
        node_data = data.get("data", {})

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
        """
        Returns a flat list of all FILTER nodes in the tree.

        Returns:
            A list of FilterNode objects of type FILTER.
        """
        results: List[FilterNode] = []

        def _recurse(node: FilterNode) -> None:
            if node.node_type == NodeType.FILTER:
                results.append(node)
            for child in node.children:
                _recurse(child)

        _recurse(self.root)
        return results

    def get_active_rules(self, only_auto: bool = False) -> List[FilterNode]:
        """
        Returns all nodes that have tagging actions and are enabled.

        Args:
            only_auto: If True, only return rules with auto_apply=True.

        Returns:
            A list of active rule FilterNode objects.
        """
        results: List[FilterNode] = []

        def _recurse(node: FilterNode) -> None:
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
        """
        Find a node by its UUID.

        Args:
            node_id: The UUID to search for.

        Returns:
            The FilterNode if found, else None.
        """
        def _recurse(node: FilterNode) -> Optional[FilterNode]:
            if node.id == node_id:
                return node
            for child in node.children:
                found = _recurse(child)
                if found:
                    return found
            return None

        return _recurse(self.root)
