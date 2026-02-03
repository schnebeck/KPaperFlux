
import pytest
import os
import tempfile
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from gui.document_list import DocumentListWidget
from gui.pdf_viewer import PdfViewerWidget
from core.database import DatabaseManager
from core.models.virtual import VirtualDocument as Document
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
    headers = [widget.tree.headerItem().text(i) for i in range(widget.tree.columnCount())]
    
    # Verify System Columns (Fixed)
    for label in widget.FIXED_COLUMNS.values():
        assert label in headers
    
    # Verify Dynamic Semantic Columns (Defaults)
    for key in widget.dynamic_columns:
        expected_label = widget.SEMANTIC_LABELS.get(key, key)
        assert expected_label in headers
    
    # Check sorting enabled
    assert widget.tree.isSortingEnabled()

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

