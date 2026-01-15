
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QComboBox, QPushButton, QColorDialog, QDialogButtonBox,
    QFormLayout
)
from PyQt6.QtGui import QColor

class StamperDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Stamp Document"))
        self.resize(300, 200)
        
        self.selected_color = (255, 0, 0) # Default Red
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.txt_text = QLineEdit("PAID")
        form.addRow(self.tr("Text:"), self.txt_text)
        
        self.combo_pos = QComboBox()
        self.combo_pos.addItems(["Top-Right", "Top-Left", "Bottom-Right", "Bottom-Left", "Center"])
        # Map nice names to internal keys if needed, but lowercase string match works with Stamper.
        form.addRow(self.tr("Position:"), self.combo_pos)
        
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
        
        layout.addLayout(form)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def choose_color(self):
        c = QColorDialog.getColor(initial=QColor(*self.selected_color), parent=self)
        if c.isValid():
            self.selected_color = (c.red(), c.green(), c.blue())
            self.lbl_color.setStyleSheet(f"background-color: {c.name()}; border: 1px solid black;")
            
    def get_data(self):
        """Return (text, position_str, color_tuple)"""
        return (
            self.txt_text.text(),
            self.combo_pos.currentText().lower(),
            self.selected_color
        )
