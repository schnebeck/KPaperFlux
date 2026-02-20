"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/document_list.py
Version:        2.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Gemini 3pro
Description:    Main document list widget with tree representation and sorting.
------------------------------------------------------------------------------
"""

from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QTreeWidgetItem,
    QTreeWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QAbstractItemView, QStyledItemDelegate, QMessageBox, QTreeWidgetItemIterator, QDialog
)
from PyQt6.QtCore import pyqtSignal, Qt, QPoint, QSettings, QLocale, QEvent, QTimer
from PyQt6.QtGui import QBrush, QColor
from pathlib import Path
from typing import Optional, List, Any, Dict
import datetime
import os
import json
from core.logger import get_logger

logger = get_logger("gui.document_list")

# Core Imports
from gui.utils import show_selectable_message_box
from core.database import DatabaseManager
from core.config import AppConfig
from core.metadata_normalizer import MetadataNormalizer
from core.semantic_translator import SemanticTranslator

# GUI Imports
from gui.utils import format_date, format_datetime, show_selectable_message_box
from gui.export_dialog import ExportDialog
from gui.dialogs.save_list_dialog import SaveListDialog
from gui.delegates.tag_delegate import TagDelegate
from gui.view_manager import ViewManagerDialog
from gui.column_manager_dialog import ColumnManagerDialog

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
    stage2_requested = pyqtSignal(list)
    # export_requested = pyqtSignal(list) # Handled locally via open_export_dialog
    stamp_requested = pyqtSignal(list)
    tags_update_requested = pyqtSignal(list)
    document_count_changed = pyqtSignal(int, int) # visible_count, total_count
    save_list_requested = pyqtSignal(str, list) # name, uuids
    restore_requested = pyqtSignal(list) # Phase 92: Trash Restore
    apply_rule_requested = pyqtSignal(object, str) # rule_node, scope ("SELECTED")
    show_generic_requested = pyqtSignal(str) # UUID
    purge_requested = pyqtSignal(list)   # Phase 92: Permanent Delete
    TAG_MAPPING = {
        "CTX_PRIVATE": "Private",
        "CTX_BUSINESS": "Business",
        "INBOUND": "Inbound",
        "OUTBOUND": "Outbound",
        "INTERNAL": "Internal"
    }

    STATUS_MAP = {
        "NEW": "New",
        "READY_FOR_PIPELINE": "Ready for Pipeline",
        "PROCESSING": "Processing",
        "PROCESSING_S1": "Processing (Stage 1)",
        "PROCESSING_S1_5": "Processing (Stamps)",
        "PROCESSING_S2": "Processing (Semantic)",
        "STAGE1_HOLD": "On Hold (Stage 1)",
        "STAGE1_5_HOLD": "On Hold (Stamps)",
        "STAGE2_HOLD": "On Hold (Semantic)",
        "PROCESSED": "Processed",
        "ERROR": "Error"
    }

    def _get_fixed_column_labels(self):
        """Returns translated labels for fixed columns."""
        return {
            0: "#",
            1: self.tr("Entity ID"),
            2: self.tr("Filename"),
            3: self.tr("Pages"),
            4: self.tr("Imported Date"),
            5: self.tr("Used Date"),
            6: self.tr("Deleted Date"),
            7: self.tr("Locked Date"),
            8: self.tr("Autoprocessed Date"),
            9: self.tr("Exported Date"),
            10: self.tr("Status"),
            11: self.tr("Type Tags"),
            12: self.tr("Tags")
        }

    def _get_semantic_labels(self):
        """Returns translated labels for semantic fields."""
        return {
            "doc_date": self.tr("Date"),
            "sender_name": self.tr("Sender"),
            "total_amount": self.tr("Amount"),
            "total_gross": self.tr("Gross Amount"),
            "total_net": self.tr("Net Amount"),
            "invoice_number": self.tr("Invoice #")
        }

    def __init__(self, 
                 db_manager: Optional[DatabaseManager] = None, 
                 filter_tree: Any = None, 
                 plugin_manager: Any = None, 
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db_manager = db_manager
        self.filter_tree = filter_tree
        self.plugin_manager = plugin_manager
        
        self.is_trash_mode = False
        self.current_filter = {}
        self.current_filter_text = ""
        self.current_advanced_query = None
        self.current_cockpit_query = None # Phase 105: Cockpit Precedence
        self.advanced_filter_active = True   # Phase 105: Active Rule Toggle
        self.target_uuid_to_restore = None   # Phase 105: Programmatic override
        self.current_hit_map: Dict[str, int] = {} # Phase 106: hit counts
        self.dynamic_columns = []
        self.is_trash_mode = False
        self.view_context = self.tr("All Documents") # For Breadcrumb
        self.fixed_columns = self._get_fixed_column_labels()
        self.semantic_labels = self._get_semantic_labels()
        self.status_labels = {k: self.tr(v) for k, v in self.STATUS_MAP.items()}
        self.tag_labels = {k: self.tr(v) for k, v in self.TAG_MAPPING.items()}

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Breadcrumb Bar ---
        self.breadcrumb_bar = QWidget()
        self.breadcrumb_bar.setObjectName("breadcrumbBar")
        # Dezent styling via code or just font
        bc_layout = QHBoxLayout(self.breadcrumb_bar)
        bc_layout.setContentsMargins(10, 5, 10, 5)

        self.lbl_breadcrumb = QLabel()
        self.lbl_breadcrumb.setStyleSheet("font-weight: bold; color: #555;")
        bc_layout.addWidget(self.lbl_breadcrumb)
        bc_layout.addStretch()

        self.btn_reset_view = QPushButton("×")
        self.btn_reset_view.setToolTip(self.tr("Reset View / Show All"))
        self.btn_reset_view.setFixedSize(20, 20)
        self.btn_reset_view.setStyleSheet("font-weight: bold; border-radius: 10px; border: none; background: #eee;")
        self.btn_reset_view.clicked.connect(self.clear_filters)
        bc_layout.addWidget(self.btn_reset_view)

        layout.addWidget(self.breadcrumb_bar)

        self.tree = QTreeWidget()
        # Header (Standard)
        # self.tree.setHeader(FixedFirstColumnHeader(...)) -> Removed to enable DnD
        # Standard QTreeWidget header is QHeaderView, which supports DnD if setSectionsMovable(True)
        self.update_headers()

        # Row Counter Delegate (Column 0)
        self.tree.setItemDelegateForColumn(0, RowNumberDelegate(self.tree))

        # Tag Delegates
        self.tree.setItemDelegateForColumn(12, TagDelegate(self.tree))
        self.tree.setItemDelegateForColumn(13, TagDelegate(self.tree))

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

        # Phase 113: Lazy Loading / Infinite Scroll
        self.CHUNK_SIZE = 100
        self._all_docs = []
        self._loaded_count = 0
        self.tree.verticalScrollBar().valueChanged.connect(self._check_scroll_bottom)

        # 5. Initialization and Restoration
        self.update_breadcrumb()
        
        # Enforce Resize Modes and sane defaults
        header = self.tree.header()
        
        # Restore State (loads columns and visibility)
        self.restore_state()

        if self.db_manager:
            self.refresh_list()

        # Final Header setup
        header.setStretchLastSection(False)
        header.setCascadingSectionResizes(True)
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)

        # Persistence: Auto-save on move/resize/sort (Debounced)
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000) # 1 second delay
        self._save_timer.timeout.connect(self.save_state)

        header.sectionMoved.connect(lambda *args: self.schedule_save())
        header.sectionResized.connect(lambda *args: self.schedule_save())
        header.sortIndicatorChanged.connect(lambda *args: self.schedule_save())

    def schedule_save(self):
        """Debounce save operation."""
        self._save_timer.start()

    def update_headers(self):
        """Set tree headers including dynamic ones."""
        # Fixed Columns from dict
        labels = [self.fixed_columns[i] for i in range(len(self.fixed_columns))]

        # Dynamic Columns (with pretty labels for known semantic keys)
        for key in self.dynamic_columns:
            label = self.semantic_labels.get(key, key)
            labels.append(label)

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
        dlg = ViewManagerDialog(
            self.filter_tree,
            parent=self,
            db_manager=None,
            current_state_callback=self.get_view_state
        )

        mw = self.window()
        if hasattr(mw, "save_filter_tree"):
            dlg.save_callback = mw.save_filter_tree

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

        # Get Available Keys
        available = []
        if self.db_manager:
            available = self.db_manager.get_available_extra_keys()
            
        # Add Semantic Shortcuts
        for shortcut in ["doc_date", "sender_name", "total_amount"]:
            if shortcut not in available:
                available.append(shortcut)

        dlg = ColumnManagerDialog(self, self.fixed_columns, self.dynamic_columns, available, self.tree.header())

        if dlg.exec():
            new_dyn_cols, ordered_items = dlg.get_result()

            # 1. Update Dynamic Columns Logic
            self.dynamic_columns = new_dyn_cols
            self.update_headers() # This resets the model columns (logical)

            # 2. Refresh List to fetch new data
            self.refresh_list()

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
                        logical_idx = len(self.fixed_columns) + self.dynamic_columns.index(key)

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
                        logical_idx = len(self.fixed_columns) + self.dynamic_columns.index(key)

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
            # Phase 110: Default Sort for Trash (Column 6: Deleted Date)
            self.tree.sortByColumn(6, Qt.SortOrder.DescendingOrder)

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
        settings = QSettings()
        settings.beginGroup("DocumentList")
        settings.setValue("headerState", self.tree.header().saveState())
        settings.setValue("dynamicColumns", self.dynamic_columns)
        settings.endGroup()
        settings.sync()

    def restore_state(self):
        settings = QSettings()
        settings.beginGroup("DocumentList")

        # Use an empty list as default if no settings exist
        dyn_cols = settings.value("dynamicColumns", [])
        if isinstance(dyn_cols, str): dyn_cols = [dyn_cols]
        elif not isinstance(dyn_cols, list): dyn_cols = []

        self.dynamic_columns = dyn_cols
        self.update_headers()

        state = settings.value("headerState")
        header = self.tree.header()
        if state:
            header.restoreState(state)
        
        # Enforce header properties (DnD and Sorting)
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)
        
        # Enforce resize modes
        for i in range(self.tree.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setCascadingSectionResizes(True)

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
                header = self.tree.header()
                header.restoreState(ba)
                header.setSectionsMovable(True) 
                header.setSectionsClickable(True)
            except Exception as e:
                logger.info(f"Error restoring header state: {e}")

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
             if doc and getattr(doc, 'is_immutable', False):
                 skipped += 1
                 continue
             to_delete.append(uuid)

        if skipped > 0:
             show_selectable_message_box(
                 self,
                 self.tr("Locked Documents"),
                 self.tr(f"{skipped} document(s) are locked and cannot be deleted."),
                 icon=QMessageBox.Icon.Information
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
        
        # Phase 112: Debug Option
        debug_action = None
        if len(selected_items) == 1:
            menu.addSeparator()
            debug_action = menu.addAction(self.tr("Show generic Document"))
            menu.addSeparator()

        # --- Semantic Data Submenu ---
        semantic_submenu = menu.addMenu(self.tr("Semantic Data"))
        extract_selection_action = semantic_submenu.addAction(self.tr("Extract from Selection"))
        extract_view_action = semantic_submenu.addAction(self.tr("Extract from View"))

        if not selected_items:
            extract_selection_action.setEnabled(False)

        tags_action = menu.addAction(self.tr("Manage Tags..."))
        stamp_action = menu.addAction(self.tr("Stamp..."))

        # Phase 106: Apply Rules
        if self.filter_tree:
            rules_menu = menu.addMenu(self.tr("Apply Rule..."))
            active_rules = self.filter_tree.get_active_rules(only_auto=False)
            if active_rules:
                for rule in active_rules:
                    act = rules_menu.addAction(rule.name)
                    # Use closure for loop variable
                    act.triggered.connect(lambda checked, r=rule: self.apply_rule_requested.emit(r, "SELECTED"))
            else:
                rules_menu.setEnabled(False)
                rules_menu.setToolTip(self.tr("No active rules found in Filter Tree."))

        menu.addSeparator()
        save_list_action = menu.addAction(self.tr("Save as List..."))
        save_list_action.triggered.connect(self.save_as_list)
        menu.addSeparator()
        export_action = menu.addAction(self.tr("Export Selected..."))
        export_all_action = menu.addAction(self.tr("Export All Visible..."))
        menu.addSeparator()
        
        # --- Phase 200: Plugin Actions ---
        if self.plugin_manager and len(selected_items) == 1:
            plugin_results = self.plugin_manager.trigger_hook("get_context_menu_actions", uuid)
            # plugin_results is a list of lists (one list per plugin)
            has_plugin_actions = False
            for action_list in plugin_results:
                if action_list:
                    if not has_plugin_actions:
                         menu.addSeparator()
                         has_plugin_actions = True
                    for p_act in action_list:
                        m_action = menu.addAction(p_act["label"])
                        # Use closure for callback
                        m_action.triggered.connect(lambda checked, cb=p_act["callback"], uid=uuid: cb(uid))

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
        elif action == extract_selection_action:
            self.stage2_requested.emit(uuids)
        elif action == extract_view_action:
            # Get all visible UUIDs
            visible_uuids = []
            count = self.tree.topLevelItemCount()
            for i in range(count):
                item = self.tree.topLevelItem(i)
                if not item.isHidden():
                    v_uid = item.data(1, Qt.ItemDataRole.UserRole)
                    if v_uid: visible_uuids.append(v_uid)
            if visible_uuids:
                self.stage2_requested.emit(visible_uuids)
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
        elif action == debug_action:
            self.show_generic_requested.emit(uuid)
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
                confirm = show_selectable_message_box(
                    self,
                    self.tr("Delete Permanently"),
                    self.tr(f"Are you sure you want to permanently delete {len(uuids)} document(s)?\nThis cannot be undone."),
                    icon=QMessageBox.Icon.Question,
                    buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
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

    def refresh_list(self, force_select_first=False):
        """Fetch docs from DB and populate tree."""
        if not self.db_manager:
            return

        # Store current selection AND current item (keyboard focus)
        selected_uuids = self.get_selected_uuids()
        current_uuid = None
        current_row_index = -1
        if self.tree.currentItem():
            item = self.tree.currentItem()
            current_uuid = item.data(1, Qt.ItemDataRole.UserRole)
            current_row_index = self.tree.indexOfTopLevelItem(item)

        # Phase 105: Tiered Query Selection
        active_query = None
        search_text = getattr(self, "current_filter_text", "")
        if not search_text:
             # Check for active query meta as fallback
             pass 
        if self.is_trash_mode:
            docs = self.db_manager.get_deleted_entities_view()
        else:
            # FIX: Prioritize Advanced Filter (Search) if it is set, regardless of "active" flag if it comes from search
            # The issue was that Cockpit Filter was overriding Search.
            # We assume if current_advanced_query is SET, it should be used.
            # advanced_filter_active might be toggled by the UI checkbox, but search should override.
            if self.current_advanced_query:
                active_query = self.current_advanced_query
                logger.info(f"[DEBUG] refresh_list: Using Advanced/Search Filter: {active_query}")
            elif self.current_cockpit_query:
                active_query = self.current_cockpit_query
                logger.info(f"[DEBUG] refresh_list: Rule Editor INACTIVE. Using Cockpit Filter: {active_query}")

            if active_query:
                 docs = self.db_manager.search_documents_advanced(active_query)
            else:
                query_text = getattr(self, "current_filter_text", None)
                if query_text:
                    docs = self.db_manager.search_documents(query_text)
                else:
                    docs = self.db_manager.get_all_entities_view()
                logger.info(f"[DEBUG] Standard View returned {len(docs)} documents.")

            # Phase 106: Calculate hit counts if search is active
            if not search_text and active_query:
                search_text = active_query.get('_meta_fulltext')
            
            self.current_hit_map = {}
            if search_text and len(search_text.strip()) >= 2:
                uuids = [d.uuid for d in docs]
                if uuids:
                    self.current_hit_map = self.db_manager.get_hit_counts_for_documents(uuids, search_text)

        # v28.2: Change Detection / Redraw Prevention
        # We include all timestamps to ensure triggers from the DB are reflected immediately
        current_sig = tuple(
            (d.uuid, d.status, str(d.last_processed_at), str(d.last_used), str(d.deleted_at), str(d.locked_at))
            for d in docs
        ) + tuple(self.dynamic_columns) + (search_text,)

        if not force_select_first and hasattr(self, '_last_refresh_sig') and self._last_refresh_sig == current_sig:
             # [SILENT] Data is identical to what is currently shown.
             return

        if hasattr(self, '_last_refresh_sig'):
             logger.info(f"[DEBUG] refresh_list: Change detected in {len(docs)} documents (or forced). Redrawing view.")
        else:
             logger.info(f"[DEBUG] refresh_list: Initial population ({len(docs)} documents).")

        self._last_refresh_sig = current_sig

        self.populate_tree(docs)

        # User Feedback: Auto-select if exactly one result OR if a specific query/search is active
        # This ensures immediate display of the top result after a search.
        if len(docs) == 1 or active_query:
            force_select_first = True

        # Re-apply basic filter (hide/show) if one was active
        if hasattr(self, "current_filter") and self.current_filter:
             self.apply_filter(self.current_filter)


        # Phase 105: Selection Resilience
        self.tree.blockSignals(True)
        restored = False

        # 1. Higher Priority: Explicit Target ( from Cockpit or Re-analysis)
        if self.target_uuid_to_restore:
             self.select_document(self.target_uuid_to_restore)
             self.target_uuid_to_restore = None
             restored = bool(self.tree.selectedItems())

        # 2. Medium Priority: Previous Selection
        if not restored and selected_uuids:
             for uuid in selected_uuids:
                  self.select_document(uuid)
                  if uuid == current_uuid:
                       for i in range(self.tree.topLevelItemCount()):
                           item = self.tree.topLevelItem(i)
                           if item.data(1, Qt.ItemDataRole.UserRole) == uuid:
                               self.tree.setCurrentItem(item)
                               break
             restored = bool(self.tree.selectedItems())

        # 3. Medium-Low Priority: Positional Persistence (Phase 105: Next Item logic)
        # If the doc moved out of filter, select the one now at the same row
        if not restored and current_row_index >= 0 and docs:
             target_index = min(current_row_index, self.tree.topLevelItemCount() - 1)
             if target_index >= 0:
                 self.selectRow(target_index)
                 restored = True

        # 4. Fallback: First Document (Prevent Gray Canvas)
        if not restored and force_select_first and docs:
             self.selectRow(0)
             restored = True

        self.tree.blockSignals(False)

        # 5. Handle Programmatic Target Selection (Drill-Down Phase 115)
        if hasattr(self, "target_select_query") and self.target_select_query:
            try:
                select_docs = self.db_manager.search_documents_advanced(self.target_select_query)
                select_uuids = [d.uuid for d in select_docs]
                if select_uuids:
                    # Ensure all documents are loaded into the tree for selection to work
                    # (Infinite scroll would otherwise hide these items)
                    while self._loaded_count < len(self._all_docs):
                        self._load_next_chunk()

                    self.select_rows_by_uuids(select_uuids)
                    restored = True
            except Exception as e:
                logger.info(f"[ERROR] Drill-down selection failed: {e}")
            self.target_select_query = None # Clear after use

        # 6. Emit selection signal manually to ensure UI sync
        self._on_selection_changed()

        self.document_count_changed.emit(len(docs), len(docs))
        self.update_breadcrumb()
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
                 old_doc.last_used == doc.last_used and
                 old_doc.deleted_at == doc.deleted_at and
                 old_doc.locked_at == doc.locked_at and
                 old_doc.type_tags == doc.type_tags and
                 old_doc.original_filename == doc.original_filename and
                 old_doc.semantic_data == doc.semantic_data):
                  return # Change is irrelevant for view

             logger.info(f"[DEBUG] update_document_item: Updating row for {doc.uuid} ({old_doc.status} -> {doc.status})")

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
        locked_str = "Yes" if getattr(doc, "is_immutable", False) else "No"
        processed_str = format_datetime(doc.last_processed_at) or "-"
        used_str = format_datetime(doc.last_used) or "-"

        # 4. Apply to Fixed Columns
        target_item.setText(2, filename)
        target_item.setText(3, pages_str)
        target_item.setText(4, format_datetime(doc.created_at) or "-")
        target_item.setText(5, format_datetime(doc.last_used) or "-")
        target_item.setText(6, format_datetime(doc.deleted_at) or "-")
        target_item.setText(7, format_datetime(doc.locked_at) or "-")
        target_item.setText(8, format_datetime(doc.last_processed_at) or "-")
        target_item.setText(9, format_datetime(doc.exported_at) or "-")
        target_item.setText(10, doc.status or "NEW")
        formatted_types = [self.format_tag(t) for t in self.sort_type_tags(type_tags)]
        target_item.setText(11, ", ".join(formatted_types))
        target_item.setText(12, ", ".join(doc.tags or []))

        # 5. Dynamic Columns (including semantic shortcuts)
        num_fixed = len(self.fixed_columns)
        for d_idx, key in enumerate(self.dynamic_columns):
            col_idx = num_fixed + d_idx
            
            # Use getattr for properties/fields
            val = getattr(doc, key, None)
            
            # Fallback to semantic_data model_extra if not found as attribute
            if val is None and doc.semantic_data:
                # Check for direct attribute on semantic_data
                val = getattr(doc.semantic_data, key, None)
                if val is None and hasattr(doc.semantic_data, "model_extra") and doc.semantic_data.model_extra:
                    val = doc.semantic_data.model_extra.get(key)

            # Special Formatting for Common Fields
            if key in ["total_amount", "total_gross", "total_net"] and val is not None:
                try:
                    locale = QLocale.system()
                    txt = locale.toCurrencyString(float(val))
                    target_item.setData(col_idx, Qt.ItemDataRole.UserRole, float(val))
                except:
                    txt = str(val)
            elif key == "doc_date" and val:
                txt = str(val)
                target_item.setData(col_idx, Qt.ItemDataRole.UserRole, txt)
            elif val is None:
                txt = "-"
            elif isinstance(val, (list, dict)):
                txt = json.dumps(val)
                target_item.setData(col_idx, Qt.ItemDataRole.UserRole, txt)
            else:
                txt = str(val)
                target_item.setData(col_idx, Qt.ItemDataRole.UserRole, txt)

            target_item.setText(col_idx, txt)

    def apply_filter(self, criteria: dict):
        """
        Filter items based on criteria.
        """
        self.current_filter = criteria
        self.current_filter_text = criteria.get('text_search')
        self.update_breadcrumb()

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
                date_val = doc.doc_date or ""

                if not date_val:
                    if date_from or date_to: show = False
                else:
                    if date_from and date_val < date_from:
                        show = False
                    if date_to and date_val > date_to:
                        show = False


            if show and target_type:
                type_tags = getattr(doc, "type_tags", []) or []
                combined = type_tags
                if target_type.lower() not in [t.lower() for t in combined]:
                    show = False

            if show and target_tags:
                doc_tags = getattr(doc, "tags", []) or []
                if isinstance(doc_tags, str):
                    doc_tags = [t.strip() for t in doc_tags.split(",") if t.strip()]

                # Search in User Tags
                found = False
                for t in doc_tags:
                    if target_tags.lower() in t.lower():
                        found = True
                        break
                if not found:
                    show = False

            if show and text_search and doc:
                query = text_search.lower()
                haystack = [
                    str(doc.sender_name or ""),
                    str(doc.doc_date or ""),
                    str(doc.total_amount or ""),
                    str(doc.type_tags or ""),
                    str(doc.tags or ""),
                    str(doc.original_filename or ""),
                    str(doc.text_content or ""),
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
            self.tree.setCurrentItem(item)
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

    def get_all_uuids_in_view(self) -> list[str]:
        """Return list of all UUIDs currently displayed in the list/tree."""
        uuids = []
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            uid = iterator.value().data(1, Qt.ItemDataRole.UserRole)
            if uid:
                uuids.append(uid)
            iterator += 1
        return uuids

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

    def apply_advanced_filter(self, query: dict, label: Optional[str] = None):
        """Apply advanced search query."""
        logger.info(f"[DEBUG] DocumentList Received Query: {query}")

        # Check if query implies Trash Mode
        is_trash = False
        # ... (rest of check_trash logic)
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
        logger.info(f"[DEBUG] check_trash result: {is_mode_trash} for query: {query}")

        if is_mode_trash:
            self.current_advanced_query = None
            self.show_trash_bin(True, refresh=False)
            self.view_context = "Trash Bin"
        else:
            self.current_advanced_query = query # Persist
            self.show_trash_bin(False, refresh=False) # Ensure we leave trash mode
            self.current_filter_text = None # Clear simple text search

            # Smart Labeling for Breadcrumb
            if label:
                 self.view_context = label
            elif query and "field" in query and query["field"] == "uuid" and query["op"] == "in":
                 self.view_context = "Manual Selection" # Usually from Cockpit or Maintenance
            else:
                 self.view_context = "Advanced Filter"

        self.update_breadcrumb()
        # Phase 105: Handled inside refresh_list logic
        self.refresh_list(force_select_first=True)
        self.tree.setFocus()

    def set_advanced_filter_active(self, active: bool):
        """Toggle between Rule Editor and Cockpit Filter precedence."""
        self.advanced_filter_active = active
        self.refresh_list(force_select_first=True)
        self.tree.setFocus()

    def _check_scroll_bottom(self, value):
        """Infinite Scroll Trigger: Loads more data if user reaches 90% of current view."""
        vbar = self.tree.verticalScrollBar()
        if vbar.maximum() > 0 and value > vbar.maximum() * 0.9:
            self._load_next_chunk()

    def _load_next_chunk(self, reset=False):
        """Paging engine for QTreeWidget items."""
        if reset:
            self.tree.setSortingEnabled(False)
            self.tree.clear()
            self._loaded_count = 0
            self.tree.verticalScrollBar().setValue(0)
        
        if self._loaded_count >= len(self._all_docs):
            return

        # Disable sorting temporarily to speed up bulk insertion
        was_sorting = self.tree.isSortingEnabled()
        self.tree.setSortingEnabled(False)

        end = min(self._loaded_count + self.CHUNK_SIZE, len(self._all_docs))
        chunk = self._all_docs[self._loaded_count:end]
        
        for doc in chunk:
            item = self._create_tree_item(doc)
            self.tree.addTopLevelItem(item)
            
        self._loaded_count = end
        
        # Restore sorting if it was active
        if was_sorting:
            self.tree.setSortingEnabled(True)

    def _create_tree_item(self, doc) -> SortableTreeWidgetItem:
        """Centralized factory for document list items."""
        created_str = format_datetime(doc.created_at)
        created_sort = str(doc.created_at) if doc.created_at else ""

        filename = doc.original_filename or f"Entity {doc.uuid[:8]}"
        pages_sort = doc.page_count if doc.page_count is not None else 0
        pages_str = str(pages_sort)
        status_raw = getattr(doc, "status", "NEW").upper()
        status = self.status_labels.get(status_raw, status_raw)
        type_tags = getattr(doc, "type_tags", []) or []
        combined_types = self.sort_type_tags(set(type_tags))
        
        import_str = format_datetime(doc.created_at) or "-"
        used_str = format_datetime(doc.last_used) or "-"
        deleted_str = format_datetime(doc.deleted_at) or "-"
        locked_at_str = format_datetime(doc.locked_at) or "-"
        processed_str = format_datetime(doc.last_processed_at) or "-"
        exported_str = format_datetime(doc.exported_at) or "-"
        
        sd = doc.semantic_data
        
        hit_count = self.current_hit_map.get(doc.uuid, 0)
        
        icon = ""
        p_class = getattr(doc, "pdf_class", "C")
        if p_class in ["A", "AB"]:
            icon = "🛡️ "
        elif p_class == "B":
            icon = "⚙️ "
        elif p_class == "H":
            icon = "📦 "
            
        filename_display = f"{icon}{filename}"
        if hit_count > 0:
            filename_display = f"({hit_count}) {filename_display}"

        col_data = [
            "",                 # 0: #
            doc.uuid,           # 1: Entity ID
            filename_display,   # 2: Filename
            pages_str,          # 3: Pages
            import_str,         # 4: Imported Date
            used_str,           # 5: Used Date
            deleted_str,        # 6: Deleted Date
            locked_at_str,      # 7: Locked Date
            processed_str,      # 8: Autoprocessed Date
            exported_str,       # 9: Exported Date
            status,             # 10: Status
            ", ".join(self.format_tag(t) for t in combined_types if t), # 11: Type Tags
            ", ".join(str(t) for t in (doc.tags or []) if t), # 12: Tags
        ]

        # Dynamic Columns
        num_fixed = len(self.fixed_columns)
        for key in self.dynamic_columns:
            val = getattr(doc, key, None)
            if val is None and doc.semantic_data:
                val = getattr(doc.semantic_data, key, None)
                if val is None and hasattr(doc.semantic_data, "model_extra") and doc.semantic_data.model_extra:
                    val = doc.semantic_data.model_extra.get(key)
            
            if key in ["total_amount", "total_gross", "total_net"] and val is not None:
                try:
                    locale = QLocale.system()
                    txt = locale.toCurrencyString(float(val))
                except:
                    txt = str(val)
            elif val is None:
                txt = "-"
            elif isinstance(val, (list, dict)):
                txt = json.dumps(val)
            else:
                txt = str(val)
            col_data.append(txt)

        item = SortableTreeWidgetItem(col_data)
        item.setData(1, Qt.ItemDataRole.UserRole, doc.uuid)
        item.setData(3, Qt.ItemDataRole.UserRole, pages_sort)
        item.setData(4, Qt.ItemDataRole.UserRole, str(doc.created_at or ""))
        item.setData(5, Qt.ItemDataRole.UserRole, str(doc.last_used or ""))
        item.setData(6, Qt.ItemDataRole.UserRole, str(doc.deleted_at or ""))
        item.setData(7, Qt.ItemDataRole.UserRole, str(doc.locked_at or ""))
        item.setData(8, Qt.ItemDataRole.UserRole, str(doc.last_processed_at or ""))
        item.setData(9, Qt.ItemDataRole.UserRole, str(doc.exported_at or ""))
        item.setData(10, Qt.ItemDataRole.UserRole, doc.status)
        item.setData(2, Qt.ItemDataRole.UserRole, p_class)

        if p_class != "C":
            tips = {
                "A": self.tr("Digital Original (Signed)"),
                "B": self.tr("Digital Original (ZUGFeRD/Factur-X)"),
                "AB": self.tr("Digital Original (Signed & ZUGFeRD)"),
                "H": self.tr("Hybrid Container (KPaperFlux Protected)")
            }
            item.setToolTip(2, tips.get(p_class, ""))

        if combined_types:
            item.setToolTip(11, "\n".join(self.format_tag(t) for t in combined_types if t))

        if doc.tags:
            tag_str = ", ".join(str(t) for t in doc.tags if t)
            item.setData(12, Qt.ItemDataRole.UserRole, tag_str)
            item.setToolTip(12, "\n".join(str(t) for t in doc.tags if t))

        for d_idx, key in enumerate(self.dynamic_columns):
            col_idx = num_fixed + d_idx
            val = getattr(doc, key, None)
            if val is None and doc.semantic_data:
                val = getattr(doc.semantic_data, key, None)
                if val is None and hasattr(doc.semantic_data, "model_extra") and doc.semantic_data.model_extra:
                    val = doc.semantic_data.model_extra.get(key)
            if val is not None:
                item.setData(col_idx, Qt.ItemDataRole.UserRole, val)

        if getattr(doc, "is_immutable", False):
            brush = QBrush(Qt.GlobalColor.gray)
            for i in range(len(col_data)):
                item.setForeground(i, brush)
        
        return item

    def populate_tree(self, docs):
        """Populate the tree using lazy incremental loading."""
        # 0. Temporarily disable sorting for bulk insertion performance
        self.tree.setSortingEnabled(False)
        self._all_docs = docs
        self.documents_cache = {doc.uuid: doc for doc in docs}
        
        # Stability: Capture current scroll bar state if we are refreshing
        v_bar = self.tree.verticalScrollBar()
        scroll_val = v_bar.value()

        # Phase 113: Load first chunk and reset state
        self._load_next_chunk(reset=True)

        # 1. Restore Sort State or apply defaults
        header = self.tree.header()
        if header.sortIndicatorSection() < 0:
             # Default: Sort by Created Date (4) or Deleted Date (6) Descending
             sort_col = 6 if self.is_trash_mode else 4
             header.setSortIndicator(sort_col, Qt.SortOrder.DescendingOrder)
        
        # 2. Trigger the sort operation
        self.tree.sortByColumn(header.sortIndicatorSection(), header.sortIndicatorOrder())

        # 3. CRITICAL: Re-enable sorting so user interaction works
        self.tree.setSortingEnabled(True)

        # 4. Final UI polish
        if scroll_val > 0:
            v_bar.setValue(scroll_val)

        # Ensure header remains clickable/movable
        header.setSectionsClickable(True)
        header.setSectionsMovable(True)

        # v28.2 REMOVED: self.document_count_changed.emit(...)
        # Callers (refresh_list, apply_advanced_filter) must emit manually
        # to ensure selection restoration is complete.
    def open_export_dialog(self, documents: list):
        if not documents:
            show_selectable_message_box(self, self.tr("Export"), self.tr("No documents to export."), icon=QMessageBox.Icon.Warning)
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
        if dlg.exec():
            # Phase 106: Mark documents as exported
            if self.db_manager:
                now = datetime.datetime.now().isoformat()
                for doc in documents:
                    self.db_manager.update_document_metadata(doc.uuid, {"exported_at": now})
                # Refresh list to show new exported dates
                self.refresh_list()

    def update_breadcrumb(self):
        """Update breadcrumb label based on current state."""
        base = self.tr("Documents")
        path = [base]

        if self.is_trash_mode:
            path.append(self.tr("Trash Bin"))
        elif self.view_context:
            if self.view_context != "All Documents":
                path.append(self.tr(self.view_context))

        # Add Search context if present
        if getattr(self, "current_filter_text", None):
             path.append(f"{self.tr('Search')}: '{self.current_filter_text}'")

        self.lbl_breadcrumb.setText(" > ".join(path))

        # Color Coding for better orientation
        color = "#555" # Default Gray
        if self.is_trash_mode:
            color = "#d32f2f" # Red
        elif "Semantic" in self.view_context or "Missing" in self.view_context:
            color = "#f57c00" # Orange
        elif len(path) > 1:
            color = "#1976d2" # Blue (Search/Filter)

        self.lbl_breadcrumb.setStyleSheet(f"font-weight: bold; color: {color};")

        # Show/Hide Reset Button
        is_active = len(path) > 1 or getattr(self, "current_filter_text", None)
        self.btn_reset_view.setVisible(bool(is_active))

    def clear_filters(self):
        """Reset all filters and view context."""
        self.current_advanced_query = None
        self.current_cockpit_query = None
        self.current_filter_text = ""
        self.view_context = "All Documents"
        self.show_trash_bin(False, refresh=True)
        self.update_breadcrumb()

    def set_view_context(self, label: str):
        """Explicitly set a context label for the breadcrumb."""
        self.view_context = label
        self.update_breadcrumb()

    def sort_type_tags(self, tags):
        """Sorts tags: DocTypes first, then CTX_ context, then direction (INBOUND, etc)."""
        if not isinstance(tags, (list, tuple, set)):
             return tags

        def tag_priority(tag):
            if not tag: return 99
            t = str(tag).upper()
            if t in ("INBOUND", "OUTBOUND", "INTERNAL"): return 3
            if t.startswith("CTX_"): return 2
            return 1 # DocTypes

        return sorted(list(tags), key=lambda x: (tag_priority(x), str(x).upper()))

    def format_tag(self, tag: str) -> str:
        """Translates technical tags into pretty UI labels."""
        if not tag: return ""
        t_str = str(tag).replace("_", " ")
        t_upper = t_str.upper()
        
        # 1. Check explicit mapping (using underscored keys from TAG_MAPPING)
        orig_upper = str(tag).upper()
        if orig_upper in self.TAG_MAPPING:
            return self.tr(self.TAG_MAPPING[orig_upper])
            
        # 2. Heuristic for DocTypes (ORDER_CONFIRMATION -> Order Confirmation)
        return self.tr(t_str.title())

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
