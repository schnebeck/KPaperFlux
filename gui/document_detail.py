
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel, QVBoxLayout, QHBoxLayout, 
    QPushButton, QScrollArea, QMessageBox
)
from PyQt6.QtCore import Qt
from core.models.virtual import VirtualDocument
from core.database import DatabaseManager
from core.document import Document
from core.vault import DocumentVault
from gui.pdf_viewer import PdfViewerWidget
from gui.widgets.tag_input import TagInputWidget
from gui.utils import show_selectable_message_box, show_notification
from decimal import Decimal

class DocumentDetailWidget(QWidget):

    """
    Split view: PDF Viewer (Left) + Editable Metadata Form (Right).
    """
    def __init__(self, db_manager: DatabaseManager = None, vault: DocumentVault = None):
        super().__init__()
        self.db_manager = db_manager
        self.vault = vault
        self.current_uuid = None
        self.doc = None
        self._locked_for_load = False
        
        self._init_ui()
        
    def set_dependencies(self, db_manager: DatabaseManager, vault: DocumentVault):
        self.db_manager = db_manager
        self.vault = vault

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        
        # Left: PDF Viewer
        self.pdf_viewer = PdfViewerWidget()
        main_layout.addWidget(self.pdf_viewer, stretch=60)
        
        # Right: Metadata Form
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_content = QWidget()
        self.form_layout = QFormLayout(form_content)
        
        # Fields
        self.uuid_lbl = QLabel()
        self.uuid_lbl.setObjectName("uuid_lbl")
        self.form_layout.addRow("UUID:", self.uuid_lbl)
        
        self.sender_edit = QLineEdit()
        self.sender_edit.setObjectName("sender_edit")
        self.form_layout.addRow(self.tr("Sender:"), self.sender_edit)
        
        self.address_edit = QTextEdit()
        self.address_edit.setObjectName("address_edit")
        self.address_edit.setMaximumHeight(80)
        self.form_layout.addRow(self.tr("Sender Address:"), self.address_edit)
        
        self.iban_edit = QLineEdit()
        self.iban_edit.setObjectName("iban_edit")
        self.form_layout.addRow(self.tr("IBAN:"), self.iban_edit)
        
        self.phone_edit = QLineEdit()
        self.phone_edit.setObjectName("phone_edit")
        self.form_layout.addRow(self.tr("Phone:"), self.phone_edit)
        
        self.date_edit = QLineEdit() 
        self.date_edit.setObjectName("date_edit")
        self.date_edit.setPlaceholderText("YYYY-MM-DD")
        self.form_layout.addRow(self.tr("Date:"), self.date_edit)
        
        self.type_edit = QLineEdit()
        self.type_edit.setObjectName("type_edit")
        self.form_layout.addRow(self.tr("Type:"), self.type_edit)
        
        self.tags_edit = TagInputWidget()
        self.tags_edit.setObjectName("tags_edit")
        self.form_layout.addRow(self.tr("Tags:"), self.tags_edit)
        
        scroll.setWidget(form_content)
        right_layout.addWidget(scroll)
        
        # Buttons
        self.btn_save = QPushButton(self.tr("Save Changes"))
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_save.setEnabled(False) # Default disabled
        right_layout.addWidget(self.btn_save)

        # Connect Change Signals
        self.sender_edit.textChanged.connect(self._mark_dirty)
        self.address_edit.textChanged.connect(self._mark_dirty)
        self.iban_edit.textChanged.connect(self._mark_dirty)
        self.phone_edit.textChanged.connect(self._mark_dirty)
        self.date_edit.textChanged.connect(self._mark_dirty)
        self.type_edit.textChanged.connect(self._mark_dirty)
        self.tags_edit.tagsChanged.connect(self._mark_dirty)

    def _mark_dirty(self):
        if getattr(self, "_locked_for_load", False):
            return
        self.btn_save.setEnabled(True)
        self.btn_save.setStyleSheet("background-color: #e8f5e9; font-weight: bold; border: 1px solid #c8e6c9;")

    def _reset_dirty(self):
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet("")
        
        main_layout.addWidget(right_widget, stretch=40)

    def display_document(self, doc: Document):
        """Populate fields and load PDF."""
        self._locked_for_load = True
        self.doc = doc
        self.current_uuid = doc.uuid
        
        # Populate fields
        sd = doc.semantic_data or {}
        self.uuid_lbl.setText(doc.uuid)
        self.sender_edit.setText(sd.get("sender", ""))
        self.address_edit.setPlainText(doc.sender_address or "")
        self.iban_edit.setText(doc.iban or "")
        self.phone_edit.setText(doc.phone or "")
        self.date_edit.setText(str(sd.get("doc_date") or ""))
        self.type_edit.setText(doc.doc_type or "")
        # Tags: Handle List or legacy String
        tags = doc.tags or []
        if isinstance(tags, list):
            self.tags_edit.setTags(tags)
        else:
            # Fallback for old CSV strings
            self.tags_edit.setText(str(tags))
        
        # Load PDF
        if self.vault:
            path = self.vault.get_file_path(doc.uuid)
            if path:
                self.pdf_viewer.load_document(path)
            else:
                self.pdf_viewer.clear()
        
        self._reset_dirty()
        self._locked_for_load = False
        
    def clear_display(self):
        """Clear all."""
        self.current_uuid = None
        self.doc = None
        
        self.uuid_lbl.clear()
        self.sender_edit.clear()
        self.address_edit.clear()
        self.iban_edit.clear()
        self.phone_edit.clear()
        self.date_edit.clear()
        self.type_edit.clear()
        self.tags_edit.clear()
        self.pdf_viewer.clear()

    def save_changes(self):
        if not self.current_uuid or not self.db_manager:
            return
            
        # Collect updates
        sd = self.doc.semantic_data or {}
        sd["sender"] = self.sender_edit.text()
        sd["doc_date"] = self.date_edit.text() if self.date_edit.text().strip() else None
        
        updates = {
            "sender_address": self.address_edit.toPlainText(),
            "iban": self.iban_edit.text(),
            "phone": self.phone_edit.text(),
            "doc_type": self.type_edit.text(),
            "tags": self.tags_edit.getTags(),
            "semantic_data": sd
        }
        
        # Basic validation for Amount (ensure float-compat or let DB/Model handle?)
        # Better: Try parsing amount to ensure validity but store as string/decimal?
        # DatabaseManager expects string/float values for query.
        
        success = self.db_manager.update_document_metadata(self.current_uuid, updates)
        if success:
            self._reset_dirty()
            show_notification(self, self.tr("Success"), self.tr("Metadata saved."))
        else:
            show_selectable_message_box(self, self.tr("Error"), self.tr("Failed to save changes."), icon=QMessageBox.Icon.Warning)
