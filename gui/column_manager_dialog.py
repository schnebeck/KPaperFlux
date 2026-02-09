from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, 
                             QPushButton, QLabel, QCheckBox, QComboBox, QDialogButtonBox, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

class ColumnManagerDialog(QDialog):
    def __init__(self, parent, fixed_columns: dict, dynamic_columns: list, available_keys: list, header):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Configure Columns"))
        self.resize(500, 600)
        
        self.fixed_columns = fixed_columns  # {idx: label}
        self.dynamic_columns = list(dynamic_columns) # Copy
        self.available_keys = sorted([k for k in available_keys if k not in self.dynamic_columns])
        self.header = header
        
        self.pretty_labels = {
            "doc_date": self.tr("Date"),
            "sender_name": self.tr("Sender"),
            "total_amount": self.tr("Amount"),
            "total_gross": self.tr("Gross Amount"),
            "total_net": self.tr("Net Amount"),
            "invoice_number": self.tr("Invoice #")
        }
        
        self.init_ui()
        self.load_columns()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Info
        layout.addWidget(QLabel(self.tr("Drag and drop to reorder. Uncheck to hide. Double-click or use button to remove dynamic columns.")))
        
        # List Widget
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.itemDoubleClicked.connect(self.remove_selected_column)
        self.list_widget.itemSelectionChanged.connect(self._update_button_states)
        layout.addWidget(self.list_widget)
        
        # Add Dynamic Column Section
        add_layout = QHBoxLayout()
        self.combo_add = QComboBox()
        self.combo_add.addItems(self.available_keys)
        add_layout.addWidget(self.combo_add)
        
        btn_add = QPushButton(self.tr("Add Column"))
        btn_add.clicked.connect(self.add_dynamic_column)
        add_layout.addWidget(btn_add)
        
        self.btn_remove = QPushButton(self.tr("Remove Selected"))
        self.btn_remove.setEnabled(False)
        self.btn_remove.clicked.connect(self.remove_selected_column)
        add_layout.addWidget(self.btn_remove)
        
        layout.addLayout(add_layout)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def load_columns(self):
        # We want to load in VISUAL order.
        # Logical Indices:
        # 0..19: Fixed
        # 20..20+len(dyn)-1: Dynamic
        
        count = self.header.count()
        visual_order = []
        for v_idx in range(count):
            l_idx = self.header.logicalIndex(v_idx)
            # Skip Column 0 (Row Counter) - It acts as a static anchor
            if l_idx == 0:
                continue
            visual_order.append(l_idx)
            
        for l_idx in visual_order:
            self._add_item_for_logical_index(l_idx)
            
    def _add_item_for_logical_index(self, l_idx):
        # Determine Label and Type
        is_fixed = l_idx in self.fixed_columns
        
        if is_fixed:
            label = self.fixed_columns[l_idx]
            key = None
            is_new = False
        else:
            # Dynamic
            # Valid only if within range
            dyn_idx = l_idx - len(self.fixed_columns)
            if 0 <= dyn_idx < len(self.dynamic_columns):
                key = self.dynamic_columns[dyn_idx]
                label = self.pretty_labels.get(key, key)
                is_new = False
            else:
                return # Should not happen unless inconsistent
                
        item_label = self.tr("%s (Fixed)") % label if is_fixed else label
        item = QListWidgetItem(item_label)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        
        # Check Visible State
        is_hidden = self.header.isSectionHidden(l_idx)
        item.setCheckState(Qt.CheckState.Unchecked if is_hidden else Qt.CheckState.Checked)
        
        # Store Data
        # UserRole 1: 'fixed' or 'dynamic'
        # UserRole 2: logical_index (original)
        # UserRole 3: key (if dynamic)
        
        item.setData(Qt.ItemDataRole.UserRole + 1, "fixed" if is_fixed else "dynamic")
        item.setData(Qt.ItemDataRole.UserRole + 2, l_idx)
        item.setData(Qt.ItemDataRole.UserRole + 3, key)
        
        self.list_widget.addItem(item)

    def add_dynamic_column(self):
        key = self.combo_add.currentText()
        if not key: return
        
        # Logic: Treat as "new".
        display_label = self.pretty_labels.get(key, key)
        item = QListWidgetItem(display_label)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        
        item.setData(Qt.ItemDataRole.UserRole + 1, "dynamic")
        item.setData(Qt.ItemDataRole.UserRole + 2, -1) # New
        item.setData(Qt.ItemDataRole.UserRole + 3, key)
        
        self.list_widget.addItem(item)
        
        # Update combo
        idx = self.combo_add.findText(key)
        if idx >= 0:
            self.combo_add.removeItem(idx)

    def remove_selected_column(self):
        item = self.list_widget.currentItem()
        if not item: return
        
        col_type = item.data(Qt.ItemDataRole.UserRole + 1)
        if col_type == "fixed":
            QMessageBox.information(self, self.tr("Fixed Column"), self.tr("Fixed columns can only be hidden, not removed from the system."))
            return
            
        key = item.data(Qt.ItemDataRole.UserRole + 3)
        
        # Remove from list
        self.list_widget.takeItem(self.list_widget.row(item))
        
        # Add back to combo if it was an available key
        if key and key not in self.available_keys:
             self.available_keys.append(key)
             self.available_keys.sort()
             self.combo_add.clear()
             self.combo_add.addItems(self.available_keys)
        
        self._update_button_states()

    def _update_button_states(self):
        item = self.list_widget.currentItem()
        if not item:
            self.btn_remove.setEnabled(False)
            return
            
        col_type = item.data(Qt.ItemDataRole.UserRole + 1)
        # ONLY allow removal for dynamic columns (JSON fields)
        self.btn_remove.setEnabled(col_type == "dynamic")

    def get_result(self):
        """
        Return tuple: (new_dynamic_columns_list, visual_indices_map, hidden_indices_set)
        
        But since logical indices CHANGE if dynamic columns change, we must define the target state carefully.
        
        Strategy:
        1. Construct the NEW list of dynamic columns based on items present in ListWidget.
        2. Construct the NEW logical order/mapping.
        3. Return data for DocumentListWidget to apply.
        """
        
        new_dynamic_columns = []
        ordered_items = [] # list of (type, key/orig_idx, is_visible)
        
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            col_type = item.data(Qt.ItemDataRole.UserRole + 1)
            orig_idx = item.data(Qt.ItemDataRole.UserRole + 2)
            key = item.data(Qt.ItemDataRole.UserRole + 3)
            visible = (item.checkState() == Qt.CheckState.Checked)
            
            if col_type == "dynamic":
                new_dynamic_columns.append(key)
                # Its new logical index will be determined later
            
            ordered_items.append({
                "type": col_type,
                "orig_idx": orig_idx,
                "key": key,
                "visible": visible
            })
            
        return new_dynamic_columns, ordered_items
