
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel, QVBoxLayout, 
    QPushButton, QScrollArea, QMessageBox, QTabWidget
)
from PyQt6.QtCore import Qt
from core.document import Document
from core.database import DatabaseManager

class MetadataEditorWidget(QWidget):
    """
    Widget to edit document metadata with extended fields organized in tabs.
    """
    def __init__(self, db_manager: DatabaseManager = None):
        super().__init__()
        self.db_manager = db_manager
        self.current_uuid = None
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

        # Buttons
        self.btn_save = QPushButton(self.tr("Save Changes"))
        self.btn_save.clicked.connect(self.save_changes)
        layout.addWidget(self.btn_save)

    def display_document(self, doc: Document):
        """Populate fields."""
        self.doc = doc
        self.current_uuid = doc.uuid
        
        # General
        self.uuid_lbl.setText(doc.uuid)
        self.created_at_lbl.setText(doc.created_at or "-")
        self.page_count_lbl.setText(str(doc.page_count) if doc.page_count is not None else "-")
        self.sender_edit.setText(doc.sender or "")
        self.date_edit.setText(str(doc.doc_date) if doc.doc_date else "")
        self.amount_edit.setText(str(doc.amount) if doc.amount is not None else "")
        self.type_edit.setText(doc.doc_type or "")
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
        
    def clear(self):
        """Clear fields."""
        self.current_uuid = None
        self.doc = None
        
        # General
        self.uuid_lbl.clear()
        self.created_at_lbl.clear()
        self.page_count_lbl.clear()
        self.sender_edit.clear()
        self.date_edit.clear()
        self.amount_edit.clear()
        self.type_edit.clear()
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

    def save_changes(self):
        if not self.current_uuid or not self.db_manager:
            return
            
        # Collect updates
        updates = {
            "sender": self.sender_edit.text(),
            "doc_date": self.date_edit.text() if self.date_edit.text().strip() else None,
            "amount": self.amount_edit.text() if self.amount_edit.text().strip() else None,
            "doc_type": self.type_edit.text(),
            "iban": self.iban_edit.text(),
            "phone": self.phone_edit.text(),
            "tags": self.tags_edit.text(),
            
            "sender_company": self.sender_company_edit.text(),
            "sender_name": self.sender_name_edit.text(),
            "sender_street": self.sender_street_edit.text(),
            "sender_zip": self.sender_zip_edit.text(),
            "sender_city": self.sender_city_edit.text(),
            "sender_country": self.sender_country_edit.text(),
            "sender_address": self.sender_address_raw.toPlainText(),
            
            "recipient_company": self.recipient_company_edit.text(),
            "recipient_name": self.recipient_name_edit.text(),
            "recipient_street": self.recipient_street_edit.text(),
            "recipient_zip": self.recipient_zip_edit.text(),
            "recipient_city": self.recipient_city_edit.text(),
            "recipient_country": self.recipient_country_edit.text()
        }
        
        # We don't generally update created_at or page_count manually, but valid to exclude them.
        
        success = self.db_manager.update_document_metadata(self.current_uuid, updates)
        if success:
            QMessageBox.information(self, self.tr("Success"), self.tr("Metadata saved."))
        else:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Failed to save changes."))
