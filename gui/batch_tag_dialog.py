from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, 
    QDialogButtonBox, QFormLayout, QGroupBox
)
from PyQt6.QtCore import Qt
from gui.completers import MultiTagCompleter
from gui.widgets.multi_select_combo import MultiSelectComboBox

class BatchTagDialog(QDialog):
    """
    Dialog to edit tags common to all selected documents.
    Changes here are applied as diffs (Add/Remove) to preserve individual extra tags.
    """
    def __init__(self, available_tags: list[str] = None, common_tags: list[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Batch Tag Editor"))
        self.resize(500, 350)
        
        layout = QVBoxLayout(self)
        
        self.available_tags = available_tags or []
        self.original_common = common_tags or []
        self.original_common_set = set(t.strip() for t in self.original_common)
        
        # Explanation Box
        info_group = QGroupBox(self.tr("Logic"))
        info_layout = QVBoxLayout(info_group)
        lbl_info = QLabel(
            self.tr("<b>Checked Tags:</b> Will be present on ALL selected documents (Merged).<br>"
                    "<b>Unchecked Tags:</b> Will be REMOVED from ALL selected documents (if they were common).<br>"
                    "<i>Individual unique tags on specific documents are preserved unless forced removed.</i>")
        )
        lbl_info.setWordWrap(True)
        lbl_info.setTextFormat(Qt.TextFormat.RichText)
        info_layout.addWidget(lbl_info)
        layout.addWidget(info_group)

        form = QFormLayout()
        
        # Common Tags Editor (Combo Box)
        self.combo_common = MultiSelectComboBox()
        self.combo_common.addItems(self.available_tags) # Populate with all known tags
        self.combo_common.setCheckedItems(self.original_common) # Check the common ones
        
        form.addRow(self.tr("Common Tags:"), self.combo_common)
        
        # Extra Force Remove
        self.extra_remove = QLineEdit()
        self.extra_remove.setPlaceholderText("Optional: Tags to strip from everyone...")
        self.extra_remove.setCompleter(MultiTagCompleter(self.available_tags, self))
        form.addRow(self.tr("Force Remove Mixed:"), self.extra_remove)
        
        layout.addLayout(form)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_data(self):
        """
        Calculate diff.
        Returns (tags_to_add, tags_to_remove)
        """
        current_list = self.combo_common.getCheckedItems()
        current_set = set(current_list)
        
        # Added: In New (Checked) but not in Old (Common)
        # This implies user checked a box that wasn't common before.
        # Logic: Add this tag to EVERY document.
        added = list(current_set - self.original_common_set)
        
        # Removed: In Old (Common) but not in New (Unchecked)
        # User unchecked a box that was previously common.
        # Logic: Remove this tag from EVERY document.
        removed = list(self.original_common_set - current_set)
        
        # Extra Force Remove
        force_rem_text = self.extra_remove.text()
        force_rem_list = [t.strip() for t in force_rem_text.split(",") if t.strip()]
        removed.extend(force_rem_list)
        
        return added, removed
