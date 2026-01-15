from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QMenu
from PyQt6.QtCore import pyqtSignal, Qt, QPoint
from core.database import DatabaseManager

class DocumentListWidget(QTableWidget):
    """
    Displays the list of documents from the database.
    """
    document_selected = pyqtSignal(str) # UUID
    delete_requested = pyqtSignal(str) # UUID
    reprocess_requested = pyqtSignal(str) # UUID
    
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db = db_manager
        
        # Setup table columns
        self.columns = [
            self.tr("Date"), 
            self.tr("Sender"), 
            self.tr("Type"), 
            self.tr("Amount"), 
            self.tr("Filename")
        ]
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)
        
        # Stretch columns
        header = self.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # Sender stretches
        
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        self.itemSelectionChanged.connect(self._on_selection_changed)
        
        # Context Menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, pos: QPoint):
        """Show context menu for selected item."""
        item = self.itemAt(pos)
        if not item:
            return
            
        uuid = self.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        if not uuid:
            return
            
        menu = QMenu(self)
        reprocess_action = menu.addAction(self.tr("Reprocess (OCR)"))
        delete_action = menu.addAction(self.tr("Delete Document"))
        
        action = menu.exec(self.mapToGlobal(pos))
        
        if action == reprocess_action:
            self.reprocess_requested.emit(uuid)
        elif action == delete_action:
            self.delete_requested.emit(uuid)

    def _on_selection_changed(self):
        """Handle selection to emit UUID."""
        rows = self.selectionModel().selectedRows()
        if rows:
            # Get UUID from the first column's UserRole
            row_idx = rows[0].row()
            first_item = self.item(row_idx, 0)
            if first_item:
                uuid = first_item.data(Qt.ItemDataRole.UserRole)
                if uuid:
                    self.document_selected.emit(uuid)

    def refresh_list(self):
        """Fetch data from DB and populate table."""
        self.setRowCount(0) # Clear existing
        documents = self.db.get_all_documents()
        
        self.setRowCount(len(documents))
        
        for row, doc in enumerate(documents):
            # Map Document fields to columns
            # ["Date", "Sender", "Type", "Amount", "Filename"]
            
            date_str = str(doc.doc_date) if doc.doc_date else ""
            sender = doc.sender or ""
            doc_type = doc_doc_type = doc.doc_type or ""
            amount_str = f"{doc.amount:.2f}" if doc.amount is not None else ""
            filename = doc.original_filename
            
            item_date = QTableWidgetItem(date_str)
            item_date.setData(Qt.ItemDataRole.UserRole, doc.uuid) # Store UUID
            
            self.setItem(row, 0, item_date)
            self.setItem(row, 1, QTableWidgetItem(sender))
            self.setItem(row, 2, QTableWidgetItem(doc_type))
            self.setItem(row, 3, QTableWidgetItem(amount_str))
            self.setItem(row, 4, QTableWidgetItem(filename))
