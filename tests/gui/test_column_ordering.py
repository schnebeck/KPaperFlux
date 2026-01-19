
import pytest
from PyQt6.QtWidgets import QHeaderView, QTreeWidget
from PyQt6.QtCore import Qt
from gui.document_list import DocumentListWidget

@pytest.fixture
def doc_list(qapp):
    # Mock DB manager as None for UI test
    widget = DocumentListWidget(db_manager=None)
    widget.show()
    return widget

def test_header_properties(doc_list):
    """Verify header is configured for reordering."""
    header = doc_list.tree.header()
    
    # Check Movable
    assert header.sectionsMovable() == True, "Sections should be movable"
    
    # Check Clickable (implied by movable usually, but for sorting)
    assert header.sectionsClickable() == True, "Sections should be clickable"
    
    # Check Resize Mode
    # We expect Interactive
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Interactive, "Sections should be resizable interactively"
    
def test_header_state_restore(doc_list):
    """Verify that calling restore_state doesn't disable movability."""
    # Force state that might have movable=False?
    # QHeaderView.saveState() saves visual indices, visibility, sizes.
    # It does NOT save 'sectionsMovable'. 
    
    # Explicitly call restore (it's called in init, but let's call again)
    doc_list.restore_state()
    
    header = doc_list.tree.header()
    assert header.sectionsMovable() == True, "Sections should remain movable after restore"
    
def test_column_0_constrained(doc_list):
    """Verify that we try to keep visual index 0 for logical index 0."""
    # This involves the logic in open_column_manager_slot which we can't easily test without mocking the dialog execution.
    # But we can check the initial state.
    header = doc_list.tree.header()
    assert header.visualIndex(0) == 0, "Row Counter should be at start initially"
