from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QTreeWidgetItem, QTreeWidget, QWidget, QVBoxLayout, QAbstractItemView, QStyledItemDelegate, QMessageBox
from PyQt6.QtCore import pyqtSignal, Qt, QPoint, QSettings, QLocale, QEvent, QTimer

class RowNumberDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.text = str(index.row() + 1)
        option.displayAlignment = Qt.AlignmentFlag.AlignCenter

class FixedFirstColumnHeader(QHeaderView):
    def mousePressEvent(self, event):
        # Disable sort click for Column 0
        if self.logicalIndexAt(event.pos()) == 0:
            return
        super().mousePressEvent(event)
from core.database import DatabaseManager
from gui.utils import format_date, format_datetime
from gui.utils import format_date, format_datetime
from gui.export_dialog import ExportDialog
from gui.dialogs.save_list_dialog import SaveListDialog
from core.config import AppConfig
from pathlib import Path
from typing import Optional
import datetime
import os
from core.metadata_normalizer import MetadataNormalizer
from core.metadata_normalizer import MetadataNormalizer
from core.semantic_translator import SemanticTranslator
from gui.delegates.tag_delegate import TagDelegate

class SortableTreeWidgetItem(QTreeWidgetItem):
    def __lt__(self, other):
        tree = self.treeWidget()
        if not tree:
            return super().__lt__(other)

        column = tree.sortColumn()
        key1 = self.data(column, Qt.ItemDataRole.UserRole)
        key2 = other.data(column, Qt.ItemDataRole.UserRole)
        
        # If UserRole data is available and comparable, use it for sorting
        if key1 is not None and key2 is not None:
            try:
                if isinstance(key1, (int, float)) and isinstance(key2, (int, float)):
                    return key1 < key2
                key1_float = float(key1)
                key2_float = float(key2)
                return key1_float < key2_float
            except (ValueError, TypeError):
                # Fallback to string comparison
                return str(key1) < str(key2)
        
        return super().__lt__(other)

