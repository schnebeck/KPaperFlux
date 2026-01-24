import sys
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from gui.pdf_viewer import PdfViewerWidget

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

class TestViewerIntegration(unittest.TestCase):
    def setUp(self):
        self.viewer = PdfViewerWidget()
        self.viewer.show()
        
    def test_split_button_visibility(self):
        """Verify Split button is visible only for multiple pages."""
        # 0 Pages (Initial)
        self.assertFalse(self.viewer.btn_split.isVisible())
        
        # 1 Page
        page_data = {"file_path": None, "page_index": 0, "rotation": 0, "is_deleted": False}
        with patch('gui.pdf_viewer.CanvasPageWidget._render_initial'):
             self.viewer._add_page_widget(page_data)
        self.assertFalse(self.viewer.btn_split.isVisible())
        
        # 2 Pages
        with patch('gui.pdf_viewer.CanvasPageWidget._render_initial'):
             self.viewer._add_page_widget(page_data)
        self.assertTrue(self.viewer.btn_split.isVisible())
        
    def test_split_signal_emission(self):
        """Verify split_requested is emitted with current UUID."""
        self.viewer.current_uuid = "test-uuid"
        
        mock_signal = MagicMock()
        self.viewer.split_requested.connect(mock_signal)
        
        self.viewer.on_split_clicked()
        mock_signal.assert_called_once_with("test-uuid")

if __name__ == '__main__':
    unittest.main()
