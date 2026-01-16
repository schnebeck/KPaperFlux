
import pytest
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QLineEdit, QTextEdit
from core.document import Document
from gui.metadata_editor import MetadataEditorWidget
from core.database import DatabaseManager

@pytest.fixture
def mock_db():
    return MagicMock(spec=DatabaseManager)

@pytest.fixture
def editor(qtbot, mock_db):
    widget = MetadataEditorWidget(mock_db)
    qtbot.addWidget(widget)
    return widget

def test_display_documents_mixed(editor):
    doc1 = Document(uuid="1", original_filename="a.pdf", sender="Amazon", amount=10.0)
    doc2 = Document(uuid="2", original_filename="b.pdf", sender="Google", amount=10.0) # Different Sender, Same Amount
    
    docs = [doc1, doc2]
    editor.display_documents(docs)
    
    # Check Sender (Mixed)
    assert editor.sender_edit.text() == ""
    assert editor.sender_edit.placeholderText() == "<Multiple Values>"
    assert "sender" in editor.mixed_fields
    
    # Check Amount (Same)
    assert editor.amount_edit.text() == "10.0"
    assert editor.amount_edit.placeholderText() == ""
    assert "amount" not in editor.mixed_fields

def test_save_changes_batch(editor, mock_db):
    doc1 = Document(uuid="1", original_filename="a.pdf", sender="Amazon", amount=10.0)
    doc2 = Document(uuid="2", original_filename="b.pdf", sender="Google", amount=10.0)
    editor.display_documents([doc1, doc2])
    
    # User edits SENDER (Mixed -> New Value)
    editor.sender_edit.setText("Common Sender")
    
    # User leaves Amount (Common) alone
    # User leaves Date (Mixed/Empty) alone
    
    with patch("gui.metadata_editor.QMessageBox"):
        editor.save_changes()
    
    # Verify DB calls
    # Should update BOTH documents
    assert mock_db.update_document_metadata.call_count == 2
    
    # Check updates passed
    # Call 1 (UUID 1)
    args, _ = mock_db.update_document_metadata.call_args_list[0]
    uuid, updates = args
    assert uuid == "1"
    assert updates["sender"] == "Common Sender"
    assert updates["amount"] == "10.0" # Common val re-saved
    
    # Call 2 (UUID 2)
    args2, _ = mock_db.update_document_metadata.call_args_list[1]
    uuid2, updates2 = args2
    assert uuid2 == "2"
    assert updates2["sender"] == "Common Sender"

def test_save_changes_partial(editor, mock_db):
    # Mixed field left EMPTY -> Should NOT update
    doc1 = Document(uuid="1", original_filename="a.pdf", sender="A")
    doc2 = Document(uuid="2", original_filename="b.pdf", sender="B")
    editor.display_documents([doc1, doc2])
    
    # Precondition
    assert editor.sender_edit.text() == ""
    assert "sender" in editor.mixed_fields
    
    with patch("gui.metadata_editor.QMessageBox"):
         editor.save_changes()
    
    args, _ = mock_db.update_document_metadata.call_args_list[0]
    uuid, updates = args
    
    # Sender should NOT be in updates because it was mixed and left empty
    assert "sender" not in updates
    # Handler logic
    pass

def test_display_documents_date_string_conversion(editor):
    """Regression test: Ensure string dates in Document don't crash QDateEdit."""
    from PyQt6.QtCore import QDate
    
    # Document stores date as string (JSON serialization).
    doc1 = Document(uuid="1", original_filename="a.pdf")
    doc1.doc_date = "2025-01-01" # String format
    
    editor.display_documents([doc1])
    
    # Check if set correctly specific to QDate(2025, 1, 1)
    assert editor.date_edit.date() == QDate(2025, 1, 1)
