import pytest
import os
import shutil
import tempfile
import json
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager
from core.vault import DocumentVault
from core.filter_tree import NodeType

@pytest.fixture
def temp_env():
    # Setup temporary vault and database
    base = tempfile.mkdtemp()
    vault_path = os.path.join(base, "vault")
    db_path = os.path.join(base, "test.db")
    
    # Ensure directories exist
    os.makedirs(vault_path, exist_ok=True)
    
    # Initialize real pipeline
    pipeline = PipelineProcessor(base_path=vault_path, db_path=db_path)
    
    yield pipeline, vault_path, db_path
    
    # Cleanup
    shutil.rmtree(base)

def test_archive_preview_integration(qtbot, temp_env):
    pipeline, vault_path, db_path = temp_env
    
    # 1. Initialize MainWindow
    # Use real pipeline and DB
    window = MainWindow(pipeline=pipeline)
    qtbot.addWidget(window)
    window.show()
    
    # Ensure UI is ready
    qtbot.wait_exposed(window)
    
    # 2. Ingest a document
    # Path relative to project root
    test_pdf = Path("tests/resources/demo_invoices_complex/Demo_01_INVOICE_de.pdf")
    if not test_pdf.exists():
        # Fallback if running from within tests directory
        test_pdf = Path("../../tests/resources/demo_invoices_complex/Demo_01_INVOICE_de.pdf")
    
    assert test_pdf.exists(), f"Test PDF not found at {test_pdf.absolute()}"
    
    # Process document (Skip AI for speed)
    doc = pipeline.process_document(str(test_pdf), skip_ai=True)
    assert doc is not None
    uuid = doc.uuid
    
    # Force list refresh
    window.list_widget.refresh_list()
    assert window.list_widget.tree.topLevelItemCount() == 1
    
    # 3. Archive the document
    # We use the slot directly to simulate user action
    window.archive_document_slot([uuid], True)
    
    # Document should be gone from normal view
    window.list_widget.refresh_list()
    assert window.list_widget.tree.topLevelItemCount() == 0
    
    # 4. Filter for Archive
    # Select 'Archive' in combo (Internal nomenclature: NodeType.ARCHIVE)
    advanced_filter = window.advanced_filter
    archive_idx = -1
    for i in range(advanced_filter.combo_filters.count()):
        data = advanced_filter.combo_filters.itemData(i)
        if hasattr(data, 'node_type') and data.node_type == NodeType.ARCHIVE:
             archive_idx = i
             break
    
    assert archive_idx != -1, "Archive filter node not found in combo box"
    
    # Select Archive and click 'Laden'
    advanced_filter.combo_filters.setCurrentIndex(archive_idx)
    advanced_filter.btn_load.click()
    
    # Verify we are in archive mode
    assert window.list_widget.is_archive_mode is True
    # Document should reappear in archive view
    assert window.list_widget.tree.topLevelItemCount() == 1
    
    # 5. Check PDF Preview
    # Selection should have happened automatically due to force_select_first fix
    # Wait for any background processing/rendering
    qtbot.wait(2000) 
    
    # Verify PDF Viewer state
    assert window.pdf_viewer.current_uuid == uuid, "PDF Viewer should be loaded with archived doc UUID"
    
    # Debug: Check pages data
    print(f"DEBUG: PDF Viewer current_pages_data: {window.pdf_viewer.current_pages_data}")
    
    # Get canvas page count via internal proxy
    page_count = window.pdf_viewer.canvas.get_page_count()
    assert page_count > 0, f"PDF Canvas should have pages loaded, got {page_count}"
    
    # Final check: Is it actually showing something?
    # We check if canvas has a document (fitz doc)
    assert window.pdf_viewer.canvas.doc is not None, "Canvas should have a fitz document"
    print(f"DEBUG: PDF Canvas Loaded Doc: {window.pdf_viewer.canvas.doc}")
    
    # Check Pixmap
    pixmap = window.pdf_viewer.canvas.display_label.pixmap()
    assert pixmap is not None, "Display label should have a pixmap"
    assert not pixmap.isNull(), "Pixmap should not be null"
    print(f"DEBUG: Pixmap Size: {pixmap.width()}x{pixmap.height()}")
