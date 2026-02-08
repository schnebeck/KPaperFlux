import sys
import unittest
from PyQt6.QtWidgets import QApplication
from gui.pdf_viewer import PdfViewerWidget
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
import os

class TestPdfViewerFit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def test_zoom_label_updates_on_fit(self):
        """Verifies that the zoom label is updated when 'Fit' is toggled."""
        viewer = PdfViewerWidget()
        viewer.resize(800, 600)
        viewer.show()
        
        # Mock a document and page
        from unittest.mock import MagicMock
        from PyQt6.QtCore import QSize
        viewer.document = MagicMock()
        viewer.document.pageCount.return_value = 1
        viewer.document.pagePointSize.return_value = QSize(100, 100) # Simple 100x100 page
        
        # Manually set a high zoom
        viewer.view.setZoomMode(QPdfView.ZoomMode.Custom)
        viewer.view.setZoomFactor(2.1)
        viewer.update_zoom_label(2.1)
        self.assertEqual(viewer.edit_zoom.text(), "210%")
        
        # Toggle Fit
        viewer.btn_fit.setChecked(True)
        viewer.toggle_fit(True)
        
        effective_zoom = viewer.nav.currentZoom()
        print(f"Effective Zoom (Navigator): {effective_zoom}")
        
        # The zoom label should NOT be 210% now.
        zoom_text = viewer.edit_zoom.text()
        print(f"Zoom after Fit: {zoom_text}")
        
        self.assertNotEqual(zoom_text, "210%", "Zoom label should update when Fit is active")

if __name__ == "__main__":
    unittest.main()
