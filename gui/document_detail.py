from PyQt6.QtWidgets import QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel, QVBoxLayout
from core.document import Document

class DocumentDetailWidget(QWidget):
    """
    Form view to display and edit document details.
    """
    def __init__(self):
        super().__init__()
        
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        
        # Form for metadata
        form_layout = QFormLayout()
        
        self.sender_edit = QLineEdit()
        self.sender_edit.setObjectName("sender_edit")
        form_layout.addRow(self.tr("Sender:"), self.sender_edit)
        
        self.amount_edit = QLineEdit()
        self.amount_edit.setObjectName("amount_edit")
        form_layout.addRow(self.tr("Amount:"), self.amount_edit)
        
        self.date_edit = QLineEdit()
        self.date_edit.setObjectName("date_edit")
        form_layout.addRow(self.tr("Date:"), self.date_edit)
        
        main_layout.addLayout(form_layout)
        
        # Text content area
        main_layout.addWidget(QLabel(self.tr("Text Content:")))
        self.text_content_edit = QTextEdit()
        self.text_content_edit.setObjectName("text_content_edit")
        self.text_content_edit.setReadOnly(True) 
        main_layout.addWidget(self.text_content_edit)

    def display_document(self, doc: Document):
        """Populate fields with document data."""
        self.sender_edit.setText(doc.sender or "")
        self.amount_edit.setText(str(doc.amount) if doc.amount is not None else "")
        self.date_edit.setText(str(doc.doc_date) if doc.doc_date else "")
        self.text_content_edit.setPlainText(doc.text_content or "")

    def clear_display(self):
        """Clear all fields."""
        self.sender_edit.clear()
        self.amount_edit.clear()
        self.date_edit.clear()
        self.text_content_edit.clear()
