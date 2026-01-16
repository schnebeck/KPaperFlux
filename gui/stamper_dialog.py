
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QComboBox, QPushButton, QColorDialog, QDialogButtonBox,
    QFormLayout, QSpinBox, QPlainTextEdit, QListWidget, QGroupBox,
    QAbstractItemView
)
from PyQt6.QtGui import QColor

class StamperDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Stamp Document"))
        self.resize(500, 400)
        
        self.selected_color = (255, 0, 0) # Default Red
        self.existing_stamps = []
        self.selected_stamp_id = None
        
        layout = QVBoxLayout(self)
        
        # --- Existing Stamps Area ---
        self.grp_existing = QGroupBox(self.tr("Existing Stamps"))
        existing_layout = QVBoxLayout(self.grp_existing)
        
        self.list_stamps = QListWidget()
        self.list_stamps.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_stamps.itemSelectionChanged.connect(self.on_selection_changed)
        existing_layout.addWidget(self.list_stamps)
        
        btn_remove_sel = QPushButton(self.tr("Remove Selected"))
        btn_remove_sel.clicked.connect(self.on_remove_selected)
        existing_layout.addWidget(btn_remove_sel)
        
        layout.addWidget(self.grp_existing)
        
        # --- New Stamp Form ---
        grp_new = QGroupBox(self.tr("New Stamp"))
        form = QFormLayout(grp_new)
        
        self.txt_text = QPlainTextEdit("PAID")
        self.txt_text.setPlaceholderText(self.tr("Enter text (multi-line supported)..."))
        self.txt_text.setFixedHeight(60)
        form.addRow(self.tr("Text:"), self.txt_text)
        
        self.combo_pos = QComboBox()
        self.combo_pos.addItems([
            "Top-Right", "Top-Center", "Top-Left", 
            "Center", 
            "Bottom-Right", "Bottom-Center", "Bottom-Left"
        ])
        form.addRow(self.tr("Position:"), self.combo_pos)
        
        self.spin_rotation = QSpinBox()
        self.spin_rotation.setRange(0, 360)
        self.spin_rotation.setValue(45)
        self.spin_rotation.setSuffix("°")
        form.addRow(self.tr("Rotation:"), self.spin_rotation)
        
        # Color
        color_layout = QHBoxLayout()
        self.lbl_color = QLabel("   ")
        self.lbl_color.setStyleSheet(f"background-color: rgb(255,0,0); border: 1px solid black;")
        self.lbl_color.setFixedSize(20, 20)
        
        btn_color = QPushButton(self.tr("Select Color..."))
        btn_color.clicked.connect(self.choose_color)
        
        color_layout.addWidget(self.lbl_color)
        color_layout.addWidget(btn_color)
        form.addRow(self.tr("Color:"), color_layout)
        
        layout.addWidget(grp_new)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        
        self.btn_apply = buttons.addButton(self.tr("Add Stamp"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_apply.clicked.connect(self.on_apply)
        
        layout.addWidget(buttons)
        
        self.action = "apply" # 'apply' or 'remove'
        self.result_stamp_id = None # ID to remove if action is remove
        
    def populate_stamps(self, stamps: list):
        """stamps: list of dict {'id': str, 'text': str}"""
        self.existing_stamps = stamps
        self.list_stamps.clear()
        for s in stamps:
            # Show first line of text or truncated
            display = s['text'].replace('\n', ' ')
            if len(display) > 50:
                display = display[:47] + "..."
            self.list_stamps.addItem(display)
            
        self.grp_existing.setVisible(len(stamps) > 0)
        self.adjustSize()
            
    def on_selection_changed(self):
        row = self.list_stamps.currentRow()
        if row >= 0 and row < len(self.existing_stamps):
            self.selected_stamp_id = self.existing_stamps[row]['id']
        else:
            self.selected_stamp_id = None
            
    def choose_color(self):
        c = QColorDialog.getColor(initial=QColor(*self.selected_color), parent=self)
        if c.isValid():
            self.selected_color = (c.red(), c.green(), c.blue())
            self.lbl_color.setStyleSheet(f"background-color: {c.name()}; border: 1px solid black;")
            
    def on_apply(self):
        self.action = "apply"
        self.accept()
        
    def on_remove_selected(self):
        if self.selected_stamp_id:
            self.action = "remove"
            self.result_stamp_id = self.selected_stamp_id
            self.accept()
            
    def get_data(self):
        """Return (action, text, position_str, color_tuple, rotation, stamp_id_to_remove)."""
        return (
            self.action,
            self.txt_text.toPlainText(),
            self.combo_pos.currentText().lower(),
            self.selected_color,
            self.spin_rotation.value(),
            self.result_stamp_id
        )
