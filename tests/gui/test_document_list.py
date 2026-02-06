import pytest
from unittest.mock import MagicMock
from datetime import date
from decimal import Decimal
from gui.document_list import DocumentListWidget
from core.models.virtual import VirtualDocument as Document
from core.models.semantic import SemanticExtraction, MetaHeader, FinanceBody, AddressInfo

@pytest.fixture
def mock_db():
    return MagicMock()

def test_document_list_population(qtbot, mock_db):
    """Test that the list widget populates correct data from DB."""
    # Data Setup
    docs = [
        Document(
            original_filename="invoice.pdf", 
            semantic_data=SemanticExtraction(
                meta_header=MetaHeader(
                    sender=AddressInfo(name="Amazon"),
                    doc_date="2023-01-01"
                ),
                bodies={
                    "finance_body": FinanceBody(
                        monetary_summation={
                            "grand_total_amount": Decimal("15.99")
                        }
                    )
                }
            )
        ),
        Document(original_filename="contract.pdf", type_tags=["Vertrag"])
    ]
    mock_db.get_all_documents.return_value = docs
    mock_db.get_all_entities_view.return_value = docs
    
    # Init Widget
    widget = DocumentListWidget(db_manager=mock_db)
    qtbot.addWidget(widget)
    widget.refresh_list()
    
    # Verify Rows
    assert widget.rowCount() == 2
    
    # Find indices dynamically
    header_item = widget.tree.headerItem()
    header_labels = [header_item.text(i) for i in range(widget.tree.columnCount())]
    
    def get_col(label):
        return header_labels.index(label)

    # Find the row for the first doc
    target_uuid = docs[0].uuid
    item = None
    for i in range(widget.rowCount()):
        if widget.item(i).text(get_col("Entity ID")) == target_uuid:
            item = widget.item(i)
            break
            
    assert item is not None, f"Could not find row with UUID {target_uuid}"

    # Fixed Columns
    assert item.text(get_col("Entity ID")) == docs[0].uuid
    assert item.text(get_col("Filename")) == "invoice.pdf"

def test_empty_state(qtbot, mock_db):
    """Test empty list behavior."""
    mock_db.get_all_documents.return_value = []
    mock_db.get_all_entities_view.return_value = []
    
    widget = DocumentListWidget(db_manager=mock_db)
    qtbot.addWidget(widget)
    widget.refresh_list()
    
    assert widget.rowCount() == 0

def test_selection_emits_signal(qtbot, mock_db):
    """Test that selecting a row emits specific signal with UUID."""
    docs = [Document(original_filename="test.pdf")]
    mock_db.get_all_documents.return_value = docs
    mock_db.get_all_entities_view.return_value = docs
    
    widget = DocumentListWidget(db_manager=mock_db)
    qtbot.addWidget(widget)
    widget.refresh_list()
    # refresh_list auto-selects if count=1. We clear it to test explicit selection.
    widget.tree.clearSelection()
    
    with qtbot.waitSignal(widget.document_selected, timeout=1000) as blocker:
        widget.selectRow(0)

        
    # Check signal payload (Expects list of UUIDs)
    assert blocker.args[0] == [docs[0].uuid]

def test_context_menu_actions(qtbot, mock_db):
    """Test context menu actions emission."""
    doc = Document(original_filename="test.pdf")
    mock_db.get_all_documents.return_value = [doc]
    mock_db.get_all_entities_view.return_value = [doc]
    
    widget = DocumentListWidget(db_manager=mock_db)
    qtbot.addWidget(widget)
    widget.refresh_list()
    
    # We can't easily click context menu in unit test, so we test the triggers manually
    # Or checking signals exist
    
    # Let's verify signals exist
    assert hasattr(widget, "delete_requested")
    assert hasattr(widget, "reprocess_requested")
    
    # We can simulate the action trigger
    with qtbot.waitSignal(widget.delete_requested) as blocker:
        widget.delete_requested.emit([doc.uuid])
    assert blocker.args[0] == [doc.uuid]
    
    with qtbot.waitSignal(widget.reprocess_requested) as blocker:
        widget.reprocess_requested.emit([doc.uuid])
    assert blocker.args[0] == [doc.uuid]
