import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from gui.widgets.splitter_strip import SplitterStripWidget, PageThumbnailWidget, SplitDividerWidget

@pytest.fixture
def splitter(qtbot):
    widget = SplitterStripWidget()
    qtbot.addWidget(widget)
    # Mock some data
    pages = [
        {"file_uuid": "F1", "page": 1, "rotation": 0},
        {"file_uuid": "F1", "page": 2, "rotation": 0},
        {"file_uuid": "F1", "page": 3, "rotation": 0},
        {"file_uuid": "F1", "page": 4, "rotation": 0}
    ]
    widget._populate_strip(pages)
    return widget

def test_selection_logic(splitter, qtbot):
    thumbs = [w for w in splitter.findChildren(PageThumbnailWidget)]
    assert len(thumbs) == 4
    
    # Single selection
    splitter.on_selection_requested(thumbs[0], Qt.KeyboardModifier.NoModifier)
    assert thumbs[0].is_selected
    assert not thumbs[1].is_selected
    
    # Ctrl selection
    splitter.on_selection_requested(thumbs[1], Qt.KeyboardModifier.ControlModifier)
    assert thumbs[0].is_selected
    assert thumbs[1].is_selected
    
    # Shift selection (from 1 to 3)
    splitter.last_selected_widget = thumbs[0]
    splitter.on_selection_requested(thumbs[2], Qt.KeyboardModifier.ShiftModifier)
    assert thumbs[0].is_selected
    assert thumbs[1].is_selected
    assert thumbs[2].is_selected
    assert not thumbs[3].is_selected

def test_reverse_sorting(splitter, qtbot):
    thumbs = [w for w in splitter.findChildren(PageThumbnailWidget)]
    # Select pages 1-3 (indices 0, 2, 4 in layout because of dividers)
    # layout: T0, D0-1, T1, D1-2, T2, D2-3, T3
    
    splitter.on_selection_requested(thumbs[0], Qt.KeyboardModifier.NoModifier)
    splitter.on_selection_requested(thumbs[1], Qt.KeyboardModifier.ControlModifier)
    splitter.on_selection_requested(thumbs[2], Qt.KeyboardModifier.ControlModifier)
    
    # Currently: T0, T1, T2
    splitter._reverse_selected_sorting()
    
    # Check layout order
    new_widgets = [splitter.content_layout.itemAt(i).widget() for i in range(splitter.content_layout.count())]
    # Expected: T2 at index 0, T1 at index 2, T0 at index 4
    assert new_widgets[0] == thumbs[2]
    assert new_widgets[2] == thumbs[1]
    assert new_widgets[4] == thumbs[0]
    
    # Test contiguous selection (manually remove dividers for test or select adjacent)
    # If I select T0 and T1, and they have D0-1 between them, they are not contiguous.
    # But if the user selects T0, D0-1, T1? No, user only selects thumbs.
    
    # Let's refine the reverse logic to handle the "gap" of dividers if they are NOT active?
    # Actually, the user wants to reverse the ORDER of pages.
    
def test_move_logic(splitter, qtbot):
    thumbs = [w for w in splitter.findChildren(PageThumbnailWidget)]
    splitter.on_selection_requested(thumbs[0], Qt.KeyboardModifier.NoModifier)
    
    # Move T0 to end (after T3 which is at index 6)
    splitter._move_selection(7)
    
    new_widgets = [splitter.content_layout.itemAt(i).widget() for i in range(splitter.content_layout.count())]
    assert new_widgets[-1] == thumbs[0]
