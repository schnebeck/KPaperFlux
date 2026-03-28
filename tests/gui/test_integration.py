import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QPushButton, QFileDialog, QDialog
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
    with patch('gui.main_window.MainLoopWorker'):
        window = MainWindow(pipeline=mock_pipeline)
        qtbot.addWidget(window)
        window.show()

    # Trigger Import (Simulate menu action)
    # Instead of finding a button that might be gone, we call the slot directly
    # matching the action_import.triggered connection.

    # Mock QFileDialog to return a specific file path
    expected_path = "/tmp/test_doc.pdf"

    instructions = [{"pages": [{"file_path": expected_path, "file_page_index": 0, "rotation": 0}]}]

    # SplitterDialog and ImportWorker are lazily imported inside
    # DocumentActionController.start_import — patch at their source modules.
    with patch('gui.main_window.QFileDialog.getOpenFileNames', return_value=([expected_path], "PDF Files (*.pdf)")), \
         patch('gui.splitter_dialog.SplitterDialog') as mock_dialog_class, \
         patch('gui.workers.ImportWorker') as mock_worker_class:

        mock_dialog = mock_dialog_class.return_value
        mock_dialog.exec.return_value = QDialog.DialogCode.Accepted
        mock_dialog.import_instructions = instructions

        # Trigger the slot directly (simulating action trigger)
        window.import_document_slot()

        # Verify ImportWorker was created
        mock_worker_class.assert_called_once()
        args = mock_worker_class.call_args[0]
        assert args[0] == mock_pipeline
        # Second arg is import_items: [("BATCH", [...])]
        assert args[1][0][0] == "BATCH"
