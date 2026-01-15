import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QPushButton, QTableWidget
from gui.main_window import MainWindow

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_all_documents.return_value = []
    return db

def test_main_window_title(qtbot, mock_db):
    """Test that the main window has the correct title."""
    window = MainWindow(db_manager=mock_db)
    qtbot.addWidget(window)
    
    assert window.windowTitle() == "KPaperFlux"

from PyQt6.QtGui import QAction

def test_import_action_exists(qtbot, mock_db):
    """Test that the Import Document action exists in the menu."""
    window = MainWindow(db_manager=mock_db)
    qtbot.addWidget(window)
    
    # Iterate over menu actions to find "Import Document"
    # Note: Accessing menu bar actions is slightly indirect
    menu_bar = window.menuBar()
    file_menu = None
    for action in menu_bar.actions():
        if "File" in action.text():
            file_menu = action.menu()
            break
            
    assert file_menu is not None
    
    import_action = None
    for action in file_menu.actions():
        if "Import" in action.text():
            import_action = action
            break
            
    assert import_action is not None
    assert import_action.isEnabled()

def test_document_list_exists(qtbot, mock_db):
    """Test that the document list widget is present."""
    window = MainWindow(db_manager=mock_db)
    qtbot.addWidget(window)
    
    table = window.findChild(QTableWidget)
    assert table is not None
