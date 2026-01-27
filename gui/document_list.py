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
    edit_requested = pyqtSignal(str) # v28.6
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
        2: "Filename",
        3: "Pages",
        4: "Created",
        5: "Status",
        6: "Type Tags",
        7: "AI Processed",
        8: "Last Used",
        9: "Locked"
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
        
        # Tag Delegate (Column 6: Type Tags)
        self.tree.setItemDelegateForColumn(6, TagDelegate(self.tree))
        
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
        
        settings = QSettings("KPaperFlux", "DocumentList")
        header_state = settings.value("headerState")
        
        # If columns are squashed (first run), fix them
        # Avoid squashing if we already have a saved state
        if not header_state and header.sectionSize(1) < 50:
             for i in range(self.tree.columnCount()):
                 self.tree.resizeColumnToContents(i)
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

    def show_trash_bin(self, enable: bool, refresh: bool = True):
        """Switch between Normal View and Trash View."""
        self.is_trash_mode = enable
        
        # Clear filters if entering trash mode to avoid confusion?
        if enable:
            self.current_filter = {}
            self.current_filter_text = ""
            self.current_advanced_query = None
            
        if refresh:
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
        settings.sync()
        
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
            # Default Hiding: Everything visible in Stage 0/1
            pass

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
             merge_action = menu.addAction(self.tr("Merge Selected Documents"))
        else:
             merge_action = None
    
        # Edit Action (v28.6)
        edit_action = None
        if len(selected_items) == 1:
            edit_action = menu.addAction(self.tr("Edit Document..."))

        reprocess_action = menu.addAction(self.tr("Reprocess / Re-Analyze"))
        
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
        elif edit_action and action == edit_action:
            self.edit_requested.emit(uuids[0])
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
        
        # Phase 102: Update last_used for selected documents
        if self.db_manager and uuids:
            # For performance, maybe only touch the first one or a small batch?
            # Let's touch the primary (last clicked) one, or all if small selection.
            for u in uuids[:5]: # Cap at 5 to avoid thrashing
                self.db_manager.touch_last_used(u)

    def refresh_list(self, force_select_first=False):
        """Fetch docs from DB and populate tree."""
        if not self.db_manager:
            return
            
        try:
             # Store current selection AND current item (keyboard focus)
             selected_uuids = self.get_selected_uuids()
             current_uuid = None
             if self.tree.currentItem():
                 current_uuid = self.tree.currentItem().data(1, Qt.ItemDataRole.UserRole)
             
             # Phase 92: Trash Mode
             if self.is_trash_mode:
                 docs = self.db_manager.get_deleted_entities_view()
             elif self.current_advanced_query:
                 print(f"[DEBUG] refresh_list executing Advanced Query: {self.current_advanced_query}")
                 docs = self.db_manager.search_documents_advanced(self.current_advanced_query)
                 print(f"[DEBUG] Advanced Query returned {len(docs)} documents.")
             else:
                 query = getattr(self, "current_filter_text", None)
                 if query:
                     docs = self.db_manager.search_documents(query)
                 else:
                     docs = self.db_manager.get_all_entities_view()
                 print(f"[DEBUG] Standard View returned {len(docs)} documents.")

             # v28.2: Change Detection / Redraw Prevention
             # We create a footprint of the data to see if a redraw is actually needed.
             current_sig = tuple((d.uuid, d.status, str(d.last_processed_at)) for d in docs)
             
             if not force_select_first and hasattr(self, '_last_refresh_sig') and self._last_refresh_sig == current_sig:
                  # [SILENT] Data is identical to what is currently shown.
                  return
             
             if hasattr(self, '_last_refresh_sig'):
                  print(f"[DEBUG] refresh_list: Change detected in {len(docs)} documents (or forced). Redrawing view.")
             else:
                  print(f"[DEBUG] refresh_list: Initial population ({len(docs)} documents).")
                  
             self._last_refresh_sig = current_sig

        except Exception as e:
             print(f"[ERROR] refresh_list error: {e}")
             docs = []
             
        self.populate_tree(docs)
        
        # Restore selection
        if selected_uuids:
             self.tree.blockSignals(True)
             for uuid in selected_uuids:
                  self.select_document(uuid)
                  if uuid == current_uuid:
                       for i in range(self.tree.topLevelItemCount()):
                           item = self.tree.topLevelItem(i)
                           if item.data(1, Qt.ItemDataRole.UserRole) == uuid:
                               self.tree.setCurrentItem(item)
                               break
             self.tree.blockSignals(False)
        elif force_select_first and docs:
             self.selectRow(0)
             
        self.document_count_changed.emit(len(docs), len(docs)) 
        return


    def select_document(self, uuid: str):
        """Programmatically select a document by UUID."""
        if not uuid:
            return
            
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(1, Qt.ItemDataRole.UserRole) == uuid:
                item.setSelected(True)
                break

    def update_document_item(self, doc):
        """
        Targeted update of a single row in the tree view.
        Prevents flickering and resource waste during AI processing.
        """
        if not doc: return
        
        # 1. Check if update is actually needed (FOOTPRINT CHANGE)
        old_doc = self.documents_cache.get(doc.uuid)
        if old_doc:
             # Compare fields displayed in the list
             if (old_doc.status == doc.status and 
                 old_doc.last_processed_at == doc.last_processed_at and 
                 old_doc.type_tags == doc.type_tags and
                 old_doc.original_filename == doc.original_filename and
                 old_doc.semantic_data == doc.semantic_data):
                  return # Change is irrelevant for view
             
             print(f"[DEBUG] update_document_item: Updating row for {doc.uuid} ({old_doc.status} -> {doc.status})")

        # 1.5 Find matching item
        target_item = None
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(1, Qt.ItemDataRole.UserRole) == doc.uuid:
                target_item = item
                break
        
        if not target_item:
            # If not found, maybe it's a new document? Fallback to refresh.
            self.refresh_list()
            return

        # 2. Update Cache
        self.documents_cache[doc.uuid] = doc
        
        # 3. Format Data
        created_str = format_datetime(doc.created_at)
        filename = doc.original_filename or f"Entity {doc.uuid[:8]}"
        pages_str = str(doc.page_count if doc.page_count is not None else 0)
        status = getattr(doc, "status", "NEW")
        type_tags = getattr(doc, "type_tags", [])
        locked_str = "Yes" if getattr(doc, "locked", False) else "No"
        processed_str = format_datetime(doc.last_processed_at) or "-"
        used_str = format_datetime(doc.last_used) or "-"
        
        # 4. Apply to Columns
        target_item.setText(2, filename)
        target_item.setText(3, pages_str)
        target_item.setText(4, created_str)
        target_item.setText(5, status)
        target_item.setText(6, ", ".join(type_tags))
        target_item.setText(7, processed_str)
        target_item.setText(8, used_str)
        target_item.setText(9, locked_str)

        # 5. Dynamic Columns
        num_fixed = len(self.FIXED_COLUMNS)
        for d_idx, key in enumerate(self.dynamic_columns):
            col_idx = num_fixed + d_idx
            val = getattr(doc, key, None)
            if val is None and doc.semantic_data:
                val = doc.semantic_data.get(key)
            
            if val is None: txt = "-"
            elif isinstance(val, (list, dict)): txt = json.dumps(val)
            else: txt = str(val)
            
            target_item.setText(col_idx, txt)
            if val is not None:
                target_item.setData(col_idx, Qt.ItemDataRole.UserRole, val)

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
                type_tags = getattr(doc, "type_tags", [])
                if target_type not in type_tags:
                    show = False
                    
            if show and target_tags:
                type_tags = getattr(doc, "type_tags", [])
                tag_val = ", ".join(type_tags).lower()
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
            self.current_advanced_query = None 
            self.show_trash_bin(True, refresh=False)
        else:
            self.current_advanced_query = query # Persist
            self.show_trash_bin(False, refresh=False) # Ensure we leave trash mode
            self.current_filter_text = None # Clear simple text search
            
        # Consolidate via refresh_list to benefit from signature checks
        self.refresh_list(force_select_first=True)

    def populate_tree(self, docs):
        """Populate the tree with document data, including dynamic columns."""
        self.tree.setSortingEnabled(False)
        
        # Stability: Capture scroll position
        v_bar = self.tree.verticalScrollBar()
        scroll_val = v_bar.value()
        
        self.tree.clear()
        self.documents_cache = {doc.uuid: doc for doc in docs}
        
        num_fixed = len(self.FIXED_COLUMNS)
        
        for i, doc in enumerate(docs):
            created_str = format_datetime(doc.created_at)
            created_sort = str(doc.created_at) if doc.created_at else ""
            
            filename = doc.original_filename or f"Entity {doc.uuid[:8]}"
            pages_sort = doc.page_count if doc.page_count is not None else 0
            pages_str = str(pages_sort)
            status = getattr(doc, "status", "NEW")
            type_tags = getattr(doc, "type_tags", [])
            locked_str = "Yes" if getattr(doc, "locked", False) else "No"
            
            # Format timestamps
            processed_str = format_datetime(doc.last_processed_at) or "-"
            used_str = format_datetime(doc.last_used) or "-"
            
            col_data = [
                "",                 # 0: # (Handled by Delegate)
                doc.uuid,           # 1: Entity ID
                filename,           # 2: Filename
                pages_str,          # 3: Pages
                created_str,        # 4: Created
                status,             # 5: Status
                ", ".join(type_tags), # 6: Type Tags
                processed_str,      # 7: AI Processed
                used_str,           # 8: Last Used
                locked_str          # 9: Locked
            ]
            
            # Phase 102: Support Dynamic Columns
            for key in self.dynamic_columns:
                # Try to get from Doc attributes or semantic_data dict
                val = getattr(doc, key, None)
                if val is None and doc.semantic_data:
                    val = doc.semantic_data.get(key)
                
                # Format
                if val is None:
                    txt = "-"
                elif isinstance(val, (list, dict)):
                    txt = json.dumps(val)
                else:
                    txt = str(val)
                
                col_data.append(txt)
            
            item = SortableTreeWidgetItem(col_data)
            
            # Set data for identification and sorting
            item.setData(1, Qt.ItemDataRole.UserRole, doc.uuid) # Logical index 1 is UUID
            item.setData(3, Qt.ItemDataRole.UserRole, pages_sort)
            item.setData(4, Qt.ItemDataRole.UserRole, created_sort)
            
            # Sort keys for timestamps
            if hasattr(doc, "last_processed_at") and doc.last_processed_at:
                item.setData(7, Qt.ItemDataRole.UserRole, str(doc.last_processed_at))
            if hasattr(doc, "last_used") and doc.last_used:
                item.setData(8, Qt.ItemDataRole.UserRole, str(doc.last_used))
            
            # Dynamic Columns Sort Data
            for d_idx, key in enumerate(self.dynamic_columns):
                col_idx = num_fixed + d_idx
                val = getattr(doc, key, None)
                if val is None and doc.semantic_data:
                    val = doc.semantic_data.get(key)
                if val is not None:
                    item.setData(col_idx, Qt.ItemDataRole.UserRole, val)
            
            self.tree.addTopLevelItem(item)
            
        self.tree.setSortingEnabled(True)
        # Restore scroll
        v_bar.setValue(scroll_val)
        # Default sort by Created Descending - only if not already sorted by user/state
        # header.sortIndicatorSection() returns the current sort column (-1 if none)
        # Note: If restored state had a sort, it's already set.
        if self.tree.header().sortIndicatorSection() < 0:
             self.tree.sortByColumn(4, Qt.SortOrder.DescendingOrder)
        
        # v28.2 REMOVED: self.document_count_changed.emit(...)
        # Callers (refresh_list, apply_advanced_filter) must emit manually
        # to ensure selection restoration is complete.
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
