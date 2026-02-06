
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, 
    QListWidgetItem, QLabel, QFrame, QPushButton, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QAction

class SemanticVariableSelector(QFrame):
    """
    A reusable premium component for selecting semantic variables with 
    search, categories, and descriptions.
    """
    variable_selected = pyqtSignal(str)

    VARIABLE_MAP = {
        "System / Zeit": {
            "DAYS_IN_STATE": "⏱️ Tage im aktuellen Status",
            "DAYS_UNTIL_DUE": "📅 Tage bis zur Fälligkeit",
            "AGE_DAYS": "⏳ Alter des Dokuments (Tage)",
        },
        "Finanzen": {
            "monetary_summation.grand_total_amount": "💰 Bruttobetrag (Gesamt)",
            "monetary_summation.tax_basis_total_amount": "💵 Nettobetrag",
            "monetary_summation.tax_total_amount": "🏦 Umsatzsteuerbetrag",
            "currency": "💱 Währung (EUR, USD...)",
            "iban": "💳 IBAN des Senders",
        },
        "Dokument": {
            "sender_name": "👤 Absender / Firma",
            "doc_date": "📍 Belegdatum",
            "doc_number": "🔢 Rechnungs/Belegnummer",
            "due_date": "🚨 Fälligkeitsdatum",
        }
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setFixedWidth(280)
        self.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 8px;
            }
            QLineEdit {
                padding: 6px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                margin: 5px;
            }
            QListWidget {
                border: none;
                background: transparent;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
            QLabel#categoryLabel {
                background-color: #f8f9fa;
                color: #7f8c8d;
                font-weight: bold;
                font-size: 10px;
                padding: 4px 8px;
                text-transform: uppercase;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Variable suchen...")
        self.search_bar.textChanged.connect(self._filter_list)
        layout.addWidget(self.search_bar)

        # List
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

        self._populate_list()

    def _populate_list(self, filter_text=""):
        self.list_widget.clear()
        filter_text = filter_text.lower()

        for category, vars in self.VARIABLE_MAP.items():
            # Filter variables in this category
            matching_vars = {k: v for k, v in vars.items() if filter_text in k.lower() or filter_text in v.lower()}
            
            if matching_vars:
                # Add Category Header
                cat_item = QListWidgetItem(category)
                cat_item.setFlags(Qt.ItemFlag.NoItemFlags) # Not selectable
                cat_item.setBackground(Qt.GlobalColor.lightGray)
                
                header_lab = QLabel(category)
                header_lab.setObjectName("categoryLabel")
                
                self.list_widget.addItem(cat_item)
                self.list_widget.setItemWidget(cat_item, header_lab)

                for var_id, description in matching_vars.items():
                    item = QListWidgetItem(description)
                    item.setData(Qt.ItemDataRole.UserRole, var_id)
                    item.setToolTip(f"ID: {var_id}")
                    self.list_widget.addItem(item)

    def _filter_list(self, text):
        self._populate_list(text)

    def _on_item_clicked(self, item):
        var_id = item.data(Qt.ItemDataRole.UserRole)
        if var_id:
            self.variable_selected.emit(var_id)
            self.hide() # Auto-hide if used as popup

class SemanticVariableButton(QPushButton):
    """
    A button that triggers the selector as a popup.
    """
    variable_selected = pyqtSignal(str)

    def __init__(self, text="Select Variable...", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("text-align: left; padding: 4px;")
        self.clicked.connect(self._show_popup)
        
    def _show_popup(self):
        self.selector = SemanticVariableSelector()
        self.selector.setWindowFlags(Qt.WindowType.Popup)
        self.selector.variable_selected.connect(self.variable_selected.emit)
        
        # Position below button
        pos = self.mapToGlobal(self.rect().bottomLeft())
        self.selector.move(pos)
        self.selector.show()
        self.selector.search_bar.setFocus()
