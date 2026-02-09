from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QComboBox, QSpinBox, QColorDialog)
from PyQt6.QtCore import Qt

class DashboardEntryDialog(QDialog):
    def __init__(self, filter_tree, parent=None, entry_data=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Dashboard Filter View"))
        self.setMinimumWidth(300)
        self.filter_tree = filter_tree
        self.entry_data = entry_data or {}

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Name
        layout.addWidget(QLabel(self.tr("Display Title:")))
        self.edit_title = QLineEdit(self.entry_data.get("title", ""))
        self.edit_title.setPlaceholderText(self.tr("e.g. My Invoices"))
        layout.addWidget(self.edit_title)

        # Filter Selection
        layout.addWidget(QLabel(self.tr("Linked Filter Rule:")))
        self.combo_filter = QComboBox()
        # Ensure we have filters
        if hasattr(self.filter_tree, 'get_all_filters'):
            self.filters = self.filter_tree.get_all_filters()
        else:
            self.filters = []

        # Add Presets first
        self.combo_filter.addItem(self.tr("--- Choose Filter ---"), None)
        self.combo_filter.addItem(self.tr("Inbox (NEW)"), {"type": "preset", "id": "NEW"})
        self.combo_filter.addItem(self.tr("Total Documents"), {"type": "preset", "id": "ALL"})
        self.combo_filter.addItem(self.tr("Processed Documents"), {"type": "preset", "id": "PROCESSED"})
        # self.combo_filter.addItem("--- Custom Filters ---", None) # Optional separator

        current_idx = 0
        preset_id = self.entry_data.get("preset_id")
        filter_id = self.entry_data.get("filter_id")

        # Handle Presets selection matching
        if preset_id:
            for i in range(self.combo_filter.count()):
                d = self.combo_filter.itemData(i)
                if d and d.get("type") == "preset" and d.get("id") == preset_id:
                    current_idx = i
                    break

        for f in self.filters:
            self.combo_filter.addItem(self.tr("Filter: %s") % f.name, {"type": "filter", "id": f.id})
            if filter_id == f.id:
                current_idx = self.combo_filter.count() - 1

        self.combo_filter.setCurrentIndex(current_idx)
        layout.addWidget(self.combo_filter)

        # Aggregation
        layout.addWidget(QLabel(self.tr("Aggregation Mode:")))
        self.combo_agg = QComboBox()
        self.combo_agg.addItem(self.tr("Count documents"), "count")
        self.combo_agg.addItem(self.tr("Sum amounts (€)"), "sum")
        
        current_agg = self.entry_data.get("aggregation", "count")
        idx_agg = self.combo_agg.findData(current_agg)
        if idx_agg >= 0: self.combo_agg.setCurrentIndex(idx_agg)
        layout.addWidget(self.combo_agg)

        # Color
        layout.addWidget(QLabel(self.tr("Color Theme:")))
        self.btn_color = QPushButton(self.tr("Choose Color..."))
        self.current_color = self.entry_data.get("color", "#3b82f6")
        self.btn_color.setStyleSheet(f"background-color: {self.current_color}; min-height: 30px; border-radius: 4px;")
        self.btn_color.clicked.connect(self.choose_color)
        layout.addWidget(self.btn_color)

        layout.addSpacing(10)

        # Buttons
        btns = QHBoxLayout()
        btn_ok = QPushButton(self.tr("Save View"))
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton(self.tr("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def choose_color(self):
        # Import removed here as it is already at the top
        color = QColorDialog.getColor(Qt.GlobalColor.blue, self)
        if color.isValid():
            self.current_color = color.name()
            self.btn_color.setStyleSheet(f"background-color: {self.current_color}; min-height: 30px; border-radius: 4px;")

    def get_data(self):
        data = {
            "title": self.edit_title.text(),
            "color": self.current_color,
            "aggregation": self.combo_agg.currentData(),
            "row": self.entry_data.get("row", 0), # Keep existing
            "col": self.entry_data.get("col", 0)
        }
        # If title is empty, use filter name
        if not data["title"]:
            data["title"] = self.combo_filter.currentText().replace(self.tr("Filter:"), "").strip()

        selection = self.combo_filter.currentData()
        if selection:
            if selection["type"] == "preset":
                data["preset_id"] = selection["id"]
            else:
                data["filter_id"] = selection["id"]
        return data
