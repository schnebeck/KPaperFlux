from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QCheckBox, QDialogButtonBox, QMessageBox
from gui.utils import show_selectable_message_box

class SaveListDialog(QDialog):
    def __init__(self, parent=None, has_selection=False):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Save as List"))
        self.resize(300, 150)
        self.has_selection = has_selection
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(self.tr("List Name:")))
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText(self.tr("My List..."))
        layout.addWidget(self.input_name)
        
        self.chk_selection = QCheckBox(self.tr("Save Selection Only"))
        if has_selection:
            self.chk_selection.setChecked(True)
            self.chk_selection.setEnabled(True)
        else:
            self.chk_selection.setChecked(False)
            self.chk_selection.setEnabled(False) # Force "All Displayed" if nothing selected
            self.chk_selection.setToolTip(self.tr("No items selected. Saving all displayed items."))
            
        layout.addWidget(self.chk_selection)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def validate_and_accept(self):
        if not self.input_name.text().strip():
             show_selectable_message_box(self, self.tr("Error"), self.tr("Please enter a name.", icon=QMessageBox.Icon.Warning))
             return
        self.accept()
        
    def get_data(self):
        return self.input_name.text().strip(), self.chk_selection.isChecked()
