
import pytest
import os
import tempfile
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from gui.document_list import DocumentListWidget
from gui.document_detail import DocumentDetailWidget
from gui.pdf_viewer import PdfViewerWidget
from core.database import DatabaseManager
from core.document import Document
from unittest.mock import MagicMock

# Ensure QApplication exists
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def mock_db():
    db = MagicMock(spec=DatabaseManager)
    db.get_all_documents.return_value = []
    return db

@pytest.fixture
def mock_vault():
    vault = MagicMock()
    return vault

def test_document_list_columns(qapp, mock_db):
    widget = DocumentListWidget(mock_db)
    # Check headers: Date, Sender, Type, Tags, Amount, Filename
    headers = [widget.horizontalHeaderItem(i).text() for i in range(widget.columnCount())]
    assert "Tags" in headers
    assert "Sender" in headers
    
    # Check sorting enabled
    assert widget.isSortingEnabled()

def test_pdf_viewer_load(qapp):
    viewer = PdfViewerWidget()
    # Loading non-existent file should be safe (handled in method)
    viewer.load_document("/non/existent/file.pdf")
    
    # Try creating real temp pdf (blank)
    import pikepdf
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        path = tmp.name
    
    try:
        with pikepdf.new() as pdf:
            pdf.add_blank_page()
            pdf.save(path)
            
        viewer.load_document(path)
        # Check document valid?
        # QPdfDocument status?
        assert viewer.document.status() in (viewer.document.Status.Ready, viewer.document.Status.Loading)
    
    finally:
        if os.path.exists(path):
            os.remove(path)

def test_detail_widget_display(qapp, mock_db, mock_vault):
    widget = DocumentDetailWidget(mock_db, mock_vault)
    
    doc = Document(
        uuid="test-uuid",
        original_filename="foo.pdf",
        sender="Test Sender",
        tags="tag1, tag2"
    )
    
    widget.display_document(doc)
    
    assert widget.sender_edit.text() == "Test Sender"
    assert widget.tags_edit.text() == "tag1, tag2"
    assert widget.uuid_lbl.text() == "test-uuid"
