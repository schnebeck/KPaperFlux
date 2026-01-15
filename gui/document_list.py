from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QMenu
from PyQt6.QtCore import pyqtSignal, Qt, QPoint, QSettings
from core.database import DatabaseManager

class DocumentListWidget(QTableWidget):
    """
    Displays the list of documents from the database.
    """
    document_selected = pyqtSignal(str) # UUID
    delete_requested = pyqtSignal(str) # UUID
    reprocess_requested = pyqtSignal(str) # UUID
    merge_requested = pyqtSignal(list) # List[str] UUIDs
    export_requested = pyqtSignal(list) # List[str] UUIDs
    stamp_requested = pyqtSignal(str) # UUID (Single for now, or list?) Let's support single for stamp simplicity.
    tags_update_requested = pyqtSignal(list) # List[str] UUIDs
    
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db = db_manager
        self.current_filter = {} # Store current filter criteria
        
        # Setup table columns
        self.columns = [
            self.tr("Date"), 
            self.tr("Sender"), 
            self.tr("Type"), 
            self.tr("Tags"),
            self.tr("Amount"), 
            self.tr("Filename")
        ]
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)
        
        # Stretch columns
        header = self.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # Sender stretches
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch) # Filename stretches? No maybe share
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_header_menu)
        
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection) # Allow multiple
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        
        self.itemSelectionChanged.connect(self._on_selection_changed)
        
        # Context Menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        # Restore State
        self.restore_state()

    def show_header_menu(self, pos: QPoint):
        """Show context menu to toggle columns."""
        menu = QMenu(self)
        header = self.horizontalHeader()
        
        for i, col_name in enumerate(self.columns):
            action = menu.addAction(col_name)
            action.setCheckable(True)
            action.setChecked(not header.isSectionHidden(i))
            action.setData(i)
            action.triggered.connect(lambda checked, idx=i: self.toggle_column(idx, checked))
            
        menu.exec(header.mapToGlobal(pos))
        
    def toggle_column(self, index: int, visible: bool):
        if visible:
            self.horizontalHeader().showSection(index)
        else:
            self.horizontalHeader().hideSection(index)
        self.save_state()

    def save_state(self):
        settings = QSettings("KPaperFlux", "DocumentList")
        settings.setValue("headerState", self.horizontalHeader().saveState())
        
    def restore_state(self):
        settings = QSettings("KPaperFlux", "DocumentList")
        state = settings.value("headerState")
        if state:
            self.horizontalHeader().restoreState(state)

    def show_context_menu(self, pos: QPoint):
        """Show context menu for selected item."""
        item = self.itemAt(pos)
        if not item:
            return
            
        uuid = self.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        if not uuid:
            return
            
        menu = QMenu(self)
        
        # Check selection count for Merge
        selected_rows = self.selectionModel().selectedRows()
        if len(selected_rows) > 1:
             merge_action = menu.addAction(self.tr("Merge Selected"))
        else:
             merge_action = None
  
        reprocess_action = menu.addAction(self.tr("Reprocess (OCR)"))
        tags_action = menu.addAction(self.tr("Manage Tags..."))
        stamp_action = menu.addAction(self.tr("Stamp..."))
        menu.addSeparator()
        export_action = menu.addAction(self.tr("Export Selected..."))
        menu.addSeparator()
        delete_action = menu.addAction(self.tr("Delete Document"))
        
        action = menu.exec(self.mapToGlobal(pos))
        
        if action == reprocess_action:
            self.reprocess_requested.emit(uuid)
        elif action == delete_action:
            # Emit for all selected? Or just focused?
            # Standard: if multiple selected, delete all.
            # But currently signal is 'delete_requested(str)'. 
            # I will just emit for the item right-clicked for now to avoid breaking interface signatue
            # OR iterate. MainWindow handles single uuid.
            # I'll stick to single delete via context menu for now, or emit multiple?
            # Let's emit for the focused one `uuid` (line 47).
            self.delete_requested.emit(uuid)
        elif merge_action and action == merge_action:
             # Gather UUIDs
             uuids = []
             for row in selected_rows:
                 u = self.item(row.row(), 0).data(Qt.ItemDataRole.UserRole)
                 if u: uuids.append(u)
             self.merge_requested.emit(uuids)
        elif action == tags_action:
             # Gather UUIDs
             uuids = []
             for row in selected_rows:
                 u = self.item(row.row(), 0).data(Qt.ItemDataRole.UserRole)
                 if u: uuids.append(u)
             if uuids:
                 self.tags_update_requested.emit(uuids)
        elif action == stamp_action:
            self.stamp_requested.emit(uuid)
        elif action == export_action:
            # Export all selected
            uuids = []
            for row in selected_rows:
                 u = self.item(row.row(), 0).data(Qt.ItemDataRole.UserRole)
                 if u: uuids.append(u)
            self.export_requested.emit(uuids)

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
        self.setSortingEnabled(False) # Disable during populate
        self.setRowCount(0) # Clear existing
        documents = self.db.get_all_documents()
        self.documents_cache = {doc.uuid: doc for doc in documents}
        
        self.setRowCount(len(documents))
        
        for row, doc in enumerate(documents):
            # Map Document fields to columns
            # ["Date", "Sender", "Type", "Tags", "Amount", "Filename"]
            
            date_str = str(doc.doc_date) if doc.doc_date else ""
            sender = doc.sender or ""
            doc_type = doc.doc_type or ""
            tags = doc.tags or ""
            amount_str = f"{doc.amount:.2f}" if doc.amount is not None else ""
            filename = doc.original_filename
            
            item_date = QTableWidgetItem(date_str)
            item_date.setData(Qt.ItemDataRole.UserRole, doc.uuid) # Store UUID
            
            self.setItem(row, 0, item_date)
            self.setItem(row, 1, QTableWidgetItem(sender))
            self.setItem(row, 2, QTableWidgetItem(doc_type))
            self.setItem(row, 3, QTableWidgetItem(tags))
            self.setItem(row, 4, QTableWidgetItem(amount_str))
            self.setItem(row, 5, QTableWidgetItem(filename))
            
        self.setSortingEnabled(True)
        
        # Re-apply filter if exists
        if self.current_filter:
            self.apply_filter(self.current_filter)

    def apply_filter(self, criteria: dict):
        """
        Filter rows based on criteria: 'date_from', 'date_to', 'type', 'tags'.
        """
        self.current_filter = criteria
        
        date_from = criteria.get('date_from')
        date_to = criteria.get('date_to')
        target_type = criteria.get('type')
        target_tags = criteria.get('tags')
        text_search = criteria.get('text_search')
        
        for row in range(self.rowCount()):
            show = True
            
            # Get UUID to lookup cache for text search
            uuid_item = self.item(row, 0)
            if not uuid_item: continue
            uuid = uuid_item.data(Qt.ItemDataRole.UserRole)
            doc = self.documents_cache.get(uuid)
            
            # Date Filter (Col 0)
            if date_from or date_to:
                date_item = self.item(row, 0)
                date_val = date_item.text() if date_item else ""
                
                if not date_val:
                    # Decide if docs with no date should be hidden?
                    # Generally yes if date range is specific.
                    show = False
                else:
                    # String comparison works for ISO dates
                    if date_from and date_val < date_from:
                        show = False
                    if date_to and date_val > date_to:
                        show = False
            
            # Type Filter (Col 2)
            if show and target_type:
                type_item = self.item(row, 2)
                type_val = type_item.text() if type_item else ""
                if target_type != type_val:
                    show = False
                    
            # Tag Filter (Col 3) - Contains
            if show and target_tags:
                tag_item = self.item(row, 3)
                tag_val = tag_item.text().lower() if tag_item else ""
                # Simple substring check
                if target_tags.lower() not in tag_val:
                    show = False

            # Text Search (Smart Search)
            if show and text_search and doc:
                query = text_search.lower()
                # Fields to search: Sender, Type, Tags, Filename, Address, Content?
                # Content might be huge. Let's include it for "Smart" search.
                
                haystack = [
                    doc.sender or "",
                    doc.doc_type or "",
                    doc.tags or "",
                    doc.original_filename or "",
                    doc.sender_address or "",
                    doc.text_content or ""
                ]
                
                # Check if query words are in haystack
                # Simple containment: query string in combined haystack
                full_text = " ".join(haystack).lower()
                if query not in full_text:
                    show = False
            
            self.setRowHidden(row, not show)
