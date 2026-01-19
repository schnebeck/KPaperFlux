from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QComboBox, QLineEdit, QScrollArea, QFrame, 
                             QDateEdit, QDoubleSpinBox, QMessageBox, QInputDialog, QMenu, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QSettings
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QSettings
from PyQt6.QtGui import QAction
import json
from gui.filter_manager import FilterManagerDialog
from core.filter_tree import NodeType, FilterNode
from core.metadata_normalizer import MetadataNormalizer
from core.semantic_translator import SemanticTranslator

from gui.widgets.multi_select_combo import MultiSelectComboBox
from gui.widgets.date_range_picker import DateRangePicker
from PyQt6.QtWidgets import QStackedWidget

class FilterConditionWidget(QWidget):
    """
    A single row representing a filter condition: [Field] [Operator] [Value] [Remove]
    """
    remove_requested = pyqtSignal()
    changed = pyqtSignal()

    FIELDS = {
        "Sender": "sender",
        "Date": "doc_date", 
        "Amount (Netto)": "amount",
        "Document Type": "doc_type",
        "Tags": "tags",
        "Filename": "original_filename",
        "Created At": "created_at",
        "Last Processed": "last_processed_at",
        
        "Recipient Name": "recipient_name",
        "Recipient Company": "recipient_company",
        "Recipient Street": "recipient_street",
        "Recipient City": "recipient_city",
        "Recipient Zip": "recipient_zip",
        "Recipient Country": "recipient_country",
        
        "Sender Name": "sender_name",
        "Sender Company": "sender_company",
        "Sender Street": "sender_street",
        "Sender City": "sender_city",
        "Sender Zip": "sender_zip",
        "Sender Country": "sender_country",
        
        "Gross (Brutto)": "gross_amount",
        "Tax %": "tax_rate",
        "Postage": "postage",
        "Packaging": "packaging",
        "Currency": "currency",
        
        "IBAN": "iban",
        "Phone": "phone",
        "Pages": "page_count",
        "Export Filename": "export_filename",
        "Text Content": "text_content",
        "UUID": "uuid",
        
        # Phase 80: Virtual Columns
        "Virtual Sender (AI)": "v_sender",
        "Virtual Date (AI)": "v_doc_date",
        "Virtual Amount (AI)": "v_amount"
    }
    
    # Operators per type hint (simplified)
    # Generic, Numeric, Text, Date
    OPERATORS = [
        ("Contains", "contains"),
        ("Equals", "equals"),
        ("Starts With", "starts_with"),
        ("Greater Than", "gt"),
        ("Less Than", "lt"),
        ("Is Empty", "is_empty"),
        ("Is Not Empty", "is_not_empty"),
        ("In List", "in"),
        ("Between", "between") # Added for ranges
    ]

    def __init__(self, parent=None, extra_keys=None, available_tags=None):
        super().__init__(parent)
        self.available_tags = available_tags or []
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.combo_field = QComboBox()
        self._populate_fields(extra_keys)
        self.combo_field.currentTextChanged.connect(self._on_field_changed)
        
        # Operator Selector
        self.combo_op = QComboBox()
        for name, key in self.OPERATORS:
            self.combo_op.addItem(name, key)
        self.combo_op.currentIndexChanged.connect(self.changed)

        # Negate Checkbox
        self.chk_negate = QCheckBox("Not")
        self.chk_negate.toggled.connect(self.changed)
            
        # Value Input (Stacked / Dynamic)
        self.input_stack = QStackedWidget()
        
        # 0: Text Input (Default)
        self.input_text = QLineEdit()
        self.input_text.textChanged.connect(self.changed)
        self.input_stack.addWidget(self.input_text)
        
        # 1: Multi Select (Tags / Enum)
        self.input_multi = MultiSelectComboBox()
        self.input_multi.selectionChanged.connect(lambda: self.changed.emit())
        self.input_stack.addWidget(self.input_multi)
        
        # 2: Date Picker
        self.input_date = DateRangePicker()
        self.input_date.rangeChanged.connect(lambda: self.changed.emit())
        self.input_stack.addWidget(self.input_date)
        
        # Remove Button
        self.btn_remove = QPushButton("X")
        self.btn_remove.setFixedWidth(24)
        self.btn_remove.clicked.connect(self.remove_requested)
        
        self.layout.addWidget(self.combo_field, 1)
        self.layout.addWidget(self.chk_negate)
        self.layout.addWidget(self.combo_op, 1)
        self.layout.addWidget(self.input_stack, 2)
        self.layout.addWidget(self.btn_remove)
        
    # ... _populate_fields ...

    def _on_field_changed(self, text):
        field_key = self.FIELDS.get(text)
        # Check dynamic
        if not field_key:
             idx = self.combo_field.currentIndex()
             field_key = self.combo_field.itemData(idx)
             
        # Logic to switch inputs
        if field_key == "doc_date" or field_key == "created_at":
            self.input_stack.setCurrentIndex(2) # Date
        elif field_key == "tags":
            self.input_stack.setCurrentIndex(1) # Multi
            # Populate Tags
            # Need to clear first? MultiSelect doesn't have clear?
            # It has model. We can recreate or clear model.
            self.input_multi.clear() # QComboBox clear
            self.input_multi.addItems(self.available_tags)
        elif field_key == "doc_type":
             self.input_stack.setCurrentIndex(1)
             self.input_multi.clear()
             # Standard types?
             self.input_multi.addItems(["invoice", "receipt", "contract", "other"])
        else:
            self.input_stack.setCurrentIndex(0) # Text
            
        self.changed.emit()
        
    def _populate_fields(self, extra_keys):
        self.combo_field.clear()
        translator = SemanticTranslator.instance()
        
        # 1. Standard Fields (Grouped conceptually)
        self.combo_field.addItem("--- " + self.tr("Standard") + " ---", None)
        # Disable the header item? Qt doesn't make it easy in basic combo, 
        # but we can check in logic.
        
        # Sort standard fields by display name for easier finding
        sorted_standard = sorted(self.FIELDS.keys())
        for name in sorted_standard:
            self.combo_field.addItem(name, self.FIELDS[name])
            
        # 2. Semantic Types (Hierarchical)
        config = MetadataNormalizer.get_config()
        if config and "types" in config:
            for type_name, type_def in config["types"].items():
                # Translated Type Name
                label_key = type_def.get("label_key", f"type_{type_name.lower()}")
                type_label = translator.translate(label_key)
                
                self.combo_field.addItem(f"--- {type_label} ---", None)
                
                for field in type_def.get("fields", []):
                    field_id = field["id"]
                    field_label_key = field.get("label_key", field_id)
                    field_label = translator.translate(field_label_key)
                    
                    # Determine Path Strategy
                    # valid path strategy is strictly required for filter to work 
                    # without complex normalization logic in SQL.
                    # We look for "json_path" strategy.
                    path = None
                    for strat in field.get("strategies", []):
                        if strat["type"] == "json_path":
                            path = strat["path"]
                            break
                    
                    if path:
                        # Construct key: semantic:path 
                        # e.g. semantic:summary.tax_amount
                        key = f"semantic:{path}"
                        display = f"{type_label} > {field_label}"
                        self.combo_field.addItem(display, key)

        # 3. Raw / Discovered Keys (Fallback)
        if extra_keys:
             self.combo_field.addItem("--- " + self.tr("Raw Data") + " ---", None)
             for key in extra_keys:
                 # Avoid duplicates if possible? 
                 # Use a simplified display
                 if key.startswith("semantic:"):
                      short = key[9:]
                      display = f"Raw: {short}"
                      value = key
                 elif key.startswith("json:"):
                      short = key[5:]
                      display = f"Raw: {short}"
                      value = key
                 else:
                      display = f"Raw: {key}"
                      value = f"json:{key}"
                 
                 # Check if this value is already added (by Type definition) to avoid clutter
                 # But raw keys might be slightly different paths or deep nested
                 # Simple check:
                 if self.combo_field.findData(value) == -1:
                     self.combo_field.addItem(display, value)

    def get_condition(self):
        # Handle standard vs dynamic fields
        if self.combo_field.currentData():
            field_key = self.combo_field.currentData()
        else:
            field_name = self.combo_field.currentText()
            field_key = self.FIELDS.get(field_name, field_name.lower())
        
        op = self.combo_op.currentData()
        
        # Get Value from active input
        idx = self.input_stack.currentIndex()
        val = None
        
        if op in ["is_empty", "is_not_empty"]:
            val = None
        elif idx == 0: # Text
            val = self.input_text.text()
            # If op is 'in' and text input, split by comma
            if op == "in" and val:
                 val = [x.strip() for x in val.split(",") if x.strip()]
        elif idx == 1: # Multi
            val = self.input_multi.getCheckedItems()
            # If single value expected? Logic handles lists usually.
        elif idx == 2: # Date
            val = self.input_date.get_value()
             
        return {"field": field_key, "op": op, "value": val, "negate": self.chk_negate.isChecked()}

    def set_condition(self, mode: dict):
        key = mode.get("field")
        if not key:
            return # Invalid condition data
        
        self.chk_negate.setChecked(mode.get("negate", False))
        
        # 1. Set Field (This triggers _on_field_changed -> sets up input stack)
        found = False
        if key.startswith("json:") or key.startswith("semantic:"):
             # Check if item exists
             for i in range(self.combo_field.count()):
                 if self.combo_field.itemData(i) == key:
                     self.combo_field.setCurrentIndex(i)
                     found = True
                     break
             if not found:
                 # Add ad-hoc
                 if key.startswith("semantic:"): display = f"AI: {key[9:]}"
                 elif key.startswith("json:"): display = f"JSON: {key[5:]}"
                 else: display = f"JSON: {key}"
                 self.combo_field.addItem(display, key)
                 self.combo_field.setCurrentIndex(self.combo_field.count() - 1)
        else:
             # Standard
             # Reverse lookup FIELDS
             text_key = None
             for k, v in self.FIELDS.items():
                 if v == key:
                     text_key = k
                     break
             
             if text_key:
                 self.combo_field.setCurrentText(text_key)
             else:
                 # Fallback: Check if data exists or add it (System Fields like 'deleted')
                 idx = self.combo_field.findData(key)
                 if idx >= 0:
                     self.combo_field.setCurrentIndex(idx)
                 else:
                     # Not found, add it so we can filter on it
                     display = f"System: {key}"
                     self.combo_field.addItem(display, key)
                     self.combo_field.setCurrentIndex(self.combo_field.count() - 1)
                 
        # 2. Set Operator
        op = mode.get("op", "contains")
        idx = self.combo_op.findData(op)
        if idx >= 0: self.combo_op.setCurrentIndex(idx)
        
        # 3. Set Value
        val = mode.get("value")
        current_idx = self.input_stack.currentIndex()
        
        if current_idx == 0:
             if isinstance(val, list): val = ", ".join(map(str, val))
             self.input_text.setText(str(val) if val is not None else "")
        elif current_idx == 1:
             if isinstance(val, list):
                 self.input_multi.setCheckedItems(val)
             elif isinstance(val, str):
                 self.input_multi.setCheckedItems([val])
        elif current_idx == 2:
             self.input_date.set_value(val)




