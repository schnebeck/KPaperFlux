import pytest
from PyQt6.QtWidgets import QPushButton
from gui.main_window import MainWindow

def test_main_window_title(qtbot):
    """Test that the main window has the correct title."""
    window = MainWindow()
    qtbot.addWidget(window)
    
    assert window.windowTitle() == "KPaperFlux"

def test_import_button_exists(qtbot):
    """Test that the Import Document button exists."""
    window = MainWindow()
    qtbot.addWidget(window)
    
    # We expect a button with objectName 'btn_import' or text 'Import'
    button = window.findChild(QPushButton, "btn_import")
    assert button is not None
    assert "Import" in button.text()
