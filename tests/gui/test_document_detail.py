import pytest
from PyQt6.QtWidgets import QLineEdit, QTextEdit
from core.document import Document
from gui.document_detail import DocumentDetailWidget
from decimal import Decimal
from datetime import date

def test_detail_widget_display(qtbot):
    """Test that the widget displays document details."""
    widget = DocumentDetailWidget()
    qtbot.addWidget(widget)
    
    doc = Document(
        original_filename="invoice.pdf",
        sender="Amazon",
        amount=Decimal("19.99"),
        doc_date=date(2023, 10, 1),
        text_content="Receipt content..."
    )
    
    widget.display_document(doc)
    
    # Assert Sender
    sender_edit = widget.findChild(QLineEdit, "sender_edit")
    assert sender_edit.text() == "Amazon"
    
    # Assert Amount
    amount_edit = widget.findChild(QLineEdit, "amount_edit")
    assert amount_edit.text() == "19.99"
    
    # Assert Text Content
    text_edit = widget.findChild(QTextEdit, "text_content_edit")
    assert "Receipt content" in text_edit.toPlainText()

def test_detail_widget_clear(qtbot):
    """Test clearing the widget."""
    widget = DocumentDetailWidget()
    qtbot.addWidget(widget)
    
    doc = Document(original_filename="test.pdf", sender="Foo")
    widget.display_document(doc)
    
    widget.clear_display()
    
    sender_edit = widget.findChild(QLineEdit, "sender_edit")
    assert sender_edit.text() == ""
