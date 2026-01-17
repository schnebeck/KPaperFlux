from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QComboBox, QLineEdit, QScrollArea, QFrame, 
                             QDateEdit, QDoubleSpinBox, QMessageBox, QInputDialog, QMenu, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QSettings
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QSettings
from PyQt6.QtGui import QAction
import json
from gui.filter_manager import FilterManagerDialog
from core.filter_tree import NodeType

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
        "UUID": "uuid"
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
        ("In List", "in")
    ]

    def __init__(self, parent=None, extra_keys=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Field Selector
        self.combo_field = QComboBox()
        self.combo_field.addItems(self.FIELDS.keys())
        
        if extra_keys:
            for key in extra_keys:
                self.combo_field.addItem(f"JSON: {key}", f"json:{key}")
                
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
        self.input_container = QWidget()
        self.input_layout = QVBoxLayout(self.input_container)
        self.input_layout.setContentsMargins(0, 0, 0, 0)
        
        self.current_input = QLineEdit()
        self.current_input.textChanged.connect(self.changed)
        self.input_layout.addWidget(self.current_input)
        
        # Remove Button
        self.btn_remove = QPushButton("X")
        self.btn_remove.setFixedWidth(24)
        self.btn_remove.clicked.connect(self.remove_requested)
        
        self.layout.addWidget(self.combo_field, 1)
        self.layout.addWidget(self.chk_negate)
        self.layout.addWidget(self.combo_op, 1)
        self.layout.addWidget(self.input_container, 2)
        self.layout.addWidget(self.btn_remove)
        
    def _on_field_changed(self, text):
        field_key = self.FIELDS.get(text)
        # TODO: Switch input widget type based on field (Date -> DateEdit, Amount -> SpinBox)
        # For prototype, keep Text/LineEdit, but maybe hint?
        # If user selects "Date", we could swap self.current_input
        self.changed.emit()

    def get_condition(self):
        # Handle standard vs dynamic fields
        if self.combo_field.currentData():
            # It's a JSON field with data set
            field_key = self.combo_field.currentData()
        else:
            # Standard field name -> lookup
            field_name = self.combo_field.currentText()
            field_key = self.FIELDS.get(field_name, field_name.lower())
        
        op = self.combo_op.currentData()
        
        if op in ["is_empty", "is_not_empty"]:
            val = None
        else:
            if hasattr(self.current_input, "text"):
                val = self.current_input.text()
            elif hasattr(self.current_input, "date"):
                val = self.current_input.date().toString(Qt.DateFormat.ISODate)
            elif hasattr(self.current_input, "value"):
                val = self.current_input.value()
            else:
                val = ""
        
        # If operator is 'in', we expect val to be a list or comma-separated string
        if op == "in" and isinstance(val, str):
            # Parse CSV to list for 'in' operator if manually entered
            # Or if it was loaded as list, it should be fine? 
            # But here we read from text input.
            # Simple assumption: Comma separated UUIDs/Strings
             val = [x.strip() for x in val.split(",") if x.strip()]
             
        return {"field": field_key, "op": op, "value": val, "negate": self.chk_negate.isChecked()}

    def set_condition(self, mode: dict):
        key = mode.get("field")
        
        self.chk_negate.setChecked(mode.get("negate", False))
        
        if key.startswith("json:"):
             # Dynamic field
             # Check if item exists, if not add it (persistence might have old keys)
             found = False
             for i in range(self.combo_field.count()):
                 if self.combo_field.itemData(i) == key:
                     self.combo_field.setCurrentIndex(i)
                     found = True
                     break
             if not found:
                 # Add ad-hoc
                 display = f"JSON: {key[5:]}"
                 self.combo_field.addItem(display, key)
                 self.combo_field.setCurrentIndex(self.combo_field.count() - 1)
        else:
            # Standard
            key_to_name = {v: k for k, v in self.FIELDS.items()}
            name = key_to_name.get(key, key)
            self.combo_field.setCurrentText(name)
        
        idx = self.combo_op.findData(mode.get("op"))
        if idx >= 0:
            self.combo_op.setCurrentIndex(idx)
            
        val = mode.get("value")
        if val is not None and hasattr(self.current_input, "setText"):
             if isinstance(val, list):
                 val = ", ".join(map(str, val))
             self.current_input.setText(str(val))


class AdvancedFilterWidget(QWidget):
    """
    Widget to build complex query objects.
    """
    filter_changed = pyqtSignal(dict) # Emits Query Object
    
    
    def __init__(self, parent=None, db_manager=None, filter_tree=None, save_callback=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.filter_tree = filter_tree
        self.save_callback = save_callback
        self.extra_keys = []
        self.loaded_filter_node = None # Track currently loaded filter
        self._loading = False # Flag to suppress dirty check during load
        if self.db_manager:
             self.extra_keys = self.db_manager.get_available_extra_keys()
             
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
        logic_layout = QHBoxLayout()
        logic_layout.addWidget(QLabel(self.tr("Match:")))
        self.combo_logic = QComboBox()
        self.combo_logic.addItems(["ALL (AND)", "ANY (OR)"])
        self.combo_logic.currentIndexChanged.connect(self._emit_change)
        logic_layout.addWidget(self.combo_logic)
        logic_layout.addStretch()
        main_layout.addLayout(logic_layout)

        # --- Conditions List ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.conditions_container = QWidget()
        self.conditions_layout = QVBoxLayout(self.conditions_container)
        self.conditions_layout.addStretch() # Push items up
        self.scroll.setWidget(self.conditions_container)
        
        main_layout.addWidget(self.scroll, 1)
        
        # --- Bottom Bar ---
        bottom_bar = QHBoxLayout()
        
        self.btn_add = QPushButton(self.tr("Add Condition"))
        self.btn_add.clicked.connect(self.add_condition)
        bottom_bar.addWidget(self.btn_add)
        
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
        
        # Initial empty state
        self.rows = []

    def add_condition(self, data=None):
        row = FilterConditionWidget(self, extra_keys=self.extra_keys)
        if data:
            row.set_condition(data)
        
        # Insert before stretch (last item)
        count = self.conditions_layout.count()
        self.conditions_layout.insertWidget(count - 1, row)
        
        row.remove_requested.connect(lambda: self.remove_condition(row))
        row.changed.connect(self._set_dirty)
        
        self.rows.append(row)
        self._set_dirty()

    def remove_condition(self, row):
        if row in self.rows:
            self.rows.remove(row)
            self.conditions_layout.removeWidget(row)
            row.deleteLater()
            self._set_dirty()
            
    def clear_all(self, reset_combo=True):
        self._reset_dirty_indicator() # Reset * details before clearing
        
        if reset_combo and isinstance(reset_combo, bool): 
            # Check typing because clicked signal might pass 'checked' boolean if not careful
            self.combo_filters.setCurrentIndex(0) # Reset selection
        
        for row in list(self.rows):
            self.remove_condition(row)
        self._set_dirty() # Changed to dirty instead of auto-emit? 
        # Actually user wants Apply workflow. Clearing is a change.
        # But for "Load" logic, we might need to bypass dirty if we immediately apply?
        # See load_from_object.

    def _set_dirty(self):
        if getattr(self, '_loading', False):
            return
            
        if self.btn_apply:
            self.btn_apply.setEnabled(True)
            
        if self.btn_revert and self.loaded_filter_node:
             self.btn_revert.setEnabled(True)
        
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
        if not self.rows:
            return {}
            
        logic = "AND" if self.combo_logic.currentIndex() == 0 else "OR"
        conditions = [row.get_condition() for row in self.rows]
        
        return {
            "operator": logic,
            "conditions": conditions
        }

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
        
        # It's a FilterNode or saved dict (legacy)
        # We stored FilterNode object in addItem
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
        if node and node.data is not None:
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
                
            # Set Logic
            op = query.get("operator", "AND")
            self.combo_logic.setCurrentIndex(0 if op == "AND" else 1)
            
            self.chk_active.blockSignals(True)
            self.chk_active.setChecked(True)
            self.chk_active.blockSignals(False)
            
            for cond in query.get("conditions", []):
                if "conditions" in cond:
                    # Nested not supported in UI MVP
                    continue
                self.add_condition(cond)
        finally:
            self._loading = False

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

