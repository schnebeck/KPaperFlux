
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QDateEdit, 
                             QStackedWidget, QLabel)
from PyQt6.QtCore import Qt, QDate, pyqtSignal

class DateRangePicker(QWidget):
    """
    Widget to select date ranges:
    - Specific Date
    - Last N Days
    - Custom Range (Start - End)
    - Specific Month/Year (simplified to Range)
    """
    rangeChanged = pyqtSignal(str) # Emits standardized logic string or JSON logic? 
    # Actually, for the filter builder we might want raw values.
    # But AdvancedFilter expects `value`. 
    # If "Last 7 days", value might be "LAST_7_DAYS" (handled by SQL translator?)
    # or we calculate the actual date range?
    # Better to emit calculated dates for simplicity of SQL backend unless we upgrade backend.
    # Let's emit a simplified tuple/string that the backend understands or standard dates.
    # If we return "2023-01-01,2023-01-31", operator "between"?
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.combo_type = QComboBox()
        self.combo_type.addItems([
            self.tr("Specific Date"),
            self.tr("Date Range"),
            self.tr("Last 7 Days"),
            self.tr("Last 30 Days"),
            self.tr("This Month"),
            self.tr("Last Month"),
            self.tr("This Year")
        ])
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        self.layout.addWidget(self.combo_type)
        
        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack)
        
        # 0: Specific Date
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.stack.addWidget(self.date_edit)
        
        # 1: Range (Start - End)
        self.range_widget = QWidget()
        r_layout = QHBoxLayout(self.range_widget)
        r_layout.setContentsMargins(0,0,0,0)
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate().addDays(-30))
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        r_layout.addWidget(self.date_start)
        r_layout.addWidget(QLabel("-"))
        r_layout.addWidget(self.date_end)
        self.stack.addWidget(self.range_widget)
        
        # 2: None (Presets)
        self.empty_widget = QWidget()
        self.stack.addWidget(self.empty_widget)
        
    def _on_type_changed(self, index):
        if index == 0:
            self.stack.setCurrentIndex(0)
        elif index == 1:
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(2) # Presets don't need input
            
    def get_value(self):
        """
        Returns a value compatible with the filter logic.
        """
        idx = self.combo_type.currentIndex()
        if idx == 0: # Specific
            return self.date_edit.date().toString(Qt.DateFormat.ISODate)
        elif idx == 1: # Range
            start = self.date_start.date().toString(Qt.DateFormat.ISODate)
            end = self.date_end.date().toString(Qt.DateFormat.ISODate)
            return f"{start},{end}"
        elif idx == 2: return "LAST_7_DAYS"
        elif idx == 3: return "LAST_30_DAYS"
        elif idx == 4: return "THIS_MONTH"
        elif idx == 5: return "LAST_MONTH"
        elif idx == 6: return "THIS_YEAR"
        return ""

    def set_value(self, val):
        # Reverse logic to restore state
        if not val: 
            return
            
        if val == "LAST_7_DAYS": self.combo_type.setCurrentIndex(2)
        elif val == "LAST_30_DAYS": self.combo_type.setCurrentIndex(3)
        elif val == "THIS_MONTH": self.combo_type.setCurrentIndex(4)
        elif val == "LAST_MONTH": self.combo_type.setCurrentIndex(5)
        elif val == "THIS_YEAR": self.combo_type.setCurrentIndex(6)
        elif "," in val:
            # Range
            parts = val.split(",")
            if len(parts) == 2:
                self.date_start.setDate(QDate.fromString(parts[0], Qt.DateFormat.ISODate))
                self.date_end.setDate(QDate.fromString(parts[1], Qt.DateFormat.ISODate))
                self.combo_type.setCurrentIndex(1)
        else:
            # Specific
            self.date_edit.setDate(QDate.fromString(val, Qt.DateFormat.ISODate))
            self.combo_type.setCurrentIndex(0)