class DocumentListWidget(QWidget):
    """
    Widget to display list of documents in a tree view with sorting.
    """
    document_selected = pyqtSignal(list) # List[str] UUIDs
    delete_requested = pyqtSignal(list)
    active_filter_changed = pyqtSignal(dict) # Emitted when a view loads a filter
    reprocess_requested = pyqtSignal(list)
    merge_requested = pyqtSignal(list)
    # export_requested = pyqtSignal(list) # Handled locally via open_export_dialog
    stamp_requested = pyqtSignal(list)
    tags_update_requested = pyqtSignal(list)
    document_count_changed = pyqtSignal(int, int) # visible_count, total_count
    save_list_requested = pyqtSignal(str, list) # name, uuids
    restore_requested = pyqtSignal(list) # Phase 92: Trash Restore
    # Logical Index -> Label Mapping (Fixed Columns)
    FIXED_COLUMNS = {
        0: "#",
        1: "Entity ID",
        2: "Doc Date",
        3: "Sender",
        4: "Type",
        5: "Tags",
        6: "Netto",
        7: "Filename",
        8: "Pages",
        9: "Created",
        10: "Updated",
        11: "Brutto",
        12: "Tax %",
        13: "Postage",
        14: "Packaging",
        15: "IBAN",
        16: "Recipient",
        17: "[v] Sender",
        18: "Status", # Was [v] Date
        19: "[v] Amount"
    }
    purge_requested = pyqtSignal(list)   # Phase 92: Permanent Delete

    def __init__(self, db_manager: DatabaseManager, pipeline: Optional[object] = None):
        super().__init__()
        self.db_manager = db_manager
        self.pipeline = pipeline
        self.current_filter = {}
        self.current_filter_text = ""
        self.current_advanced_query = None # Phase 58: Store advanced query state
        self.dynamic_columns = []
        self.is_trash_mode = False # Phase 92
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.tree = QTreeWidget()
        # Header (Standard)
        # self.tree.setHeader(FixedFirstColumnHeader(...)) -> Removed to enable DnD
        # Standard QTreeWidget header is QHeaderView, which supports DnD if setSectionsMovable(True)
        self.update_headers()
        
        # Row Counter Delegate (Column 0)
        self.tree.setItemDelegateForColumn(0, RowNumberDelegate(self.tree))
        
        # Tag Delegate (Column 5)
        self.tree.setItemDelegateForColumn(5, TagDelegate(self.tree))
        
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setSortingEnabled(True)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        
        # Context Menu
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        
        # Header Menu
        self.tree.header().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.header().customContextMenuRequested.connect(self.show_header_menu)
        self.tree.header().setSectionsMovable(True) # Explicitly enable DnD reordering

        layout.addWidget(self.tree)
        
        # Restore State
        self.restore_state()

        if self.db_manager:
            self.refresh_list()

        # Enforce Resize Modes and sane defaults
        header = self.tree.header()
        
        # If columns are squashed (e.g. valid restoration of 0-width or first run), fix them
        # We check a key column (e.g. Date at index 1)
        if header.sectionSize(1) < 50:
             for i in range(self.tree.columnCount()):
                 self.tree.resizeColumnToContents(i)
                 # Ensure strict minimum
                 if header.sectionSize(i) < 50:
                     header.resizeSection(i, 100)
                     
        for i in range(self.tree.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            
        header.setStretchLastSection(False)
        header.setCascadingSectionResizes(True)
        header.setSectionsMovable(True) # Force enable DnD reordering LAST
        
        # Persistence: Auto-save on move/resize/sort (Debounced)
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000) # 1 second delay
        self._save_timer.timeout.connect(self.save_state)
        
        header.sectionMoved.connect(lambda: self.schedule_save())
        header.sectionResized.connect(lambda: self.schedule_save())
        header.sortIndicatorChanged.connect(lambda: self.schedule_save())
            
    def schedule_save(self):
        """Debounce save operation."""
        self._save_timer.start()
            
    def update_headers(self):
        """Set tree headers including dynamic ones."""
        # Fixed Columns from dict
        labels = [self.tr(self.FIXED_COLUMNS[i]) for i in range(len(self.FIXED_COLUMNS))]
        
        # Dynamic Columns
        labels.extend(self.dynamic_columns)
        self.tree.setHeaderLabels(labels)
            
    def show_header_menu(self, pos: QPoint):
        """Show context menu to configure or hide columns."""
        menu = QMenu(self)
        header = self.tree.header()
        
        # Action to open Manager
        config_action = menu.addAction(self.tr("Configure Columns..."))
        config_action.triggered.connect(self.open_column_manager_slot)
        
        # Determine clicked section
        logic_idx = header.logicalIndexAt(pos)
        
        if logic_idx > 0: # Do not allow hiding Row Counter (0)
            menu.addSeparator()
            col_name = self.tree.headerItem().text(logic_idx)
            hide_action = menu.addAction(self.tr(f"Hide '{col_name}'"))
            
            def hide_slot():
                header.setSectionHidden(logic_idx, True)
                self.save_state()
                
            hide_action.triggered.connect(hide_slot)

        menu.addSeparator()
        views_action = menu.addAction(self.tr("Saved Views..."))
        views_action.triggered.connect(self.open_view_manager_slot)
            
        menu.exec(header.mapToGlobal(pos))

    def open_view_manager_slot(self):
        from gui.view_manager import ViewManagerDialog
        
        dlg = ViewManagerDialog(
            self.filter_tree, 
            parent=self, 
            db_manager=None, # Passed if available, DocumentList might not have it directly?
            # DocumentList is usually child of MainWindow which has db_manager.
            # We might need to access parent or store db_manager.
            current_state_callback=self.get_view_state
        )
        
        # We need db_manager for saving deeply. 
        # Assuming MainWindow sets it or we traverse parent.
        mw = self.window()
        if hasattr(mw, "db_manager"):
            dlg.db_manager = mw.db_manager
            
        dlg.view_selected.connect(self._on_view_loaded)
        dlg.exec()
        
    def _on_view_loaded(self, state):
        filter_data = self.set_view_state(state)
        if filter_data:
            # We have a filter to apply.
            # DocumentListWidget doesn't usually emit filter changes UP, 
            # it receives them. But here the user changed filter via List's View Manager.
            # We should probably notify MainWindow to update the Filter Widget.
            # Or define a signal `view_loaded` that carries the filter.
            self.active_filter_changed.emit(filter_data) 
            # We need to define this signal if not exists.
            
    # Existing methods
    def open_column_manager_slot(self):
        """Open the dynamic column manager dialog."""
        from gui.column_manager_dialog import ColumnManagerDialog
        
        # Get Available Keys
        available = []
        if self.db_manager:
            available = self.db_manager.get_available_extra_keys()
            
        dlg = ColumnManagerDialog(self, self.FIXED_COLUMNS, self.dynamic_columns, available, self.tree.header())
        
        if dlg.exec():
            new_dyn_cols, ordered_items = dlg.get_result()
            
            # 1. Update Dynamic Columns Logic
            self.dynamic_columns = new_dyn_cols
            self.update_headers() # This resets the model columns (logical)
            
            # 2. Refresh List to fetch new data
            self.refresh_list()
            
            # 3. Apply Visual Order and Visibility
            header = self.tree.header()
            
            # 3. Apply Visual Order and Visibility
            header = self.tree.header()
            
            # CRITICAL: Unhide all sections first to ensure moveSection works on full visual indices
            for i in range(header.count()):
                header.showSection(i)
                
            # FORCE Column 0 ("#") to act as visual index 0?
            # Ideally we move Logical 0 to Visual 0 first.
            current_visual_0 = header.visualIndex(0)
            if current_visual_0 != 0:
                header.moveSection(current_visual_0, 0)

            # We iterate through the DESIRED visual order (ordered_items)
            # The dialog returns items WITHOUT Col 0.
            # So the first item in 'ordered_items' should be at visual_pos = 1.
            
            for list_idx, item in enumerate(ordered_items):
                visual_pos = list_idx + 1 # Offset by 1 for "#" column
                
                # Determine Logical Index of this item in the NEW model
                logical_idx = -1
                
                if item["type"] == "fixed":
                    logical_idx = item["orig_idx"]
                elif item["type"] == "dynamic":
                    key = item["key"]
                    if key in self.dynamic_columns:
                        logical_idx = len(self.FIXED_COLUMNS) + self.dynamic_columns.index(key)
                
                if logical_idx != -1:
                    # Move Section
                    current_visual = header.visualIndex(logical_idx)
                    if current_visual != visual_pos: # Only move if necessary
                        header.moveSection(current_visual, visual_pos)
            
            # Apply Visibility separately AFTER reordering
            # Note: Col 0 ("#") is always visible? Or do we allow hiding?
            # Dialog logic excluded it, but context menu allows hiding/showing except #.
            # So we only touch visibility for items in the list. # stays Visible.
            
            for item in ordered_items:
                 logical_idx = -1
                 if item["type"] == "fixed":
                    logical_idx = item["orig_idx"]
                 elif item["type"] == "dynamic":
                    key = item["key"]
                    if key in self.dynamic_columns:
                        logical_idx = len(self.FIXED_COLUMNS) + self.dynamic_columns.index(key)
                        
                 if logical_idx != -1:
                     header.setSectionHidden(logical_idx, not item["visible"])
            
            self.save_state()
        

        
    def toggle_column(self, index: int, visible: bool):
        if visible:
            self.tree.header().showSection(index)
        else:
            self.tree.header().hideSection(index)
        self.save_state()

    def set_dynamic_columns(self, columns):
        """Update the list of dynamic columns to display."""
        self.dynamic_columns = columns
        self.update_headers()
        self.refresh_list()

    def show_trash_bin(self, enable: bool):
        """Switch between Normal View and Trash View."""
        self.is_trash_mode = enable
        
        # Clear filters if entering trash mode to avoid confusion?
        if enable:
            self.current_filter = {}
            self.current_filter_text = ""
            self.current_advanced_query = None
            
        self.refresh_list()
        self.save_state()
        
    def remove_dynamic_column(self, key: str):
        if key not in self.dynamic_columns:
            return
            
        self.dynamic_columns.remove(key)
        self.update_headers()
        self.refresh_list()
        self.save_state()

    def save_state(self):
        settings = QSettings("KPaperFlux", "DocumentList")
        settings.setValue("headerState", self.tree.header().saveState())
        settings.setValue("dynamicColumns", self.dynamic_columns)
        
    def restore_state(self):
        settings = QSettings("KPaperFlux", "DocumentList")
        
        dyn_cols = settings.value("dynamicColumns", [])
        if isinstance(dyn_cols, str): dyn_cols = [dyn_cols]
        elif not isinstance(dyn_cols, list): dyn_cols = []
        
        if dyn_cols:
            self.dynamic_columns = dyn_cols
            self.update_headers()

        state = settings.value("headerState")
        if state:
            self.tree.header().restoreState(state)
            # FORCE Enable DnD because restoreState might reset it to False (legacy state)
            self.tree.header().setSectionsMovable(True)
        else:
            # Default Hiding: Hide Metadata & Finance extras to keep clean
            # Visible: #, UUID, Date, Sender, Type, Tags, Netto, Filename (0-7)
            # Hide: 8 (Pages) ...
            to_hide = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19] 
            for i in to_hide:
                self.tree.header().hideSection(i)

    def get_view_state(self):
        """Capture current filter and layout state for Saved Views."""
        state = {
            "version": 1,
            "dynamic_columns": self.dynamic_columns,
            "header_state": self.tree.header().saveState().data().hex(),
            "filter": self.current_advanced_query if hasattr(self, "current_advanced_query") else None
        }
        return state

    def set_view_state(self, state):
        """Restore a Saved View."""
        if not state: return
        
        # 1. Restore Dynamic Columns
        self.dynamic_columns = state.get("dynamic_columns", [])
        self.update_headers()
        
        # 2. Restore Header Layout
        header_hex = state.get("header_state")
        if header_hex:
            try:
                ba = bytes.fromhex(header_hex)
                self.tree.header().restoreState(ba)
                self.tree.header().setSectionsMovable(True) # Ensure DnD persists
            except Exception as e:
                print(f"Error restoring header state: {e}")
                
        # 3. Apply Filter (Caller must handle this? Or we emit signal?)
        # DocumentListWidget usually receives filter, doesn't generate it.
        # But if the View contains the filter, the ListWidget acts as the applier?
        # Ideally, MainWindow handles the filter application part.
        # But here we can return the filter to the caller.
        return state.get("filter")

    def delete_selected_documents(self, uuids: list[str]):
        """Filter out locked documents before requesting deletion."""
        to_delete = []
        skipped = 0
        
        for uuid in uuids:
             doc = self.documents_cache.get(uuid)
             if doc and getattr(doc, 'locked', False):
                 skipped += 1
                 continue
             to_delete.append(uuid)
             
        if skipped > 0:
             QMessageBox.information(
                 self,
                 self.tr("Locked Documents"),
                 self.tr(f"{skipped} document(s) are locked and cannot be deleted.")
             )
             
        if to_delete:
             self.delete_requested.emit(to_delete)

    def show_context_menu(self, pos: QPoint):
        """Show context menu for selected item."""
        item = self.tree.itemAt(pos)
        if not item:
            return
            
        uuid = item.data(1, Qt.ItemDataRole.UserRole)
        if not uuid:
            return
            
        menu = QMenu(self)
        
        selected_items = self.tree.selectedItems()
        
        if len(selected_items) > 1:
             merge_action = menu.addAction(self.tr("Merge Selected"))
        else:
             merge_action = None
    
        reprocess_action = menu.addAction(self.tr("Reprocess / Re-Analyze"))
        
        # Split Action (Only for single multi-page doc)
        split_action = None
        if len(selected_items) == 1:
            doc = self.documents_cache.get(uuid)
            if doc and getattr(doc, 'page_count', 0) > 1:
                split_action = menu.addAction(self.tr("Split Document..."))
                
        tags_action = menu.addAction(self.tr("Manage Tags..."))
        stamp_action = menu.addAction(self.tr("Stamp..."))
        menu.addSeparator()
        save_list_action = menu.addAction(self.tr("Save as List..."))
        save_list_action.triggered.connect(self.save_as_list)
        menu.addSeparator()
        export_action = menu.addAction(self.tr("Export Selected..."))
        export_all_action = menu.addAction(self.tr("Export All Visible..."))
        menu.addSeparator()
        
        if self.is_trash_mode:
             restore_action = menu.addAction(self.tr("Restore"))
             purge_action = menu.addAction(self.tr("Delete Permanently"))
             reprocess_action = None # Disable reprocess in trash
             delete_action = None
        else:
             delete_action = menu.addAction(self.tr("Delete Document"))
             restore_action = None
             purge_action = None
        
        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        
        uuids = []
        for i in selected_items:
            u = i.data(1, Qt.ItemDataRole.UserRole)
            if u: uuids.append(u)
        
        if not uuids and uuid:
            uuids = [uuid]
            
        if action == reprocess_action:
            self.reprocess_requested.emit(uuids)
        elif split_action and action == split_action:
            self.split_requested.emit(uuids[0])
        elif action == delete_action:
            self.delete_selected_documents(uuids)
        elif merge_action and action == merge_action:
             self.merge_requested.emit(uuids)
        elif action == tags_action:
             self.tags_update_requested.emit(uuids)
        elif action == stamp_action:
            self.stamp_requested.emit(uuids)
        elif action == export_action:
            # Get selected documents
            docs = []
            for u in uuids:
                if u in self.documents_cache:
                    docs.append(self.documents_cache[u])
            self.open_export_dialog(docs)
        elif action == export_all_action:
            # Get ALL visible documents (respecting filters)
            docs = self.get_visible_documents()
            self.open_export_dialog(docs)
        
        # Phase 92: Trash Actions
        elif self.is_trash_mode:
            if action == restore_action:
                self.restore_requested.emit(uuids)
            elif action == purge_action:
                confirm = QMessageBox.question(
                    self, 
                    self.tr("Delete Permanently"), 
                    self.tr(f"Are you sure you want to permanently delete {len(uuids)} document(s)?\nThis cannot be undone."),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if confirm == QMessageBox.StandardButton.Yes:
                     self.purge_requested.emit(uuids)

    def get_visible_documents(self) -> list:
        """Return list of Document objects currently visible in the tree."""
        visible_docs = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if not item.isHidden():
                uuid = item.data(1, Qt.ItemDataRole.UserRole)
                if uuid in self.documents_cache:
                    visible_docs.append(self.documents_cache[uuid])
        return visible_docs

    def _on_selection_changed(self):
        """Emit signal with selected UUID(s)."""
        selected_items = self.tree.selectedItems()
        uuids = []
        for item in selected_items:
            u = item.data(1, Qt.ItemDataRole.UserRole)
            if u: uuids.append(u)
        
        self.document_selected.emit(uuids)

    def refresh_list(self):
        """Fetch docs from DB and populate tree."""
        if not self.db_manager:
            return
            
        try:
             # Phase 92: Trash Mode
             if self.is_trash_mode:
                 docs = self.db_manager.get_deleted_documents()
                 # TODO: Apply basic text filter on trash? For now, show all.
                 
             # Prioritize Advanced Query if active
             elif self.current_advanced_query:
                 docs = self.db_manager.search_documents_advanced(self.current_advanced_query)
             else:
                 query = getattr(self, "current_filter_text", None)
                 if query:
                     docs = self.db_manager.search_documents(query)
                     docs = self.db_manager.search_documents(query)
                 else:
                     # Phase 98: Switch to Entity View
                     docs = self.db_manager.get_all_entities_view()

        except:
             docs = []
             
        self.populate_tree(docs)
        return


    def select_document(self, uuid: str):
        """Programmatically select a document by UUID."""
        if not uuid:
            return
            
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(1, Qt.ItemDataRole.UserRole) == uuid:
                item.setSelected(True)
                self.tree.scrollToItem(item)
                break

    def apply_filter(self, criteria: dict):
        """
        Filter items based on criteria.
        """
        self.current_filter = criteria
        
        date_from = criteria.get('date_from')
        date_to = criteria.get('date_to')
        target_type = criteria.get('type')
        target_tags = criteria.get('tags')
        text_search = criteria.get('text_search')
        
        visible_count = 0
        total_count = self.tree.topLevelItemCount()
        
        for i in range(total_count):
            item = self.tree.topLevelItem(i)
            show = True
            
            uuid = item.data(1, Qt.ItemDataRole.UserRole)
            doc = self.documents_cache.get(uuid)
            
            if date_from or date_to:
                date_val = str(doc.doc_date) if doc and doc.doc_date else ""
                
                if not date_val:
                    if date_from or date_to: show = False
                else:
                    if date_from and date_val < date_from:
                        show = False
                    if date_to and date_val > date_to:
                        show = False
            
            if show and target_type:
                type_val = doc.doc_type if doc and doc.doc_type else ""
                if target_type != type_val:
                    show = False
                    
            if show and target_tags:
                tag_val = doc.tags.lower() if doc and doc.tags else ""
                if target_tags.lower() not in tag_val:
                    show = False

            if show and text_search and doc:
                query = text_search.lower()
                haystack = [
                    doc.sender or "",
                    doc.doc_type or "",
                    doc.tags or "",
                    doc.original_filename or "",
                    doc.sender_address or "",
                    doc.text_content or "",
                    doc.recipient_company or "",
                    doc.recipient_name or "",
                    doc.recipient_city or "",
                    doc.sender_company or "",
                    doc.sender_city or "",
                    str(doc.page_count or ""),
                    str(doc.created_at or "")
                ]
                full_text = " ".join(haystack).lower()
                if query not in full_text:
                    show = False
            
            item.setHidden(not show)
            if show:
                visible_count += 1
                
        self.document_count_changed.emit(visible_count, total_count)

    def rowCount(self) -> int:
        """Compatibility method for MainWindow (QTreeWidget -> QTableWidget check)."""
        return self.tree.topLevelItemCount()
        
    def selectedItems(self) -> list[QTreeWidgetItem]:
        """Compatibility method for MainWindow (QTreeWidget -> QTableWidget check)."""
        return self.tree.selectedItems()

    def selectRow(self, row: int):
        """Compatibility method for MainWindow (QTableWidget -> QTreeWidget)."""
        if 0 <= row < self.tree.topLevelItemCount():
            item = self.tree.topLevelItem(row)
            item.setSelected(True)
            self.tree.scrollToItem(item)

    def item(self, row: int, column: int = 0) -> QTreeWidgetItem:
        """Compatibility method for MainWindow (QTableWidget -> QTreeWidget)."""
        # QTreeWidget doesn't have 'cells', it has Items. 
        # MainWindow uses this to check if a row is selected -> item(row, 0).isSelected()
        if 0 <= row < self.tree.topLevelItemCount():
            return self.tree.topLevelItem(row)
        return None

    def get_selected_uuids(self) -> list[str]:
        """Return list of UUIDs for selected items."""
        uuids = set()
        for item in self.tree.selectedItems():
            uid = item.data(1, Qt.ItemDataRole.UserRole)
            if uid:
                uuids.add(uid)
        return list(uuids)

    def select_rows_by_uuids(self, uuids: list[str]):
        """Select items matching the given UUIDs."""
        self.tree.clearSelection()
        if not uuids: 
            return
        
        uuid_set = set(uuids)
        
        if self.tree.selectionMode() == QAbstractItemView.SelectionMode.SingleSelection and len(uuids) > 1:
             uuid_set = {uuids[0]}
             
        for i in range(self.tree.topLevelItemCount()):
             item = self.tree.topLevelItem(i)
             uid = item.data(1, Qt.ItemDataRole.UserRole)
             if uid in uuid_set and not item.isHidden():
                 item.setSelected(True)

    def apply_advanced_filter(self, query: dict):
        """Apply advanced search query."""
        print(f"[DEBUG] DocumentList Received Query: {query}")
        
        # Check if query implies Trash Mode
        is_trash = False
        # Basic check for single condition or root group
        # If user explicitly filters for 'deleted', switch mode
        # Helper usually better, but inline for MVP:
        def check_trash(q):
            if not q: return False
            if "field" in q and q["field"] == "deleted":
                val = q.get("value")
                # Robust check for True/true/1
                if val is True: return True
                if isinstance(val, str) and val.lower() in ("true", "1", "yes"): return True
                if isinstance(val, int) and val == 1: return True
                return False
            if "conditions" in q:
                return any(check_trash(c) for c in q["conditions"])
            return False
            
        is_mode_trash = check_trash(query)
        print(f"[DEBUG] check_trash result: {is_mode_trash} for query: {query}")
        
        if is_mode_trash:
            self.show_trash_bin(True)
            self.current_advanced_query = None # Trash Mode takes precedence/is the mode
            # But wait, what if they want "Deleted AND Type=Invoice"?
            # For now, Trash Mode is a global toggle. Filters inside Trash are TODO.
            # We just show All Trash.
        else:
            self.show_trash_bin(False) # Ensure we leave trash mode
            self.current_advanced_query = query # Persist
            self.current_filter_text = None # Clear simple text search
            
            docs = self.db_manager.search_documents_advanced(query)
            self.populate_tree(docs)
            if docs:
                self.selectRow(0)

    def populate_tree(self, docs):
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        self.documents_cache = {doc.uuid: doc for doc in docs}
        
        for i, doc in enumerate(docs):
            # --- Field Formatting ---
            doc_date_str = format_date(doc.doc_date)
            date_sort = str(doc.doc_date) if doc.doc_date else "" 
            
            created_str = format_datetime(doc.created_at)
            created_sort = str(doc.created_at) if doc.created_at else ""

            updated_str = format_datetime(doc.last_processed_at)
            updated_sort = str(doc.last_processed_at) if doc.last_processed_at else ""
            
            sender = doc.sender or ""
            doc_type = doc.doc_type
            if isinstance(doc_type, list):
                doc_type = ", ".join(doc_type)
            doc_type = doc_type or ""
            tags = doc.tags or ""
            filename = doc.original_filename or ""
            
            # Helper for formatting monetary values
            def format_money(val, curr):
                s_sort = 0.0
                s_str = ""
                if val is not None:
                    try:
                        s_sort = float(val)
                        s_str = f"{s_sort:.2f}"
                        if curr: s_str += f" {curr}"
                    except:
                        s_str = str(val)
                return s_str, s_sort

            amount_str, amount_sort = format_money(doc.amount, doc.currency)
            gross_str, gross_sort = format_money(doc.gross_amount, doc.currency)
            postage_str, postage_sort = format_money(doc.postage, doc.currency)
            packaging_str, packaging_sort = format_money(doc.packaging, doc.currency)
            
            # Tax
            tax_sort = 0.0
            tax_str = ""
            if doc.tax_rate is not None:
                try:
                    tax_sort = float(doc.tax_rate)
                    tax_str = f"{tax_sort:.1f}%"
                except:
                    tax_str = str(doc.tax_rate)
            
            iban = doc.iban or ""
            recipient = doc.recipient_company or doc.recipient_name or ""
            
            pages_sort = doc.page_count if doc.page_count is not None else 0
            pages_str = str(pages_sort) if doc.page_count is not None else ""

            # Columns 0-16
            col_data = [
                "",                 # 0: # (Handled by Delegate)
                doc.uuid,           # 1
                doc_date_str,       # 2
                sender,             # 3
                doc_type,           # 4
                tags,               # 5
                amount_str,         # 6
                filename,           # 7
                pages_str,          # 8
                created_str,        # 9
                updated_str,        # 10
                gross_str,          # 11
                tax_str,            # 12
                postage_str,        # 13
                packaging_str,      # 14
                iban,               # 15
                recipient,          # 16
                doc.v_sender or "", # 17
                doc.extra_data.get("entity_status", "") if doc.extra_data else "",# 18 (Status)
                str(doc.v_amount) if doc.v_amount is not None else "" # 19
            ]
            
            if doc.extra_data:
                 for key in self.dynamic_columns:
                     val = ""
                     parts = key.split('.')
                     data = doc.extra_data
                     for p in parts:
                         if isinstance(data, dict):
                             data = data.get(p)
                         elif isinstance(data, list):
                             if data and isinstance(data[0], dict):
                                 data = data[0].get(p)
                             else:
                                 data = None
                         else:
                             data = None
                         if data is None: break
                     
                     if data is not None:
                         val = str(data)
                     col_data.append(val)
            else:
                 col_data.extend([""] * len(self.dynamic_columns))
            
            item = SortableTreeWidgetItem(col_data)
            
            if getattr(doc, 'locked', False):
                 for c in range(item.columnCount()):
                     item.setForeground(c, Qt.GlobalColor.gray)
            
            item.setData(0, Qt.ItemDataRole.UserRole, i + 1)
            item.setData(1, Qt.ItemDataRole.UserRole, doc.uuid)
            item.setData(2, Qt.ItemDataRole.UserRole, date_sort)
            item.setData(6, Qt.ItemDataRole.UserRole, amount_sort)
            item.setData(8, Qt.ItemDataRole.UserRole, pages_sort)
            item.setData(9, Qt.ItemDataRole.UserRole, created_sort)
            item.setData(10, Qt.ItemDataRole.UserRole, updated_sort)
            item.setData(11, Qt.ItemDataRole.UserRole, gross_sort)
            item.setData(12, Qt.ItemDataRole.UserRole, tax_sort)
            item.setData(13, Qt.ItemDataRole.UserRole, postage_sort)
            item.setData(14, Qt.ItemDataRole.UserRole, packaging_sort)
            
            # Tooltips for truncated content (DocType=4, Tags=5)
            if doc_type:
                item.setData(4, Qt.ItemDataRole.ToolTipRole, doc_type)
            if tags:
                item.setData(5, Qt.ItemDataRole.ToolTipRole, tags)
            item.setData(13, Qt.ItemDataRole.UserRole, postage_sort)
            item.setData(14, Qt.ItemDataRole.UserRole, packaging_sort)
            
            self.tree.addTopLevelItem(item)

        self.tree.setSortingEnabled(True)
        
        if self.current_filter:
             self.apply_filter(self.current_filter)
        else:
             self.document_count_changed.emit(len(docs), len(docs))
    def open_export_dialog(self, documents: list):
        if not documents:
             QMessageBox.warning(self, self.tr("Export"), self.tr("No documents to export."))
             return
             
        # Resolve file paths if missing
        vault_path_str = AppConfig().get_vault_path()
        if vault_path_str:
            vault_path = Path(vault_path_str)
            for doc in documents:
                if not doc.file_path:
                    # Construct default path
                    # Try UUID.pdf
                    potential = vault_path / f"{doc.uuid}.pdf"
                    if potential.exists():
                        doc.file_path = str(potential)

        dlg = ExportDialog(self, documents)
        dlg.exec()

    def save_as_list(self):
        # Determine if selection exists
        selected = self.tree.selectedItems()
        has_selection = bool(selected)
        
        dlg = SaveListDialog(self, has_selection=has_selection)
        if dlg.exec():
            name, only_selection = dlg.get_data()
            
            target_uuids = []
            if only_selection and has_selection:
                # Get Selected UUIDs
                for item in selected:
                     uuid = item.data(1, Qt.ItemDataRole.UserRole)
                     if uuid:
                         target_uuids.append(uuid)
            else:
                # Get All Displayed UUIDs
                count = self.tree.topLevelItemCount()
                for i in range(count):
                    item = self.tree.topLevelItem(i)
                    if not item.isHidden():
                        uuid = item.data(1, Qt.ItemDataRole.UserRole)
                        if uuid:
                            target_uuids.append(uuid)
                            
            if target_uuids:
                 self.save_list_requested.emit(name, target_uuids)
