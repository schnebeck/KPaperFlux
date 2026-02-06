import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QLineEdit, QTextEdit
from core.models.virtual import VirtualDocument as Document
from gui.metadata_editor import MetadataEditorWidget
from core.database import DatabaseManager
from core.models.semantic import SemanticExtraction, MetaHeader, AddressInfo, FinanceBody, MonetarySummation

@pytest.fixture
def mock_db():
    return MagicMock(spec=DatabaseManager)

@pytest.fixture
def editor(qtbot, mock_db):
    widget = MetadataEditorWidget(mock_db)
    qtbot.addWidget(widget)
    return widget

def test_display_documents_mixed(editor):
    doc1 = Document(
        uuid="1", 
        original_filename="a.pdf", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(sender=AddressInfo(name="Company A")),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("10.0"))
                )
            }
        )
    )
    doc2 = Document(
        uuid="2", 
        original_filename="b.pdf", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(sender=AddressInfo(name="Company B")),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("10.0"))
                )
            }
        )
    ) 
    
    docs = [doc1, doc2]
    editor.display_documents(docs)
    
    # Check Sender (Mixed)
    assert editor.sender_edit.text() == ""
    assert editor.sender_edit.placeholderText() == "<Multiple Values>"
    
def test_save_changes_batch(editor, mock_db):
    # Setup two documents with same metadata
    doc1 = Document(
        uuid="1", 
        original_filename="a.pdf", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(sender=AddressInfo(name="Company A")),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("10.0"))
                )
            }
        )
    )
    doc2 = Document(
        uuid="2", 
        original_filename="b.pdf", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(sender=AddressInfo(name="Company B")),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("10.0"))
                )
            }
        )
    )
    
    # We must patch self.doc in the editor because save_changes relies on it for merging
    editor.doc = doc1 
    editor.display_documents([doc1, doc2])
    
    # User edits SENDER (Mixed -> New Value)
    editor.sender_edit.setText("Common Sender")
    
    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()
    
    # Verify DB calls
    assert mock_db.update_document_metadata.call_count == 2
    
    # Check updates passed for first doc
    args, _ = mock_db.update_document_metadata.call_args_list[0]
    uuid, updates = args
    assert uuid == "1"
    # updates["semantic_data"] is now a SemanticExtraction object
    assert updates["semantic_data"].sender_summary == "Common Sender"


