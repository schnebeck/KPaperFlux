
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, 
    QDialogButtonBox, QFormLayout
)

class BatchTagDialog(QDialog):
    """
    Dialog to specify tags to add and remove from selected documents.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manage Tags"))
        self.resize(400, 200)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.txt_add = QLineEdit()
        self.txt_add.setPlaceholderText("tag1, tag2")
        self.txt_add.setToolTip(self.tr("Tags to add to selected documents (comma separated)."))
        
        self.txt_remove = QLineEdit()
        self.txt_remove.setPlaceholderText("tag3")
        self.txt_remove.setToolTip(self.tr("Tags to remove from selected documents (comma separated)."))
        
        form.addRow(self.tr("Add Tags:"), self.txt_add)
        form.addRow(self.tr("Remove Tags:"), self.txt_remove)
        
        layout.addLayout(form)
        
        # Info
        lbl_info = QLabel(self.tr("Leave empty to make no changes."))
        lbl_info.setStyleSheet("color: gray;")
        layout.addWidget(lbl_info)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_data(self):
        """Return (tags_to_add_list, tags_to_remove_list)"""
        add_str = self.txt_add.text()
        remove_str = self.txt_remove.text()
        
        def parse_tags(s):
            return [t.strip() for t in s.split(",") if t.strip()]
            
        return parse_tags(add_str), parse_tags(remove_str)
