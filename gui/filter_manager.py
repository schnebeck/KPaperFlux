from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,                              QWidget, QLineEdit, QPushButton, QSplitter, QLabel, QMessageBox, QMenu,
                             QInputDialog, QTextEdit, QStyle)
from gui.utils import show_selectable_message_box
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
    
    def __init__(self, filter_tree: FilterTree, db_manager=None, parent=None, start_node: FilterNode = None):
        super().__init__(parent)
        self.tree_model = filter_tree
        self.db_manager = db_manager
        self.start_node = start_node # Focused node/folder on open
        
        # UI Setup
        self.layout = QVBoxLayout(self)
        
        # --- Top Bar (Search) ---
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
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
        self.tree_widget.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        
        self.tree_widget.item_dropped.connect(self.on_item_dropped)
        
        self.populate_tree()
        
        if self.start_node:
            self.focus_node(self.start_node)
        
        self.splitter.addWidget(self.tree_widget)
        
        # Right: Details
        self.details_area = QWidget()
        self.details_layout = QVBoxLayout(self.details_area)
        self.details_label = QLabel()
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
        
        self.btn_new_folder = QPushButton()
        self.btn_new_folder.clicked.connect(self.create_folder)
        bottom_bar.addWidget(self.btn_new_folder)
        
        self.btn_delete = QPushButton()
        self.btn_delete.clicked.connect(self.delete_item)
        bottom_bar.addWidget(self.btn_delete)
        
        bottom_bar.addStretch()
        
        self.btn_close = QPushButton()
        self.btn_close.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_close)
        
        self.layout.addLayout(bottom_bar)
        self.retranslate_ui()
    
    def changeEvent(self, event):
        if event and event.type() == Qt.EventType.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        self.setWindowTitle(self.tr("Filter & Rule Manager"))
        self.search_input.setPlaceholderText(self.tr("Search filters..."))
        
        # Reset details text if nothing selected
        if not self.tree_widget.currentItem():
            self.details_label.setText(self.tr("<b>Select an item</b> to view details"))
            self.details_text.clear()
        else:
            # Refresh details for current
            node = self.item_map.get(id(self.tree_widget.currentItem()))
            if node:
                self.update_details(node)

        self.btn_new_folder.setText("✚ " + self.tr("New Folder"))
        self.btn_delete.setText("🗑 " + self.tr("Delete"))
        self.btn_close.setText(self.tr("Close"))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.delete_item()
        else:
            super().keyPressEvent(event)
        
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
        elif node.node_type == NodeType.TRASH:
            item.setIcon(0, QIcon.fromTheme("user-trash"))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled) # Trash is dragging disabled
        elif node.node_type == NodeType.ARCHIVE:
            item.setIcon(0, QIcon.fromTheme("archive-folder", QIcon.fromTheme("document-export")))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled) 
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
        
        # Disable delete for specialized nodes
        self.btn_delete.setEnabled(node.node_type not in [NodeType.TRASH, NodeType.ARCHIVE])

    def focus_node(self, node: FilterNode):
        """Finds and selects the item for a given node."""
        for item_id, n in self.item_map.items():
            if n == node:
                # Need to find the actual QTreeWidgetItem by its ID
                # Since id(item) is not persistent across populate, we need a better lookup or store the reverse.
                # For now, let's just iterate items in tree.
                it = self._find_item_by_node(self.tree_widget.invisibleRootItem(), node)
                if it:
                    self.tree_widget.setCurrentItem(it)
                    it.setSelected(True)
                    it.setExpanded(True)
                break

    def _find_item_by_node(self, parent_it, node):
        for i in range(parent_it.childCount()):
            it = parent_it.child(i)
            if self.item_map.get(id(it)) == node:
                return it
            found = self._find_item_by_node(it, node)
            if found: return found
        return None

    def update_details(self, node: FilterNode):
        """Update the details pane based on selected node."""
        if node.node_type == NodeType.FOLDER:
            self.details_label.setText(f"<b>{self.tr('Folder')}:</b> {node.name}")
            html = self.tr("Contains %n item(s).", "", len(node.children))
            self.details_text.setHtml(html)
            return

        if node.node_type == NodeType.TRASH:
            self.details_label.setText(f"<b>{node.name}</b>")
            self.details_text.setHtml(f"<p>{self.tr('Deleted documents live here.')}</p><p>{self.tr('Select this filter to restore or permanently delete files.')}</p>")
            return

        if node.node_type == NodeType.ARCHIVE:
            self.details_label.setText(f"<b>{node.name}</b>")
            self.details_text.setHtml(f"<p>{self.tr('Your long-term document storage.')}</p><p>{self.tr('This filter shows all documents marked as Archive.')}</p>")
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
            self.details_label.setText(f"<b>{self.tr('Static List')}:</b> {node.name}")
            
            html = f"<p>{self.tr('Contains <b>%n</b> documents.', '', count)}</p><hr/>"
            
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
                    html += f"<p><i>...{self.tr('and %n more.', '', count - 10)}</i></p>"
            else:
                # Fallback to UUIDs
                html += "<ul>"
                for uid in uuids[:10]:
                    html += f"<li>{uid}</li>"
                html += "</ul>"
                
            self.details_text.setHtml(html)
            
        else:
            # Regular Filter or Snapshot
            # Reverse map for human readable display
            field_map_rev = {
                "direction": self.tr("AI Direction"),
                "tenant_context": self.tr("AI Context"),
                "confidence": self.tr("AI Confidence"),
                "reasoning": self.tr("AI Reasoning"),
                "type_tags": self.tr("Type Tags"),
                "visual_audit_mode": self.tr("Visual Audit"),
                "original_filename": self.tr("Filename"),
                "export_filename": self.tr("Filename"),
                "created_at": self.tr("Created At"),
                "last_processed_at": self.tr("Last Processed"),
                "page_count_virt": self.tr("Pages"),
                "cached_full_text": self.tr("Text Content")
            }

            self.details_label.setText(f"<b>{self.tr('Filter Rule')}:</b> {node.name}")
            
            lines = []
            
            # Phase 106: Display Rule specific fields
            if node.tags_to_add or node.tags_to_remove:
                lines.append(f"<b>{self.tr('Tagging Actions')}:</b>")
                lines.append("<ul style='margin-bottom: 10px;'>")
                if node.tags_to_add:
                    lines.append(f"<li>➕ {self.tr('Add')}: <span style='color: green;'>{', '.join(node.tags_to_add)}</span></li>")
                if node.tags_to_remove:
                    lines.append(f"<li>➖ {self.tr('Remove')}: <span style='color: red;'>{', '.join(node.tags_to_remove)}</span></li>")
                
                status_bits = []
                if node.is_enabled: status_bits.append(f"<span style='color: green;'>{self.tr('Active')}</span>")
                else: status_bits.append(f"<span style='color: gray;'>{self.tr('Inactive')}</span>")
                
                if node.auto_apply: status_bits.append(f"<span style='color: blue;'>{self.tr('Run on Import')}</span>")
                
                lines.append(f"<li>⚙️ {self.tr('Settings')}: {' | '.join(status_bits)}</li>")
                lines.append("</ul>")
                lines.append("<hr/>")

            if node.data and 'conditions' in node.data:
                 op_main = node.data.get('operator', 'AND')
                 lines.append(f"<b>{self.tr('Filtering Logic')}: {op_main}</b>")
                 lines.append("<ul>")
                 for c in node.data['conditions']:
                     f_key = c.get('field', '')
                     f_display = field_map_rev.get(f_key, f_key)
                     o = c.get('op')
                     v = c.get('value')
                     
                     # Format value for display
                     if isinstance(v, list):
                         v_display = ", ".join(map(str, v))
                     else:
                         v_display = str(v)
                         
                     neg = self.tr("NOT ") if c.get('negate') else ""
                     lines.append(f"<li>{neg}<b>{f_display}</b> <i>{o}</i> '{v_display}'</li>")
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
        name, ok = QInputDialog.getText(self, self.tr("New Folder"), self.tr("Folder Name:"))
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
        items = self.tree_widget.selectedItems()
        if not items:
            return
            
        nodes = []
        for it in items:
            node = self.item_map.get(id(it))
            if node and node.node_type not in [NodeType.TRASH, NodeType.ARCHIVE]:
                nodes.append(node)
        
        if not nodes:
            return

        if len(nodes) == 1:
            msg = self.tr("Delete '%1'?").arg(nodes[0].name)
        else:
            msg = self.tr("Delete %n selected item(s)?", "", len(nodes))

        confirm = show_selectable_message_box(self, self.tr("Delete"), msg, icon=QMessageBox.Icon.Question, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            for node in nodes:
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
        menu.addAction("📤 " + self.tr("Export to Exchange..."), lambda: self.export_item(item))
        menu.addSeparator()
        menu.addAction("🗑 " + self.tr("Delete"), self.delete_item)
        menu.exec(self.tree_widget.viewport().mapToGlobal(pos))

    def export_item(self, item):
        """Export selected node as portable exchange file."""
        node = self.item_map.get(id(item))
        if not node:
               return
               
        from core.exchange import ExchangeService
        payload_type = "smart_list" if node.node_type == NodeType.FILTER else "filter_tree"
        
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export Item"), f"{node.name}.kpfx", "KPaperFlux Exchange (*.kpfx *.json)")
        if path:
            try:
                ExchangeService.save_to_file(payload_type, node.to_dict(), path)
                show_selectable_message_box(self, self.tr("Export Successful"), self.tr("Exported to %s") % path)
            except Exception as e:
                QMessageBox.critical(self, self.tr("Error"), f"Failed to export: {e}")

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
                show_selectable_message_box(self, self.tr("Move Failed"), str(e), icon=QMessageBox.Icon.Warning)
