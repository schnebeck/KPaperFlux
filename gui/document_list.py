from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QMenu
from PyQt6.QtCore import pyqtSignal, Qt, QPoint, QSettings, QLocale
from core.database import DatabaseManager
from gui.utils import format_date, format_datetime

class DocumentListWidget(QTableWidget):
    """
    Displays the list of documents from the database.
    """
    document_selected = pyqtSignal(list) # List[str] UUIDs
    delete_requested = pyqtSignal(str) # UUID
    reprocess_requested = pyqtSignal(list) # List[str] UUIDs (Changed from str)
    merge_requested = pyqtSignal(list) # List[str] UUIDs
    export_requested = pyqtSignal(list) # List[str] UUIDs
    stamp_requested = pyqtSignal(str) # UUID (Single for now, or list?) Let's support single for stamp simplicity.
    tags_update_requested = pyqtSignal(list) # List[str] UUIDs
    document_count_changed = pyqtSignal(int, int) # visible, total
    
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
            self.tr("Filename"),
            self.tr("Pages"),
            self.tr("Created"),
            self.tr("Updated")
        ]
        self.dynamic_columns = []
        
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)
        
        header = self.horizontalHeader()
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_header_menu)
        
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        
        self.itemSelectionChanged.connect(self._on_selection_changed)
        
        # Context Menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        # Restore State
        self.restore_state()
        
        # Enforce Resize Modes AFTER restore
        header = self.horizontalHeader()
        for i in range(len(self.columns)):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            
        header.setStretchLastSection(False)
        header.setCascadingSectionResizes(True) # Improve resizing UX

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
            
        # Separator
        menu.addSeparator()
        
        # Dynamic Columns Submenu
        dyn_menu = menu.addMenu(self.tr("Add JSON Column..."))
        
        available_keys = self.db.get_available_extra_keys()
        for key in available_keys:
             # Check if already added
             if key in self.dynamic_columns:
                 action = dyn_menu.addAction(f"✓ {key}")
                 action.setEnabled(False)
             else:
                 action = dyn_menu.addAction(key)
                 action.triggered.connect(lambda checked, k=key: self.add_dynamic_column(k))
                 
        # Remove Dynamic Column
        if self.dynamic_columns:
            rem_menu = menu.addMenu(self.tr("Remove JSON Column..."))
            for i, key in enumerate(self.dynamic_columns):
                action = rem_menu.addAction(key)
                action.triggered.connect(lambda checked, k=key: self.remove_dynamic_column(k))

        menu.exec(header.mapToGlobal(pos))
        
    def toggle_column(self, index: int, visible: bool):
        if visible:
            self.horizontalHeader().showSection(index)
        else:
            self.horizontalHeader().hideSection(index)
        self.save_state()

    def add_dynamic_column(self, key: str):
        if key in self.dynamic_columns:
            return
            
        self.dynamic_columns.append(key)
        self.columns.append(key) # Use key as header
        
        # reset table columns
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)
        
        self.refresh_list()
        self.save_state()
        
    def remove_dynamic_column(self, key: str):
        if key not in self.dynamic_columns:
            return
            
        idx = self.dynamic_columns.index(key)
        col_idx = len(self.columns) - len(self.dynamic_columns) + idx
        
        self.dynamic_columns.remove(key)
        self.columns.pop(col_idx)
        
        self.removeColumn(col_idx)
        self.setHorizontalHeaderLabels(self.columns)
        
        self.save_state()

    def save_state(self):
        settings = QSettings("KPaperFlux", "DocumentList")
        settings.setValue("headerState", self.horizontalHeader().saveState())
        settings.setValue("dynamicColumns", self.dynamic_columns)
        
    def restore_state(self):
        settings = QSettings("KPaperFlux", "DocumentList")
        
        # Restore dynamic columns first
        dyn_cols = settings.value("dynamicColumns", [])
        # Ensure it's a list (QSettings quirks)
        if isinstance(dyn_cols, str): dyn_cols = [dyn_cols]
        elif not isinstance(dyn_cols, list): dyn_cols = []
        
        if dyn_cols:
            self.dynamic_columns = dyn_cols
            self.columns.extend(dyn_cols)
            self.setColumnCount(len(self.columns))
            self.setHorizontalHeaderLabels(self.columns)

        state = settings.value("headerState")
        if state:
            self.horizontalHeader().restoreState(state)
        else:
            # Defaults: Hide Pages (6), Created (7)
            self.horizontalHeader().hideSection(6)
            self.horizontalHeader().hideSection(7)
            
        # Fix: Always ensure 'Updated' (8) is visible if newly added
        # This handles cases where old settings obscure the new column
        if self.horizontalHeader().isSectionHidden(8):
             self.horizontalHeader().showSection(8)

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
   
        reprocess_action = menu.addAction(self.tr("Reprocess / Re-Analyze"))
        tags_action = menu.addAction(self.tr("Manage Tags..."))
        stamp_action = menu.addAction(self.tr("Stamp..."))
        menu.addSeparator()
        export_action = menu.addAction(self.tr("Export Selected..."))
        menu.addSeparator()
        delete_action = menu.addAction(self.tr("Delete Document"))
        
        action = menu.exec(self.mapToGlobal(pos))
        
        if action == reprocess_action:
            # Gather UUIDs
            uuids = []
            if len(selected_rows) > 0:
                for row in selected_rows:
                     u = self.item(row.row(), 0).data(Qt.ItemDataRole.UserRole)
                     if u: uuids.append(u)
            else:
                 # Fallback to single item if selection model behaves oddly (right click sometimes selects only one)
                 uuids.append(uuid)
            
            self.reprocess_requested.emit(uuids)
            
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
        """Emit signal with selected UUID(s)."""
        selected_rows = self.selectionModel().selectedRows()
        if not selected_rows:
            self.document_selected.emit([])
            return
            
        uuids = []
        for row in selected_rows:
            uuid_item = self.item(row.row(), 0)
            if uuid_item:
                u = uuid_item.data(Qt.ItemDataRole.UserRole)
                if u: uuids.append(u)
        
        self.document_selected.emit(uuids)

    def refresh_list(self):
        """Fetch data from DB and populate table."""
        self.setSortingEnabled(False) # Disable during populate
        self.setRowCount(0) # Clear existing
        documents = self.db.get_all_documents()
        self.documents_cache = {doc.uuid: doc for doc in documents}
        
        self.setRowCount(len(documents))
        
        from datetime import datetime # Import local to avoid top-level clutter if not used elsewhere
        
        for row, doc in enumerate(documents):
            # Map Document fields to columns
            # ["Date", "Sender", "Type", "Tags", "Amount", "Filename", "Pages", "Created", "Updated"]
            
            locale = QLocale.system()
            
            # Localized Date (doc_date)
            date_str = format_date(doc.doc_date)

            sender = doc.sender or ""
            doc_type = doc.doc_type or ""
            tags = doc.tags or ""
            amount_str = locale.toString(float(doc.amount), 'f', 2) if doc.amount is not None else ""
            filename = doc.original_filename
            
            pages_str = str(doc.page_count) if doc.page_count is not None else ""
            created_str = format_datetime(doc.created_at)
            
            # Localized Updated (last_processed_at)
            updated_str = format_datetime(doc.last_processed_at)
            
            item_date = QTableWidgetItem(date_str)
            item_date.setData(Qt.ItemDataRole.UserRole, doc.uuid) # Store UUID
            
            self.setItem(row, 0, item_date)
            self.setItem(row, 1, QTableWidgetItem(sender))
            self.setItem(row, 2, QTableWidgetItem(doc_type))
            self.setItem(row, 3, QTableWidgetItem(tags))
            self.setItem(row, 4, QTableWidgetItem(amount_str))
            self.setItem(row, 5, QTableWidgetItem(filename))
            self.setItem(row, 6, QTableWidgetItem(pages_str))
            self.setItem(row, 7, QTableWidgetItem(created_str))
            self.setItem(row, 8, QTableWidgetItem(updated_str))
            
            # Dynamic Columns (Index 9+)
            for i, key in enumerate(self.dynamic_columns):
                # Resolve value path
                val = ""
                if doc.extra_data:
                    parts = key.split('.')
                    data = doc.extra_data
                    for p in parts:
                        if isinstance(data, dict):
                            data = data.get(p)
                        elif isinstance(data, list):
                            # List traversal: Try to find key in first dict item
                            if data and isinstance(data[0], dict):
                                data = data[0].get(p)
                            else:
                                data = None
                        else:
                            data = None
                        
                        if data is None: break
                    
                    if data is not None:
                        val = str(data)
                
                col_idx = 9 + i
                self.setItem(row, col_idx, QTableWidgetItem(val))
            
        self.setSortingEnabled(True)
        
        # Re-apply filter if exists
        if self.current_filter:
            self.apply_filter(self.current_filter)
        else:
             self.document_count_changed.emit(self.rowCount(), self.rowCount())

    def select_document(self, uuid: str):
        """Programmatically select a document by UUID."""
        if not uuid:
            return
            
        # Find row with this UUID
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == uuid:
                self.selectRow(row)
                self.scrollToItem(item)
                break

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
                    doc.text_content or "",
                    # Extended Logic (Phase 8)
                    doc.recipient_company or "",
                    doc.recipient_name or "",
                    doc.recipient_city or "",
                    doc.sender_company or "",
                    doc.sender_city or "",
                    str(doc.page_count or ""),
                    doc.created_at or ""
                ]
                
                # Check if query words are in haystack
                # Simple containment: query string in combined haystack
                full_text = " ".join(haystack).lower()
                if query not in full_text:
                    show = False
            
            self.setRowHidden(row, not show)

        # Count visible
        visible_count = 0
        for i in range(self.rowCount()):
            if not self.isRowHidden(i):
                visible_count += 1
                
        self.document_count_changed.emit(visible_count, self.rowCount())

    def get_selected_uuids(self) -> list[str]:
        """Return list of UUIDs for selected rows."""
        uuids = set()
        for item in self.selectedItems():
            row = item.row()
            uuid_item = self.item(row, 0)
            if uuid_item:
                uid = uuid_item.data(Qt.ItemDataRole.UserRole)
                if uid:
                    uuids.add(uid)
        return list(uuids)

    def select_rows_by_uuids(self, uuids: list[str]):
        """Select rows matching the given UUIDs."""
        self.clearSelection()
        if not uuids: 
            return
        
        uuid_set = set(uuids)
        
        # Check selection mode
        if self.selectionMode() == QTableWidget.SelectionMode.SingleSelection and len(uuids) > 1:
             # Only pick first if strictly single selection
             uuid_set = {uuids[0]}
             
        selection_model = self.selectionModel()
        
        for row in range(self.rowCount()):
             item = self.item(row, 0)
             if not item: continue
             
             uid = item.data(Qt.ItemDataRole.UserRole)
             if uid in uuid_set:
                 self.selectRow(row)
