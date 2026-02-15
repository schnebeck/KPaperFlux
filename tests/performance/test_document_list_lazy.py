import pytest
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from gui.document_list import DocumentListWidget
from core.models.virtual import VirtualDocument
from unittest.mock import MagicMock

@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])

@pytest.fixture
def document_list(qtbot):
    widget = DocumentListWidget(db_manager=MagicMock())
    qtbot.addWidget(widget)
    return widget

def generate_dummy_docs(count):
    docs = []
    for i in range(count):
        doc = VirtualDocument(uuid=f"uuid-{i}")
        doc.original_filename = f"Document {i}.pdf"
        doc.status = "PROCESSED"
        doc.page_count = 1
        docs.append(doc)
    return docs

def test_populate_performance_large_dataset(qtbot, document_list):
    """
    Measure time to populate list with 5000 documents.
    We want this to be near-instant (under 500ms) for initial view via lazy loading.
    """
    large_docs = generate_dummy_docs(5000)
    
    start_time = time.time()
    document_list.populate_tree(large_docs)
    end_time = time.time()
    
    duration = end_time - start_time
    print(f"\nPopulation of 5000 items took: {duration:.4f}s")
    
    # In item-based QTreeWidget, 5000 items usually take > 1-2 seconds.
    # We want to fail this if it's too slow, forcing us to implement lazy loading.
    assert duration < 0.5, f"Initial population too slow: {duration:.4f}s"

def test_lazy_loading_scrolling(qtbot, document_list):
    """
    Verify that scrolling to the bottom loads more items.
    """
    document_list.resize(800, 600)
    document_list.show()
    qtbot.waitExposed(document_list)

    large_docs = generate_dummy_docs(1000)
    document_list.populate_tree(large_docs)
    
    # Initially 100
    assert document_list.tree.topLevelItemCount() == 100
    
    # Force process events to update scrollbars
    QApplication.processEvents()
    
    # Simulate scroll to bottom
    vbar = document_list.tree.verticalScrollBar()
    print(f"DEBUG: Scrollbar max: {vbar.maximum()}")
    
    # If maximum is 0, it means 100 items fit? Unlikely for 600px height.
    # But let's just trigger the scroll logic manually if needed or set a small size.
    document_list.resize(800, 200) 
    QApplication.processEvents()
    
    vbar.setValue(vbar.maximum())
    QApplication.processEvents()
    
    # QtBot wait to be safe
    qtbot.wait(200)
    
    # Now should be 200
    assert document_list.tree.topLevelItemCount() == 200
