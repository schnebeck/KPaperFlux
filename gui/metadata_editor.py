
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QMessageBox, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView
)
import json
from PyQt6.QtCore import Qt, pyqtSignal
from core.document import Document
from core.database import DatabaseManager
from gui.utils import format_date, format_datetime

class MetadataEditorWidget(QWidget):
    """
    Widget to edit document metadata with extended fields organized in tabs.
    """
    metadata_saved = pyqtSignal()

    def __init__(self, db_manager: DatabaseManager = None):
        super().__init__()
        self.db_manager = db_manager
        self.current_uuids = []
        self.mixed_fields = set()
        self.doc = None
        
        self._init_ui()
        
    def set_db_manager(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # --- Tab 1: General ---
        self.general_tab = QWidget()
        general_layout = QFormLayout(self.general_tab)
        
        self.uuid_lbl = QLabel()
        self.uuid_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        general_layout.addRow("UUID:", self.uuid_lbl)
        
        self.created_at_lbl = QLabel()
        general_layout.addRow(self.tr("Created At:"), self.created_at_lbl)
        
        self.updated_at_lbl = QLabel()
        general_layout.addRow(self.tr("Updated At:"), self.updated_at_lbl)
        
        self.page_count_lbl = QLabel()
        general_layout.addRow(self.tr("Pages:"), self.page_count_lbl)
        
        self.sender_edit = QLineEdit()
        general_layout.addRow(self.tr("Sender (Summary):"), self.sender_edit)
        
        self.date_edit = QLineEdit() 
        self.date_edit.setPlaceholderText("YYYY-MM-DD")
        general_layout.addRow(self.tr("Date:"), self.date_edit)
        
        self.amount_edit = QLineEdit()
        general_layout.addRow(self.tr("Amount:"), self.amount_edit)
        
        self.type_edit = QLineEdit()
        general_layout.addRow(self.tr("Type:"), self.type_edit)
        
        # Export Filename
        export_container = QWidget()
        export_layout = QHBoxLayout(export_container)
        export_layout.setContentsMargins(0, 0, 0, 0)
        self.export_filename_edit = QLineEdit()
        self.btn_regen_export = QPushButton("↺")
        self.btn_regen_export.setToolTip(self.tr("Regenerate Filename based on Sender/Type/Date"))
        self.btn_regen_export.clicked.connect(self.regenerate_export_filename)
        self.btn_regen_export.setFixedWidth(30)
        export_layout.addWidget(self.export_filename_edit)
        export_layout.addWidget(self.btn_regen_export)
        general_layout.addRow(self.tr("Export Filename:"), export_container)
        
        self.iban_edit = QLineEdit()
        general_layout.addRow(self.tr("IBAN:"), self.iban_edit)
        
        self.phone_edit = QLineEdit()
        general_layout.addRow(self.tr("Phone:"), self.phone_edit)
        
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Tag1, Tag2...")
        general_layout.addRow(self.tr("Tags:"), self.tags_edit)
        
        self.tab_widget.addTab(self.general_tab, self.tr("General"))
        
        # --- Tab 2: Sender Details ---
        self.sender_tab = QWidget()
        sender_layout = QFormLayout(self.sender_tab)
        
        self.sender_company_edit = QLineEdit()
        sender_layout.addRow(self.tr("Company:"), self.sender_company_edit)
        
        self.sender_name_edit = QLineEdit()
        sender_layout.addRow(self.tr("Name:"), self.sender_name_edit)
        
        self.sender_street_edit = QLineEdit()
        sender_layout.addRow(self.tr("Street:"), self.sender_street_edit)
        
        self.sender_zip_edit = QLineEdit()
        sender_layout.addRow(self.tr("ZIP:"), self.sender_zip_edit)
        
        self.sender_city_edit = QLineEdit()
        sender_layout.addRow(self.tr("City:"), self.sender_city_edit)
        
        self.sender_country_edit = QLineEdit()
        sender_layout.addRow(self.tr("Country:"), self.sender_country_edit)
        
        self.sender_address_raw = QTextEdit()
        self.sender_address_raw.setMaximumHeight(60)
        sender_layout.addRow(self.tr("Full Address (Raw):"), self.sender_address_raw)
        
        self.tab_widget.addTab(self.sender_tab, self.tr("Sender"))
        
        # --- Tab 3: Recipient Details ---
        self.recipient_tab = QWidget()
        recipient_layout = QFormLayout(self.recipient_tab)
        
        self.recipient_company_edit = QLineEdit()
        recipient_layout.addRow(self.tr("Company:"), self.recipient_company_edit)
        
        self.recipient_name_edit = QLineEdit()
        recipient_layout.addRow(self.tr("Name:"), self.recipient_name_edit)
        
        self.recipient_street_edit = QLineEdit()
        recipient_layout.addRow(self.tr("Street:"), self.recipient_street_edit)
        
        self.recipient_zip_edit = QLineEdit()
        recipient_layout.addRow(self.tr("ZIP:"), self.recipient_zip_edit)
        
        self.recipient_city_edit = QLineEdit()
        recipient_layout.addRow(self.tr("City:"), self.recipient_city_edit)
        
        self.recipient_country_edit = QLineEdit()
        recipient_layout.addRow(self.tr("Country:"), self.recipient_country_edit)

        self.tab_widget.addTab(self.recipient_tab, self.tr("Recipient"))
        
        # --- Tab 4: Extra JSON Data ---
        self.extra_tab = QWidget()
        extra_layout = QVBoxLayout(self.extra_tab)
        
        self.extra_table = QTableWidget()
        self.extra_table.setColumnCount(2)
        self.extra_table.setHorizontalHeaderLabels([self.tr("Key"), self.tr("Value")])
        self.extra_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.extra_table.setAlternatingRowColors(True)
        
        # Toolbar for adding keys?
        extra_tools = QHBoxLayout()
        self.btn_add_key = QPushButton("+")
        self.btn_add_key.setToolTip(self.tr("Add new field"))
        self.btn_add_key.clicked.connect(self.add_extra_field)
        self.btn_remove_key = QPushButton("-")
        self.btn_remove_key.setToolTip(self.tr("Remove selected field"))
        self.btn_remove_key.clicked.connect(self.remove_extra_field)
        
        extra_tools.addWidget(self.btn_add_key)
        extra_tools.addWidget(self.btn_remove_key)
        extra_tools.addStretch()
        
        extra_layout.addLayout(extra_tools)
        extra_layout.addWidget(self.extra_table)
        
        self.tab_widget.addTab(self.extra_tab, self.tr("Extra Data"))

        # Buttons
        self.btn_save = QPushButton(self.tr("Save Changes"))
        self.btn_save.clicked.connect(self.save_changes)
        layout.addWidget(self.btn_save)

    def display_documents(self, docs: list[Document]):
        """Populate fields for multiple documents."""
        self.doc = None # Single doc reference invalid
        self.current_uuids = [d.uuid for d in docs]
        
        if not docs:
            self.clear()
            return
            
        if len(docs) == 1:
            self.display_document(docs[0])
            return

        # Batch Display
        # Determine common values
        
        # Fields mapping: attr -> widget
        fields = {
            "sender": self.sender_edit,
            "doc_date": self.date_edit,
            "amount": self.amount_edit,
            "doc_type": self.type_edit,
            "export_filename": self.export_filename_edit,
            "iban": self.iban_edit,
            "phone": self.phone_edit,
            "tags": self.tags_edit,
            
            "sender_company": self.sender_company_edit,
            "sender_name": self.sender_name_edit,
            "sender_street": self.sender_street_edit,
            "sender_zip": self.sender_zip_edit,
            "sender_city": self.sender_city_edit,
            "sender_country": self.sender_country_edit,
            "sender_address": self.sender_address_raw,
            
            "recipient_company": self.recipient_company_edit,
            "recipient_name": self.recipient_name_edit,
            "recipient_street": self.recipient_street_edit,
            "recipient_zip": self.recipient_zip_edit,
            "recipient_city": self.recipient_city_edit,
            "recipient_country": self.recipient_country_edit
        }
        
        # Store initial state to detect mixed fields
        self.mixed_fields = set()
        
        for attr, widget in fields.items():
            values = set()
            for d in docs:
                val = getattr(d, attr)
                # Normalize: None -> "" or stringify
                if val is None: val = ""
                else: val = str(val)
                values.add(val)
            
            if len(values) == 1:
                # All same
                val = values.pop()
                if isinstance(widget, QLineEdit): widget.setText(val)
                elif isinstance(widget, QTextEdit): widget.setPlainText(val)
                widget.setPlaceholderText("")
            else:
                # Mixed
                self.mixed_fields.add(attr)
                if isinstance(widget, QLineEdit): 
                    widget.clear()
                    widget.setPlaceholderText("<Multiple Values>")
                elif isinstance(widget, QTextEdit): 
                    widget.clear()
                    widget.setPlaceholderText("<Multiple Values>")

        # Info Labels (Special handling)
        self.uuid_lbl.setText("<Multiple Selected>")
        self.created_at_lbl.setText("-")
        self.updated_at_lbl.setText("-")
        # Sum pages? Or range?
        pages = sum((d.page_count or 0) for d in docs)
        self.page_count_lbl.setText(f"Total: {pages}")
        
        # Extra Data - Batch editing not easily supported yet
        self.extra_table.setRowCount(0)
        # Maybe show common keys? For now clear to avoid confusion.

    def display_document(self, doc: Document):
        """Populate fields for single document."""
        self.current_uuids = [doc.uuid]
        self.mixed_fields = set() # No mixed fields
        self.doc = doc
        
        # Reset Placeholders
        self._reset_placeholders()

        # General
        self.uuid_lbl.setText(doc.uuid)
        self.created_at_lbl.setText(format_datetime(doc.created_at) or "-")
        self.updated_at_lbl.setText(format_datetime(doc.last_processed_at) or "-")
        
        self.page_count_lbl.setText(str(doc.page_count) if doc.page_count is not None else "-")
        self.sender_edit.setText(doc.sender or "")
        self.date_edit.setText(str(doc.doc_date) if doc.doc_date else "")
        self.amount_edit.setText(str(doc.amount) if doc.amount is not None else "")
        self.type_edit.setText(doc.doc_type or "")
        self.export_filename_edit.setText(doc.export_filename or "")
        self.iban_edit.setText(doc.iban or "")
        self.phone_edit.setText(doc.phone or "")
        self.tags_edit.setText(doc.tags or "")
        
        # Sender
        self.sender_company_edit.setText(doc.sender_company or "")
        self.sender_name_edit.setText(doc.sender_name or "")
        self.sender_street_edit.setText(doc.sender_street or "")
        self.sender_zip_edit.setText(doc.sender_zip or "")
        self.sender_city_edit.setText(doc.sender_city or "")
        self.sender_country_edit.setText(doc.sender_country or "")
        self.sender_address_raw.setPlainText(doc.sender_address or "")
        
        # Recipient
        self.recipient_company_edit.setText(doc.recipient_company or "")
        self.recipient_name_edit.setText(doc.recipient_name or "")
        self.recipient_street_edit.setText(doc.recipient_street or "")
        self.recipient_zip_edit.setText(doc.recipient_zip or "")
        self.recipient_city_edit.setText(doc.recipient_city or "")
        self.recipient_country_edit.setText(doc.recipient_country or "")
        
        # Extra Data
        self.extra_table.setRowCount(0)
        self.extra_table.setSortingEnabled(False)
        if doc.extra_data:
            for k, v in doc.extra_data.items():
                row = self.extra_table.rowCount()
                self.extra_table.insertRow(row)
                
                # Format value
                val_str = ""
                if isinstance(v, (dict, list)):
                    try:
                        val_str = json.dumps(v, ensure_ascii=False)
                    except:
                        val_str = str(v)
                else:
                    val_str = str(v)
                    
                self.extra_table.setItem(row, 0, QTableWidgetItem(k))
                self.extra_table.setItem(row, 1, QTableWidgetItem(val_str))
        self.extra_table.setSortingEnabled(True)
        
    def _reset_placeholders(self):
        """Reset standard placeholders."""
        self.date_edit.setPlaceholderText("YYYY-MM-DD")
        self.tags_edit.setPlaceholderText("Tag1, Tag2...")
        self.sender_edit.setPlaceholderText("")
        self.amount_edit.setPlaceholderText("") # etc.
        # Ideally iterate all and clear

    def clear(self):
        """Clear fields."""
        self.current_uuids = []
        self.doc = None
        self.mixed_fields = set()
        
        # General
        self.uuid_lbl.clear()
        self.created_at_lbl.clear()
        self.updated_at_lbl.clear()
        self.page_count_lbl.clear()
        self.sender_edit.clear()
        self.date_edit.clear()
        self.amount_edit.clear()
        self.type_edit.clear()
        self.export_filename_edit.clear()
        self.iban_edit.clear()
        self.phone_edit.clear()
        self.tags_edit.clear()
        
        # Sender
        self.sender_company_edit.clear()
        self.sender_name_edit.clear()
        self.sender_street_edit.clear()
        self.sender_zip_edit.clear()
        self.sender_city_edit.clear()
        self.sender_country_edit.clear()
        self.sender_address_raw.clear()
        
        # Recipient
        self.recipient_company_edit.clear()
        self.recipient_name_edit.clear()
        self.recipient_street_edit.clear()
        self.recipient_zip_edit.clear()
        self.recipient_city_edit.clear()
        self.recipient_country_edit.clear()
        
        self.extra_table.setRowCount(0)
        
        self._reset_placeholders()

    def save_changes(self):
        if not self.current_uuids or not self.db_manager:
            return
            
        # Collect updates
        # Need to know which fields to update.
        # Map: attr -> widget
        fields = {
            "sender": self.sender_edit,
            "doc_date": self.date_edit,
            "amount": self.amount_edit,
            "doc_type": self.type_edit,
            "export_filename": self.export_filename_edit,
            "iban": self.iban_edit,
            "phone": self.phone_edit,
            "tags": self.tags_edit,
            
            "sender_company": self.sender_company_edit,
            "sender_name": self.sender_name_edit,
            "sender_street": self.sender_street_edit,
            "sender_zip": self.sender_zip_edit,
            "sender_city": self.sender_city_edit,
            "sender_country": self.sender_country_edit,
            "sender_address": self.sender_address_raw,
            
            "recipient_company": self.recipient_company_edit,
            "recipient_name": self.recipient_name_edit,
            "recipient_street": self.recipient_street_edit,
            "recipient_zip": self.recipient_zip_edit,
            "recipient_city": self.recipient_city_edit,
            "recipient_country": self.recipient_country_edit
        }
        
        updates = {}
        
        for attr, widget in fields.items():
            if isinstance(widget, QLineEdit):
                text = widget.text().strip()
            elif isinstance(widget, QTextEdit):
                text = widget.toPlainText().strip()
                
            # Logic:
            # 1. If field was mixed (in self.mixed_fields):
            #    - Update ONLY if text is NOT empty.
            # 2. If field was common (not in mixed):
            #    - Update always (even if empty, meaning user cleared it).
            
            if attr in self.mixed_fields:
                if text: # User entered something
                    # Special case for Amount/Date conversion logic?
                    # The update_document_metadata handles conversion if passed as string?
                    # Actually update_document_metadata expects primitives usually?
                    # Let's clean it up.
                    if text == "<Multiple Values>": continue # Should not happen if cleared/placeholder
                    updates[attr] = text
            else:
                # Common value. Update to text (empty or not).
                updates[attr] = text if text else None
                
        # Clean up specific types based on model needs (Date, Amount)
        # Assuming db_manager.update_document_metadata handles string->type conversion?
        # Let's check update_document_metadata implementation or handle here.
        # It's safer to handle here or trust manager. 
        # For efficiency, let's assume strings are passed and manager/model handles it 
        # OR we need to be careful.
        
        # Actually `update_document_metadata` iterates keys and setattr.
        # Document (Pydantic) will coerce types? Yes, if valid.
        # But text "" for Date might fail.
        
        if "amount" in updates and updates["amount"] == "": updates["amount"] = None
        if "doc_date" in updates and updates["doc_date"] == "": updates["doc_date"] = None
        
        # Extra Data (Only for single doc mode)
        if len(self.current_uuids) == 1:
            new_extra = {}
            for row in range(self.extra_table.rowCount()):
                key_item = self.extra_table.item(row, 0)
                val_item = self.extra_table.item(row, 1)
                if key_item and key_item.text().strip():
                     key = key_item.text().strip()
                     val_raw = val_item.text().strip() if val_item else ""
                     
                     # Try to parse JSON value
                     try:
                         val = json.loads(val_raw)
                     except:
                         val = val_raw
                     new_extra[key] = val
            updates["extra_data"] = new_extra

        count = 0
        for uuid in self.current_uuids:
             if self.db_manager.update_document_metadata(uuid, updates):
                 count += 1
                 
        if count > 0:
            QMessageBox.information(self, self.tr("Success"), self.tr(f"Metadata saved for {count} documents."))
            self.metadata_saved.emit()
        else:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Failed to save changes."))

    def regenerate_export_filename(self):
        import re
        # Gather data from widgets
        sender = self.sender_company_edit.text() or self.sender_name_edit.text() or self.sender_edit.text() or "Unknown"
        doc_type = self.type_edit.text() or "Document"
        date_part = self.date_edit.text() or "UnknownDate"
        
        def clean(s):
             s = str(s).strip()
             s = re.sub(r'[^\w\s-]', '', s)
             s = re.sub(r'[\s]+', '_', s)
             return s
             
        base = f"{clean(sender)}_{clean(doc_type)}_{clean(date_part)}"
        self.export_filename_edit.setText(base)

    def add_extra_field(self):
        row = self.extra_table.rowCount()
        self.extra_table.insertRow(row)
        self.extra_table.setItem(row, 0, QTableWidgetItem("new_key"))
        self.extra_table.setItem(row, 1, QTableWidgetItem(""))
        
    def remove_extra_field(self):
        row = self.extra_table.currentRow()
        if row >= 0:
            self.extra_table.removeRow(row)
