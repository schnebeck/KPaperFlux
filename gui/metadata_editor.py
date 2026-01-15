
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel, QVBoxLayout, 
    QPushButton, QScrollArea, QMessageBox
)
from core.document import Document
from core.database import DatabaseManager

class MetadataEditorWidget(QWidget):
    """
    Widget to edit document metadata.
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
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_content = QWidget()
        self.form_layout = QFormLayout(form_content)
        
        # Fields
        self.uuid_lbl = QLabel()
        self.uuid_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.form_layout.addRow("UUID:", self.uuid_lbl)
        
        self.sender_edit = QLineEdit()
        self.form_layout.addRow(self.tr("Sender:"), self.sender_edit)
        
        self.address_edit = QTextEdit()
        self.address_edit.setMaximumHeight(80)
        self.form_layout.addRow(self.tr("Sender Address:"), self.address_edit)
        
        self.iban_edit = QLineEdit()
        self.form_layout.addRow(self.tr("IBAN:"), self.iban_edit)
        
        self.phone_edit = QLineEdit()
        self.form_layout.addRow(self.tr("Phone:"), self.phone_edit)
        
        self.date_edit = QLineEdit() 
        self.date_edit.setPlaceholderText("YYYY-MM-DD")
        self.form_layout.addRow(self.tr("Date:"), self.date_edit)
        
        self.amount_edit = QLineEdit()
        self.form_layout.addRow(self.tr("Amount:"), self.amount_edit)
        
        self.type_edit = QLineEdit()
        self.form_layout.addRow(self.tr("Type:"), self.type_edit)
        
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Tag1, Tag2...")
        self.form_layout.addRow(self.tr("Tags:"), self.tags_edit)
        
        scroll.setWidget(form_content)
        layout.addWidget(scroll)
        
        # Buttons
        self.btn_save = QPushButton(self.tr("Save Changes"))
        self.btn_save.clicked.connect(self.save_changes)
        layout.addWidget(self.btn_save)

    def display_document(self, doc: Document):
        """Populate fields."""
        self.doc = doc
        self.current_uuid = doc.uuid
        
        # Populate fields
        self.uuid_lbl.setText(doc.uuid)
        self.sender_edit.setText(doc.sender or "")
        self.address_edit.setPlainText(doc.sender_address or "")
        self.iban_edit.setText(doc.iban or "")
        self.phone_edit.setText(doc.phone or "")
        self.date_edit.setText(str(doc.doc_date) if doc.doc_date else "")
        self.amount_edit.setText(str(doc.amount) if doc.amount is not None else "")
        self.type_edit.setText(doc.doc_type or "")
        self.tags_edit.setText(doc.tags or "")
        
    def clear(self):
        """Clear fields."""
        self.current_uuid = None
        self.doc = None
        
        self.uuid_lbl.clear()
        self.sender_edit.clear()
        self.address_edit.clear()
        self.iban_edit.clear()
        self.phone_edit.clear()
        self.date_edit.clear()
        self.amount_edit.clear()
        self.type_edit.clear()
        self.tags_edit.clear()

    def save_changes(self):
        if not self.current_uuid or not self.db_manager:
            return
            
        # Collect updates
        updates = {
            "sender": self.sender_edit.text(),
            "sender_address": self.address_edit.toPlainText(),
            "iban": self.iban_edit.text(),
            "phone": self.phone_edit.text(),
            "doc_type": self.type_edit.text(),
            "tags": self.tags_edit.text(),
            "doc_date": self.date_edit.text() if self.date_edit.text().strip() else None,
            "amount": self.amount_edit.text() if self.amount_edit.text().strip() else None
        }
        
        success = self.db_manager.update_document_metadata(self.current_uuid, updates)
        if success:
            QMessageBox.information(self, self.tr("Success"), self.tr("Metadata saved."))
        else:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Failed to save changes."))
            
from PyQt6.QtCore import Qt
