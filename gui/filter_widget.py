
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QDateEdit, QComboBox, 
    QLineEdit, QPushButton, QGroupBox, QVBoxLayout
)
from PyQt6.QtCore import pyqtSignal, QDate, Qt
from core.query_parser import QueryParser

class FilterWidget(QWidget):
    """
    Widget for filtering documents by Date, Type, and Tags.
    """
    filter_changed = pyqtSignal(dict) # Emits dictionary of filter criteria
    
    def __init__(self):
        super().__init__()
        
        self.parser = QueryParser()
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Smart Search Row
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(10, 0, 0, 0)
        self.txt_smart_search = QLineEdit()
        self.txt_smart_search.setPlaceholderText(self.tr("Search documents (e.g. 'Amazon 2024 Invoice')..."))
        self.txt_smart_search.returnPressed.connect(self.emit_smart_filter)
        search_layout.addWidget(QLabel(self.tr("Search:")))
        search_layout.addWidget(self.txt_smart_search)
        
        btn_advanced = QPushButton(self.tr("Advanced Filter \u25BC"))
        btn_advanced.setCheckable(True)
        btn_advanced.toggled.connect(self._toggle_advanced)
        search_layout.addWidget(btn_advanced)
        
        self.layout.addLayout(search_layout)
        
        # Advanced Group (Hidden by default)
        self.advanced_group = QGroupBox(self.tr("Advanced Criteria"))
        self.advanced_group.setVisible(False)
        self.layout.addWidget(self.advanced_group)
        
        form = QHBoxLayout(self.advanced_group)
        
        # Date Range
        form.addWidget(QLabel(self.tr("From:")))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setDate(QDate.currentDate().addYears(-1)) # Default 1 year back
        
        self.enable_date = QPushButton(self.tr("Enable Date"))
        self.enable_date.setCheckable(True)
        self.enable_date.setChecked(False)
        self.enable_date.toggled.connect(self._toggle_date_inputs)
        
        self.date_from.setEnabled(False)
        form.addWidget(self.date_from)
        
        form.addWidget(QLabel(self.tr("To:")))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setEnabled(False)
        form.addWidget(self.date_to)
        
        form.addWidget(self.enable_date)

        # Type
        form.addWidget(QLabel(self.tr("Type:")))
        self.combo_type = QComboBox()
        self.combo_type.addItem(self.tr("All"), None)
        self.combo_type.addItems(["Invoice", "Receipt", "Contract", "Letter", "Other"])
        form.addWidget(self.combo_type)
        
        # Tags
        form.addWidget(QLabel(self.tr("Tags:")))
        self.txt_tags = QLineEdit()
        self.txt_tags.setPlaceholderText(self.tr("e.g. tax"))
        form.addWidget(self.txt_tags)
        
        # Apply/Reset (Advanced)
        btn_apply = QPushButton(self.tr("Apply Advanced"))
        btn_apply.clicked.connect(self.emit_filter)
        form.addWidget(btn_apply)
        
    def _toggle_advanced(self, checked: bool):
        self.advanced_group.setVisible(checked)
        
    def emit_smart_filter(self):
        query = self.txt_smart_search.text().strip()
        if not query:
            self.filter_changed.emit({})
            return
            
        # Parse query
        criteria = self.parser.parse(query)
        self.filter_changed.emit(criteria)

    def _toggle_date_inputs(self, checked: bool):
        self.date_from.setEnabled(checked)
        self.date_to.setEnabled(checked)
        
    def reset_filter(self):
        self.txt_smart_search.clear()
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
