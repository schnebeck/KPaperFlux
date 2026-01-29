
import pytest
from PyQt6.QtWidgets import QSplitter, QWidget
from gui.main_window import MainWindow
from gui.metadata_editor import MetadataEditorWidget
from gui.pdf_viewer import PdfViewerWidget
from core.database import DatabaseManager

@pytest.fixture
def mock_db():
    from unittest.mock import MagicMock
    db = MagicMock(spec=DatabaseManager)
    return db

def test_layout_structure(qtbot, mock_db):
    mw = MainWindow(db_manager=mock_db)
    qtbot.addWidget(mw)
    
    # Check Central Widget Layout
    central = mw.centralWidget()
    assert central is not None
    
    from PyQt6.QtCore import Qt
    # Check Main Horizontal Splitter
    main_splitter = mw.main_splitter
    assert isinstance(main_splitter, QSplitter)
    assert main_splitter.orientation() == Qt.Orientation.Horizontal
    
    # Check Left Pane (Vertical Splitter)
    left_pane = main_splitter.widget(0)
    assert isinstance(left_pane, QSplitter)
    assert left_pane.orientation() == Qt.Orientation.Vertical
    
    # Check Right Pane (Viewer)
    right_pane = main_splitter.widget(1)
    assert isinstance(right_pane, PdfViewerWidget)
    
    # Check Left Pane Widgets
    # 0 = Filter, 1 = List, 2 = Editor
    assert left_pane.count() == 3
    assert hasattr(mw, 'advanced_filter')
    assert hasattr(mw, 'list_widget')
    assert isinstance(left_pane.widget(2), MetadataEditorWidget)
    
def test_toggle_editor(qtbot, mock_db):
    mw = MainWindow(db_manager=mock_db)
    qtbot.addWidget(mw)
    mw.show()
    qtbot.waitForWindowShown(mw)
    
    editor = mw.editor_widget
    
    # Switch to Explorer page so children can be visible
    mw.central_stack.setCurrentIndex(1)
    
    # Initially hidden (no selection)
    assert editor.isHidden()
    
    # Trigger toggle on
    mw.toggle_editor_visibility(True)
    assert not editor.isHidden()
    
    # Trigger toggle off
    mw.toggle_editor_visibility(False)
    assert editor.isHidden()
