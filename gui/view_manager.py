
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTreeWidget, QTreeWidgetItem, QInputDialog, QMessageBox, QLabel)
from PyQt6.QtCore import Qt, pyqtSignal
from core.filter_tree import NodeType, FilterNode
import json

class ViewManagerDialog(QDialog):
    view_selected = pyqtSignal(dict) # Emits the view state dict
    
    def __init__(self, filter_tree, parent=None, db_manager=None, current_state_callback=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manage Views"))
        self.resize(400, 500)
        self.filter_tree = filter_tree
        self.db_manager = db_manager
        self.current_state_callback = current_state_callback
        
        self.layout = QVBoxLayout(self)
        
        # List
        self.tree_list = QTreeWidget()
        self.tree_list.setHeaderLabel(self.tr("Saved Views"))
        self.tree_list.itemDoubleClicked.connect(self._on_load)
        self.layout.addWidget(self.tree_list)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_load = QPushButton(self.tr("Load"))
        self.btn_load.clicked.connect(self._on_load)
        btn_layout.addWidget(self.btn_load)
        
        self.btn_save = QPushButton(self.tr("Save Current View..."))
        self.btn_save.clicked.connect(self._on_save_current)
        btn_layout.addWidget(self.btn_save)
        
        self.btn_delete = QPushButton(self.tr("Delete"))
        self.btn_delete.clicked.connect(self._on_delete)
        btn_layout.addWidget(self.btn_delete)
        
        self.layout.addLayout(btn_layout)
        
        self.refresh_list()
        
    def refresh_list(self):
        self.tree_list.clear()
        if not self.filter_tree or not self.filter_tree.root:
            return
            
        # Recursive helper to find VIEW nodes
        def add_nodes(parent_node, parent_item):
            for child in parent_node.children:
                if child.node_type == NodeType.VIEW:
                    item = QTreeWidgetItem(parent_item)
                    item.setText(0, child.name)
                    item.setData(0, Qt.ItemDataRole.UserRole, child)
                    # No icon?
                elif child.node_type == NodeType.FOLDER:
                    # Optional: Show folder structure if views are in folders? 
                    # For MVP, maybe flattened list or basic structure.
                    # Let's show structure.
                    item = QTreeWidgetItem(parent_item)
                    item.setText(0, child.name)
                    item.setExpanded(True)
                    add_nodes(child, item)
                    
        # Add Root children
        add_nodes(self.filter_tree.root, self.tree_list.invisibleRootItem())

    def _on_save_current(self):
        if not self.current_state_callback:
            return
            
        name, ok = QInputDialog.getText(self, self.tr("Save View"), self.tr("View Name:"))
        if ok and name:
            state = self.current_state_callback()
            # Save to Tree
            # Where? Root folder default.
            
            # TODO: Improve architecture to save via DB Manager properly
            # Currently we manipulate tree and assume auto-save?
            # Or call db_manager.save_filter_tree()?
            
            # Create Node
            node = FilterNode(name, NodeType.VIEW, data=state)
            self.filter_tree.root.add_child(node)
            
            if self.db_manager:
                self.db_manager.save_filter_tree(self.filter_tree)
                
            self.refresh_list()
            
    def _on_load(self):
        item = self.tree_list.currentItem()
        if not item: return
        
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node and node.node_type == NodeType.VIEW:
            self.view_selected.emit(node.data)
            self.accept()
            
    def _on_delete(self):
        item = self.tree_list.currentItem()
        if not item: return
        
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node:
            if QMessageBox.question(self, self.tr("Confirm"), self.tr("Delete this view?")) == QMessageBox.StandardButton.Yes:
                if node.parent:
                    node.parent.remove_child(node)
                    if self.db_manager:
                        self.db_manager.save_filter_tree(self.filter_tree)
                    self.refresh_list()
