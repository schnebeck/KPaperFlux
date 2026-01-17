from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, 
                             QWidget, QLineEdit, QPushButton, QSplitter, QLabel, QMessageBox, QMenu,
                             QInputDialog, QTextEdit, QStyle)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from core.filter_tree import FilterTree, NodeType, FilterNode
import json

class ManagerTreeWidget(QTreeWidget):
    """
    Custom TreeWidget to handle Drag & Drop moves.
    """
    item_dropped = pyqtSignal(QTreeWidgetItem, QTreeWidgetItem)

    def dropEvent(self, event):
        # Identify Target
        # position() is QPointF, need toPoint()
        pos = event.position().toPoint()
        target_item = self.itemAt(pos)
        source_item = self.currentItem()
        
        if source_item and source_item != target_item:
            # Emit signal to Manager to handle model update
            # We pass target_item even if it's None (Root?)
            # But itemAt returns None if dropping on viewport whitespace.
            # Handle root drops?
            self.item_dropped.emit(source_item, target_item)

        # Ignore default handling to prevent UI/Model desync.
        # We will repopulate tree after model update.
        event.ignore()

class FilterManagerDialog(QDialog):
    """
    Dialog to manage the Filter Tree (Folders, Filters, Snapshots).
    """
    filter_selected = pyqtSignal(object) # Emits FilterNode (or data) on selection/open
    
    def __init__(self, filter_tree: FilterTree, db_manager=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filter Manager")
        self.resize(1000, 600)
        
        self.tree_model = filter_tree
        self.db_manager = db_manager
        
        # UI Setup
        self.layout = QVBoxLayout(self)
        
        # --- Top Bar (Search) ---
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search filters...")
        self.search_input.textChanged.connect(self.on_search_changed)
        top_bar.addWidget(self.search_input)
        
        self.layout.addLayout(top_bar)
        
        # --- Splitter (Tree | Detail) ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Tree
        self.tree_widget = ManagerTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.tree_widget.currentItemChanged.connect(self.on_item_changed)
        self.tree_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        # Enable Drag & Drop
        self.tree_widget.setDragEnabled(True)
        self.tree_widget.setAcceptDrops(True)
        self.tree_widget.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        
        self.tree_widget.item_dropped.connect(self.on_item_dropped)
        
        self.populate_tree()
        
        self.splitter.addWidget(self.tree_widget)
        
        # Right: Details
        self.details_area = QWidget()
        self.details_layout = QVBoxLayout(self.details_area)
        self.details_label = QLabel("<b>Select an item</b> to view details")
        self.details_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        
        self.details_layout.addWidget(self.details_label)
        self.details_layout.addWidget(self.details_text)
        
        self.splitter.addWidget(self.details_area)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        
        self.layout.addWidget(self.splitter)
        
        # --- Bottom Bar ---
        bottom_bar = QHBoxLayout()
        
        self.btn_new_folder = QPushButton("New Folder")
        self.btn_new_folder.clicked.connect(self.create_folder)
        bottom_bar.addWidget(self.btn_new_folder)
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self.delete_item)
        bottom_bar.addWidget(self.btn_delete)
        
        bottom_bar.addStretch()
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_close)
        
        self.layout.addLayout(bottom_bar)
        
    def populate_tree(self):
        self.tree_widget.clear()
        self.item_map = {} # Map QTreeWidgetItem -> FilterNode
        self._add_node_recursive(self.tree_model.root, self.tree_widget.invisibleRootItem())
        
    def _add_node_recursive(self, node: FilterNode, parent_item):
        if node.name == "Root" and not node.parent:
            # Don't show root, show its children? Or show Root folder?
            # Usually root is hidden.
            for child in node.children:
                self._add_node_recursive(child, parent_item)
            return

        item = QTreeWidgetItem(parent_item)
        item.setText(0, node.name)
        
        # Icons
        if node.node_type == NodeType.FOLDER:
            item.setIcon(0, QIcon.fromTheme("folder"))
            item.setExpanded(True)
        else:
            # Check if it's a Static List (UUID IN ...)
            is_static_list = False
            if node.data and 'conditions' in node.data:
                for c in node.data['conditions']:
                     if c.get('field') == 'uuid' and c.get('op') == 'in':
                         is_static_list = True
                         break
            
            if is_static_list:
                # Use List Icon
                item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView))
            else:
                # Use Filter Icon
                item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
            
        self.item_map[id(item)] = node
        
        for child in node.children:
            self._add_node_recursive(child, item)
            
    def on_search_changed(self, text):
        # Filter tree view
        if not text:
            # Show all
            self.populate_tree()
            return
            
        results = self.tree_model.search(text)
        # For simplicity, just rebuild tree showing only matches + parents?
        # Or hide non-matches?
        # Hiding QTreeWidgetItems is easier.
        # But QTreeWidget structure mirrors model. 
        # If I want to verify Search Logic from UI, I should use the result list to highlight or filter.
        # Let's simple re-populate with matches? No, that loses hierarchy context.
        # Standard approach: Iterate all items, hide those not in results AND not parent of result.
        
        # Implementation:
        # 1. Reset all hidden
        # 2. Iterate and match text (or use search results)
        self._filter_items(self.tree_widget.invisibleRootItem(), text.lower())

    def _filter_items(self, item, query):
        # Returns True if item or any child is visible
        visible = False
        text = item.text(0).lower()
        
        if query in text:
            visible = True
            
        child_visible = False
        for i in range(item.childCount()):
            child = item.child(i)
            if self._filter_items(child, query):
                child_visible = True
        
        if visible or child_visible:
            item.setHidden(False)
            if child_visible:
                item.setExpanded(True)
            return True
        else:
            item.setHidden(True)
            return False

    def on_item_changed(self, current, previous):
        if not current:
            return
            
        node = self.item_map.get(id(current))
        if not node:
            return
            
        self.update_details(node)

    def update_details(self, node: FilterNode):
        """Update the details pane based on selected node."""
        if node.node_type == NodeType.FOLDER:
            self.details_label.setText(f"<b>Folder:</b> {node.name}")
            html = f"Contains {len(node.children)} items."
            self.details_text.setHtml(html)
            return

        # Regular Filter or Snapshot
        is_static_list = False
        uuids = []
        if node.data and 'conditions' in node.data:
            for c in node.data['conditions']:
                 if c.get('field') == 'uuid' and c.get('op') == 'in':
                     is_static_list = True
                     uuids = c.get('value', [])
                     break
        
        if is_static_list:
            count = len(uuids)
            self.details_label.setText(f"<b>Static List:</b> {node.name}")
            
            html = f"<p>Contains <b>{count}</b> documents.</p><hr/>"
            
            # Fetch Filenames if DB available
            if self.db_manager and uuids:
                # Limit to 10 for preview
                preview_ids = uuids[:10]
                
                # Fetch only export_filename for these IDs
                # Manual SQL or get_document_by_uuid loop? Loop is slow if not cached.
                # db.get_document_by_uuid is single fetch.
                # Better: db_manager.execute_query lookup? Or just loop for 10 items.
                
                # Let's try to get filenames.
                filenames = []
                for uid in preview_ids:
                    doc = self.db_manager.get_document_by_uuid(uid)
                    if doc:
                         name = doc.export_filename or doc.original_filename or "Unknown"
                         filenames.append(name)
                    else:
                         filenames.append(f"Missing ({uid})")
                         
                html += "<ul>"
                for entry in filenames:
                    html += f"<li>{entry}</li>"
                html += "</ul>"
                
                if count > 10:
                    html += f"<p><i>...and {count - 10} more.</i></p>"
            else:
                # Fallback to UUIDs
                html += "<ul>"
                for uid in uuids[:10]:
                    html += f"<li>{uid}</li>"
                html += "</ul>"
                
            self.details_text.setHtml(html)
            
        else:
            # Dynamic Filter
            self.details_label.setText(f"<b>Filter Rule:</b> {node.name}")
            
            # Simple human readable summary
            # Condition 'field' 'op' 'value'
            lines = []
            if node.data and 'conditions' in node.data:
                 op_main = node.data.get('operator', 'AND')
                 lines.append(f"<b>Logic: {op_main}</b>")
                 lines.append("<ul>")
                 for c in node.data['conditions']:
                     f = c.get('field')
                     o = c.get('op')
                     v = c.get('value')
                     neg = "NOT " if c.get('negate') else ""
                     lines.append(f"<li>{neg}<b>{f}</b> <i>{o}</i> '{v}'</li>")
                 lines.append("</ul>")
            
            self.details_text.setHtml("".join(lines))

    def on_item_double_clicked(self, item, column):
        if not item:
            return
        node = self.item_map.get(id(item))
        if node and node.node_type != NodeType.FOLDER:
             # Just like selecting "Load"
             self.on_select_clicked()

    def create_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder Name:")
        if ok and name:
            # Default parent: selected folder or root
            parent_node = self.tree_model.root
            current_item = self.tree_widget.currentItem()
            if current_item:
                selected_node = self.item_map.get(id(current_item))
                if selected_node and selected_node.node_type == NodeType.FOLDER:
                    parent_node = selected_node
                elif selected_node and selected_node.parent:
                     parent_node = selected_node.parent
            
            self.tree_model.add_folder(parent_node, name)
            self.populate_tree() # Refresh
            
    def delete_item(self):
        current_item = self.tree_widget.currentItem()
        if not current_item:
            return
            
        node = self.item_map.get(id(current_item))
        if not node:
            return
            
        confirm = QMessageBox.question(self, "Delete", f"Delete '{node.name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            if node.parent:
                node.parent.remove_child(node)
                self.populate_tree()

    def on_select_clicked(self):
        current_item = self.tree_widget.currentItem()
        if not current_item:
            return
            
        node = self.item_map.get(id(current_item))
        if node and node.node_type != NodeType.FOLDER:
            self.filter_selected.emit(node)
            self.accept()
            
    def show_context_menu(self, pos):
        item = self.tree_widget.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        menu.addAction("Delete", self.delete_item)
        menu.exec(self.tree_widget.viewport().mapToGlobal(pos))

    def on_item_dropped(self, source_item, target_item):
        source_node = self.item_map.get(id(source_item))
        
        target_node = self.tree_model.root # Default to Root
        if target_item:
             t_node = self.item_map.get(id(target_item))
             if t_node:
                 target_node = t_node
        
        if source_node and target_node:
            try:
                # If target is not a folder, maybe drop into its parent?
                # User Experience: Dropping ON a file usually means nothing or replace.
                # Dropping ON a folder means move into.
                # Dropping BETWEEN items (Indicator) is what InternalMove usually shows.
                # But calculating "Between" from itemAt is hard without indicator rect.
                # For simplicity V1: Drop ON Folder = Move to Folder. Drop ON Root = Move to Root.
                
                if target_node.node_type != NodeType.FOLDER and target_node != self.tree_model.root:
                    # If dropping on a leaf, move to that leaf's parent
                    if target_node.parent:
                        target_node = target_node.parent
                
                self.tree_model.move_node(source_node, target_node)
                self.populate_tree() # Reflect Structure
                
                # Expand target if folder
                # Need to find new item for target_node
                # (handled by populate state? No, populate resets.)
                # TODO: Restore expansion/selection if impactful.
                
            except ValueError as e:
                # e.g. "Cannot move node into its own child"
                QMessageBox.warning(self, "Move Failed", str(e))
