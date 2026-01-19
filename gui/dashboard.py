
import json
from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QFrame,  QHBoxLayout, QScrollArea, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor, QPalette, QCursor

class StatCard(QFrame):
    clicked = pyqtSignal(dict) # Emits the filter query

    def __init__(self, title, count, color_hex, filter_query, parent=None):
        super().__init__(parent)
        self.filter_query = filter_query
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setObjectName("StatCard")
        
        # Styles
        self.setStyleSheet(f"""
            QFrame#StatCard {{
                background-color: white;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
            }}
            QFrame#StatCard:hover {{
                border: 1px solid {color_hex};
                background-color: #f9fafb;
            }}
        """)
        
        layout = QVBoxLayout(self)
        
        # Title
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #6b7280; font-weight: bold; font-size: 11pt;")
        layout.addWidget(lbl_title)
        
        # Count
        lbl_count = QLabel(str(count))
        lbl_count.setStyleSheet(f"color: {color_hex}; font-weight: bold; font-size: 24pt;")
        lbl_count.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(lbl_count)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.filter_query)

class DashboardWidget(QWidget):
    navigation_requested = pyqtSignal(dict) # Emits filter query to MainWindow

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Grid for Cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.content_widget = QWidget()
        self.grid = QGridLayout(self.content_widget)
        self.grid.setSpacing(20)
        self.grid.setContentsMargins(20, 20, 20, 20)
        
        self.scroll.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll)
        
        self.refresh_stats()

    def refresh_stats(self):
        # Clear existing
        for i in reversed(range(self.grid.count())): 
            self.grid.itemAt(i).widget().setParent(None)
            
        # Layout: 3 columns
        col_count = 3
        
        # 1. Inbox (NEW Entities)
        inbox_count = self.db_manager.count_entities("NEW")
        inbox_card = StatCard(
            "Inbox", 
            inbox_count, 
            "#3b82f6", # Blue
            {"status": "NEW"} # This query needs to be handled by DocumentList later!
        )
        inbox_card.clicked.connect(self.navigation_requested.emit)
        inbox_card.setFixedHeight(120)
        self.grid.addWidget(inbox_card, 0, 0)
        
        # 2. Total Entities
        total_count = self.db_manager.count_entities(None)
        total_card = StatCard(
            "Total Docs", 
            total_count, 
            "#10b981", # Green
            None # Show all
        )
        total_card.clicked.connect(self.navigation_requested.emit)
        total_card.setFixedHeight(120)
        self.grid.addWidget(total_card, 0, 1)

        # 3. Processed (Not NEW)
        # Simple math or query
        processed_count = total_count - inbox_count
        processed_card = StatCard(
            "Processed", 
            processed_count, 
            "#6b7280", # Gray
            {"status": "PROCESSED"} 
        )
        processed_card.clicked.connect(self.navigation_requested.emit)
        processed_card.setFixedHeight(120)
        self.grid.addWidget(processed_card, 0, 2)

            
        # Add Stretch to push items to top
        self.grid.setRowStretch(self.grid.rowCount(), 1)


    def _get_cards_config(self):
        # Todo: Move to json config if needed. For now hardcoded as per plan.
        return [
            {
                "title": "Inbox (Untagged)", 
                "color": "#3b82f6", # Blue
                "query": {
                    "field": "tags",
                    "op": "equals",
                    "value": "" # Using empty check logic? Or specific op? 
                    # Advanced Search logic for 'equals' '' matches empty strings or NULL?
                    # Let's hope so. If not we might need 'empty' op.
                    # Currently core/database.py handles 'equals' as exact match.
                    # Empty string match.
                } 
            },
            {
                "title": "Open Invoices",
                "color": "#ef4444", # Red
                "query": {
                    "op": "and",
                    "conditions": [
                         {"field": "doc_type", "op": "contains", "value": "Invoice"}, # JSON List contains
                         {"field": "tags", "op": "contains", "value": "status:open"}
                    ]
                }
            },
            {
                "title": "To-Do",
                "color": "#f59e0b", # Amber
                "query": {
                    "field": "tags",
                    "op": "contains", 
                    "value": "todo:" 
                }
            },
            {
               "title": "Drafts",
               "color": "#6b7280", # Gray
               "query": {
                   "field": "tags",
                   "op": "contains",
                   "value": "draft"
               }
            }
        ]