from gui.widgets.filter_group import FilterGroupWidget

class AdvancedFilterWidget(QWidget):
    """
    Widget to build complex query objects.
    """
    filter_changed = pyqtSignal(dict) # Emits Query Object
    trash_mode_changed = pyqtSignal(bool) # New signal for Trash Mode
    
    def __init__(self, parent=None, db_manager=None, filter_tree=None, save_callback=None):
        super().__init__(parent)
        # ... validation ...
        self.db_manager = db_manager
        self.filter_tree = filter_tree
        self.save_callback = save_callback
        self.extra_keys = []
        self.available_tags = []
        self.loaded_filter_node = None
        self._loading = False
        
        if self.db_manager:
            self.extra_keys = self.db_manager.get_available_extra_keys()
            if hasattr(self.db_manager, "get_available_tags"):
                self.available_tags = self.db_manager.get_available_tags()

        self._init_ui()
        self.load_known_filters()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # --- Top Bar (Management) ---
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel(self.tr("Saved Filters:")))
        
        self.combo_filters = QComboBox()
        self.combo_filters.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.combo_filters.customContextMenuRequested.connect(self._show_combo_context)
        self.combo_filters.addItem(self.tr("- Select -"), None)
        self.combo_filters.currentIndexChanged.connect(self._on_saved_filter_selected)
        top_bar.addWidget(self.combo_filters, 1)
        
        self.btn_revert = QPushButton(self.tr("Revert"))
        self.btn_revert.setEnabled(False)
        self.btn_revert.clicked.connect(self.revert_changes)
        top_bar.addWidget(self.btn_revert)
        
        self.btn_save = QPushButton(self.tr("Save..."))
        self.btn_save.clicked.connect(self.save_current_filter)
        top_bar.addWidget(self.btn_save)
        
        self.btn_manage = QPushButton(self.tr("Manage"))
        self.btn_manage.clicked.connect(self.manage_filters)
        top_bar.addWidget(self.btn_manage)
        
        main_layout.addLayout(top_bar)
        
        # --- Logic Switch ---
        # REMOVED: Nested Logic handles this per group.
        # But we might want a legacy "Match: " label? 
        # No, the root group has its own logic combo.
        
        # --- Conditions Area ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        # Root Group
        self.root_group = FilterGroupWidget(extra_keys=self.extra_keys, 
                                            available_tags=self.available_tags, 
                                            is_root=True)
        self.root_group.changed.connect(self._set_dirty)
        self.scroll.setWidget(self.root_group)
        
        main_layout.addWidget(self.scroll, 1)
        
        # --- Bottom Bar ---
        bottom_bar = QHBoxLayout()
        
        # Buttons are now inside the group headers (add condition/group).
        # We only need Global actions here.
        
        self.btn_clear = QPushButton(self.tr("Clear All"))
        self.btn_clear.clicked.connect(lambda: self.clear_all(reset_combo=True))
        bottom_bar.addWidget(self.btn_clear)
        
        bottom_bar.addStretch()
        
        self.btn_apply = QPushButton(self.tr("Apply Changes"))
        self.btn_apply.setEnabled(False) # Initially clean
        self.btn_apply.clicked.connect(self._emit_change)
        bottom_bar.addWidget(self.btn_apply)
        
        self.chk_active = QCheckBox(self.tr("Filter Active"))
        self.chk_active.setChecked(True)
        self.chk_active.toggled.connect(self._on_active_toggled)
        bottom_bar.addWidget(self.chk_active)
        
        main_layout.addLayout(bottom_bar)

    def add_condition(self, data=None):
        # Delegate to root group
        self.root_group.add_condition(data)

    def remove_condition(self, row):
        # Handled internally by groups
        pass

    def clear_all(self, reset_combo=True):
        self._reset_dirty_indicator()
        if reset_combo and isinstance(reset_combo, bool): 
            self.combo_filters.setCurrentIndex(0)
            
        self.root_group.clear()
        self._set_dirty()
        # Auto-apply to update view immediately (UX feedback)
        self._emit_change()
        
    def get_query(self):
        # Delegate
        return self.root_group.get_query()
        
    def load_from_node(self, node: FilterNode):
        self._loading = True
        self.loaded_filter_node = node
        
        # Clear UI
        self.root_group.clear()
        
        # Load Data
        data = node.data
        if data:
            self.root_group.set_query(data)
            
        self._loading = False
        self._reset_dirty_indicator()
        self.btn_apply.setEnabled(False)
        self.btn_revert.setEnabled(False)
        self.chk_active.setChecked(True) # Assume active upon load
        
        # Auto-Apply on Load? Usually yes for saved filters.
        self._emit_change()
            

    def _set_dirty(self):
        if getattr(self, '_loading', False):
            return
            
        if self.btn_apply:
            self.btn_apply.setEnabled(True)
            
        if self.btn_revert and self.loaded_filter_node:
             self.btn_revert.setEnabled(True)
        
        # Ignore Trash Node
        if self.loaded_filter_node and hasattr(self.loaded_filter_node, "node_type") and self.loaded_filter_node.node_type == NodeType.TRASH:
            return

        if self.loaded_filter_node:
            idx = self.combo_filters.findData(self.loaded_filter_node)
            if idx >= 0:
                current_text = self.combo_filters.itemText(idx)
                if not current_text.endswith(" *"):
                     self.combo_filters.setItemText(idx, current_text + " *")

    def _reset_dirty_indicator(self):
        """Removes the * from the currently loaded filter in the combo."""
        if self.btn_revert:
            self.btn_revert.setEnabled(False)
            
        if self.loaded_filter_node:
            idx = self.combo_filters.findData(self.loaded_filter_node)
            if idx >= 0:
                current_text = self.combo_filters.itemText(idx)
                if current_text.endswith(" *"):
                     self.combo_filters.setItemText(idx, current_text[:-2])

    def _on_active_toggled(self, checked):
        # Toggling active state applied immediately
        self._emit_change()

    def _emit_change(self):
        query = self.get_query_object()
        
        if self.btn_apply:
            self.btn_apply.setEnabled(False) # Clean state
        
        if not self.chk_active.isChecked():
            # If disabled, emit empty query (all docs)
            # But we keep the query object internally in UI
            self.filter_changed.emit({})
            return

        print(f"[DEBUG] AdvancedFilter Emitting: {json.dumps(query, default=str)}")
        self.filter_changed.emit(query)

    def get_query_object(self):
        # Delegate to root group
        if self.root_group:
            return self.root_group.get_query()
        return {}

    # --- Persistence ---
    def load_known_filters(self):
        self.combo_filters.blockSignals(True)
        self.combo_filters.clear()
        self.combo_filters.addItem(self.tr("- Select -"), None)
        
        if self.filter_tree:
            # Add Favorites (by UUID -> lookup)
            # For MVP, populate from all known filters or just favorites?
            # Let's populate from Root Children that are Filters for now? 
            # Or traverse favorites.
            # Tree API has 'favorites' list of IDs.
            # But we don't have easy ID lookup in Tree.
            # Recursively add all filters to combo logic
            def add_nodes(node, path_prefix=""):
                for child in node.children:
                     if child.node_type == NodeType.FILTER:
                         display = f"{path_prefix}{child.name}" if path_prefix else child.name
                         self.combo_filters.addItem(display, child)
                     elif child.node_type == NodeType.TRASH:
                         # Always show Trash at top level or appropriate usage
                         display = f"[ {child.name} ]"
                         self.combo_filters.addItem(display, child)
                     elif child.node_type == NodeType.FOLDER:
                         new_prefix = f"{path_prefix}{child.name} / " if path_prefix else f"{child.name} / "
                         add_nodes(child, new_prefix)

            add_nodes(self.filter_tree.root)
            
            # Separator
            self.combo_filters.insertSeparator(self.combo_filters.count())
            self.combo_filters.addItem(self.tr("Browse All..."), "BROWSE_ALL")
            
        self.combo_filters.blockSignals(False)


    def _on_saved_filter_selected(self, index):
        data = self.combo_filters.currentData()
        data = self.combo_filters.currentData()
        if not data:
            self.loaded_filter_node = None
            return
            
        if data == "BROWSE_ALL":
            self.combo_filters.blockSignals(True)
            self.combo_filters.setCurrentIndex(0)
            self.combo_filters.blockSignals(False)
            self.open_filter_manager()
            return
        
        # Check if it is a FilterNode Object (which has node_type)
        if hasattr(data, "node_type") and data.node_type == NodeType.TRASH:
             self.loaded_filter_node = data
             # Standardize Trash as a normal filter Query
             # This ensures verify logic in DocumentList.apply_advanced_filter works.
             # Must be a Group structure since set_query expects 'conditions' list.
             trash_query = {
                 "operator": "AND",
                 "conditions": [
                     {"field": "deleted", "op": "equals", "value": True}
                 ]
             }
             self.load_from_object(trash_query)
             self._emit_change()
             return
             
        # It's a FilterNode or saved dict (legacy)
        # We stored FilterNode object in addItem
        
        # Ensure we exit trash mode
        self.trash_mode_changed.emit(False)
        
        if hasattr(data, "data"):
             self.load_from_object(data.data)
             self.loaded_filter_node = data # Set loaded reference
             self._emit_change()

    def open_filter_manager(self):
        if not self.filter_tree:
             return
        dlg = FilterManagerDialog(self.filter_tree, db_manager=self.db_manager, parent=self)
        dlg.filter_selected.connect(self._on_manager_selected)
        dlg.exec()
        
        # Reload combo in case favorites changed or items renamed
        self.load_known_filters()
        
        # Trigger Save
        if self.save_callback:
            self.save_callback()

        # Restore selection if a filter is loaded (it might be cleared by load_known_filters)
        if self.loaded_filter_node:
             self._sync_combo_selection(self.loaded_filter_node)

    def _on_manager_selected(self, node):
        if not node: return
        
        if node.node_type == NodeType.TRASH:
            # Special Trash Handling
            self.loaded_filter_node = node
            self.trash_mode_changed.emit(True)
            self._sync_combo_selection(node)
            return
        
        # Normal Filter
        self.trash_mode_changed.emit(False) # Exit trash mode
        
        if node.data is not None:
            self.load_from_object(node.data)
            self.loaded_filter_node = node
            self._emit_change()
            
            self._sync_combo_selection(node)

    def _sync_combo_selection(self, node):
            # Sync Combo
            idx = self.combo_filters.findData(node)
            if idx >= 0:
                self.combo_filters.setCurrentIndex(idx)
            else:
                display_name = f"{node.name} (Folder: {node.parent.name if node.parent else 'Root'})"
                self.combo_filters.insertItem(1, display_name, node)
                self.combo_filters.setCurrentIndex(1)

    def revert_changes(self):
        if self.loaded_filter_node and self.loaded_filter_node.data:
            self.load_from_object(self.loaded_filter_node.data)
            self._emit_change() # Emit clean state
            # _reset_dirty_indicator is called inside load_from_object
            if self.btn_apply:
                self.btn_apply.setEnabled(False) # Clean

    def load_from_object(self, query):
        self._reset_dirty_indicator() # Clear previous *
        
        self._loading = True
        try:
            self.clear_all(reset_combo=False)
            if not query:
                return
                
            self.chk_active.blockSignals(True)
            self.chk_active.setChecked(True)
            self.chk_active.blockSignals(False)
            
            # Use root_group to load nested query
            self.root_group.set_query(query)
                
        finally:
            self._loading = False
            self.btn_apply.setEnabled(False) # Loaded state is clean
            self.btn_revert.setEnabled(False)
            self._loading = False

    def apply_advanced_filter(self):
        """Public method to force application of current filter."""
        self._emit_change()

    def save_current_filter(self):
        if not self.rows:
             QMessageBox.warning(self, self.tr("Save Filter"), self.tr("No conditions to save."))
             return
             
        if not self.filter_tree:
            return

        name, ok = QInputDialog.getText(self, self.tr("Save Filter"), self.tr("Filter Name:"))
        if ok and name:
            query = self.get_query_object()
            
            # Save as Filter Node in Root (MVP)
            # TODO: Improve with Type selection/Folder selection
            self.filter_tree.add_filter(self.filter_tree.root, name, query)
            
            if self.save_callback:
                self.save_callback()
            
            self.load_known_filters() # Refresh
            
            # Select the new item
            idx = self.combo_filters.findText(name)
            if idx >= 0:
                 self.combo_filters.setCurrentIndex(idx)

    def manage_filters(self):
        self.open_filter_manager()

    def _show_combo_context(self, pos):
        # We need to determine which item is under mouse if dropdown open?
        # Or just the current item?
        # QComboBox context menu usually for current item or text field.
        # But users might want to right click expanded list.
        # QComboBox view right click?
        # The `customContextMenuRequested` on combo itself usually refers to the closed box area.
        # But if dropdown is open, the VIEW handles events.
        # Accessing view: self.combo_filters.view()
        
        # Simpler MVP: Right click on the collapsed box deletes the currently selected item.
        # Check current data
        data = self.combo_filters.currentData()
        idx = self.combo_filters.currentIndex()
        if idx <= 0 or data == "BROWSE_ALL":
             return

        # It's a filter node
        node_name = self.combo_filters.currentText()
        
        menu = QMenu(self)
        del_action = QAction(f"Delete '{node_name}'", self)
        del_action.triggered.connect(lambda: self._delete_node(data)) # data is the Node or dict
        menu.addAction(del_action)
        menu.exec(self.combo_filters.mapToGlobal(pos))

    def _delete_node(self, node):
        if not self.filter_tree:
            return
            
        # Check if node is real node
        if hasattr(node, "parent") and node.parent:
            confirm = QMessageBox.question(
                self, self.tr("Delete Filter"), 
                self.tr("Are you sure you want to delete '%s'?") % node.name, 
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                node.parent.remove_child(node)
                if self.save_callback:
                    self.save_callback()
                self.load_known_filters() # Refresh
                self.clear_all(reset_combo=True)

    def _persist(self):
        # Tree persistence managed by MainWindow for now
        pass

