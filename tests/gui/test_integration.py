import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QPushButton, QFileDialog
from PyQt6.QtCore import Qt
from gui.main_window import MainWindow

@pytest.fixture
def mock_pipeline():
    return MagicMock()

def test_import_button_triggers_pipeline(qtbot, mock_pipeline):
    """
    Test that clicking the import button:
    1. Opens a file dialog (Mocked)
    2. Calls pipeline.process_document with the selected file
    """
    window = MainWindow(pipeline=mock_pipeline)
    qtbot.addWidget(window)
    window.show()

    # Find the button
    button = window.findChild(QPushButton, "btn_import")
    assert button is not None

    # Mock QFileDialog to return a specific file path
    expected_path = "/tmp/test_doc.pdf"
    
    from PyQt6.QtWidgets import QMessageBox
    
    with patch.object(QFileDialog, 'getOpenFileName', return_value=(expected_path, "PDF Files (*.pdf)")), \
         patch.object(QMessageBox, 'information') as mock_msg:
        # Simulate click using Qt constant
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        
        # Verify pipeline call
        mock_pipeline.process_document.assert_called_once_with(expected_path)
        
        # Verify success message
        mock_msg.assert_called_once()
