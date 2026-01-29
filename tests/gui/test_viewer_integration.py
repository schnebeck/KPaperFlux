import sys
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from gui.pdf_viewer import PdfViewerWidget

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

class TestViewerIntegration(unittest.TestCase):
    def test_split_button_visibility(self):
        """Verify Split button is visible only for multiple pages."""
        viewer = PdfViewerWidget()
        # Mock document after it's created in __init__
        viewer.document = MagicMock()
        
        # Initial state (initially hidden by _init_ui)
        self.assertTrue(viewer.btn_split.isHidden())
        
        # 1 Page
        viewer.document.pageCount.return_value = 1
        from PyQt6.QtPdf import QPdfDocument
        viewer.on_document_status(QPdfDocument.Status.Ready)
        self.assertTrue(viewer.btn_split.isHidden())
        
        # 2 Pages
        viewer.document.pageCount.return_value = 2
        viewer.on_document_status(QPdfDocument.Status.Ready)
        self.assertFalse(viewer.btn_split.isHidden())
        
    def test_split_signal_emission(self):
        """Verify split_requested is emitted with current UUID."""
        viewer = PdfViewerWidget()
        viewer.current_uuid = "test-uuid"
        
        mock_signal = MagicMock()
        viewer.split_requested.connect(mock_signal)
        
        viewer.on_split_clicked()
        mock_signal.assert_called_once_with("test-uuid")

if __name__ == '__main__':
    unittest.main()
