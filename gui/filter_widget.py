
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QDateEdit, QComboBox, 
    QLineEdit, QPushButton, QGroupBox
)
from PyQt6.QtCore import pyqtSignal, QDate, Qt

class FilterWidget(QWidget):
    """
    Widget for filtering documents by Date, Type, and Tags.
    """
    filter_changed = pyqtSignal(dict) # Emits dictionary of filter criteria
    
    def __init__(self):
        super().__init__()
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        group = QGroupBox(self.tr("Filter"))
        self.layout.addWidget(group)
        
        form = QHBoxLayout(group)
        
        # Date Range
        form.addWidget(QLabel(self.tr("From:")))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setDate(QDate.currentDate().addYears(-1)) # Default 1 year back
        # self.date_from.setSpecialValueText(self.tr("Start")) # Optional: Allow "Any" by checkable?
        # For simplicity: Use a checkable group or checkbox for "Enable Date Filter"
        # Or just assume large range.
        self.enable_date = QPushButton(self.tr("Date Filter"))
        self.enable_date.setCheckable(True)
        self.enable_date.setChecked(False)
        self.enable_date.toggled.connect(self._toggle_date_inputs)
        
        # form.addWidget(self.enable_date) 
        # Better UX: Checkbox "Filter Date" next to inputs.
        
        self.date_from.setEnabled(False)
        form.addWidget(self.date_from)
        
        form.addWidget(QLabel(self.tr("To:")))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setEnabled(False)
        form.addWidget(self.date_to)
        
        # Enable Button logic
        form.addWidget(self.enable_date)

        # Type
        form.addWidget(QLabel(self.tr("Type:")))
        self.combo_type = QComboBox()
        self.combo_type.addItem(self.tr("All"), None)
        # Populate standard types or fetch from DB?
        # Hardcode common ones plus dynamic?
        self.combo_type.addItems(["Invoice", "Receipt", "Contract", "Letter", "Other"])
        form.addWidget(self.combo_type)
        
        # Tags
        form.addWidget(QLabel(self.tr("Tags:")))
        self.txt_tags = QLineEdit()
        self.txt_tags.setPlaceholderText(self.tr("e.g. tax, insurance"))
        form.addWidget(self.txt_tags)
        
        # Apply/Reset
        btn_apply = QPushButton(self.tr("Apply"))
        btn_apply.clicked.connect(self.emit_filter)
        form.addWidget(btn_apply)
        
        btn_reset = QPushButton(self.tr("Reset"))
        btn_reset.clicked.connect(self.reset_filter)
        form.addWidget(btn_reset)
        
        # Connect change signals for auto-apply if desired?
        # self.combo_type.currentIndexChanged.connect(self.emit_filter)
        # For dates/text usually explicit Apply is better.

    def _toggle_date_inputs(self, checked: bool):
        self.date_from.setEnabled(checked)
        self.date_to.setEnabled(checked)
        
    def reset_filter(self):
        self.enable_date.setChecked(False)
        self.date_from.setDate(QDate.currentDate().addYears(-1))
        self.date_to.setDate(QDate.currentDate())
        self.combo_type.setCurrentIndex(0)
        self.txt_tags.clear()
        self.emit_filter()
        
    def emit_filter(self):
        criteria = {}
        
        if self.enable_date.isChecked():
            # Convert QDate to python date or string 'YYYY-MM-DD'
            criteria['date_from'] = self.date_from.date().toString("yyyy-MM-dd")
            criteria['date_to'] = self.date_to.date().toString("yyyy-MM-dd")
            
        type_val = self.combo_type.currentData()
        if not type_val: 
            # Check text if 'All' has None data
            if self.combo_type.currentIndex() != 0:
                 type_val = self.combo_type.currentText()
                 
        if type_val:
            criteria['type'] = type_val
            
        tags = self.txt_tags.text().strip()
        if tags:
            criteria['tags'] = tags
            
        self.filter_changed.emit(criteria)
