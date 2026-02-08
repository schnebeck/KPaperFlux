
import sys
import unittest
from PyQt6.QtWidgets import QApplication
from gui.pdf_viewer import DualPdfViewerWidget, PdfViewerWidget
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtPdf import QPdfDocument

class TestPdfDeltaSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def setup_mock_docs(self, dual, left_size=(100, 100), right_size=(100, 100)):
        from unittest.mock import MagicMock
        for viewer, size in [(dual.left_viewer, left_size), (dual.right_viewer, right_size)]:
            viewer.document = MagicMock()
            viewer.document.status.return_value = QPdfDocument.Status.Ready
            viewer.document.pageCount.return_value = 1
            viewer.document.pagePointSize.return_value = QSize(*size)
            viewer.on_document_status(QPdfDocument.Status.Ready)

    def test_delta_ui_integration(self):
        dual = DualPdfViewerWidget()
        dual.show()
        self.setup_mock_docs(dual)
        dual.left_viewer.canvas.set_zoom(1.0)
        dual.right_viewer.canvas.set_zoom(1.1)
        self.assertAlmostEqual(dual._zoom_delta, 0.1, places=2)
        self.assertEqual(dual.right_viewer.edit_zoom.text(), "Δ +10%")

    def test_initial_delta_zero(self):
        dual = DualPdfViewerWidget()
        dual.show()
        self.setup_mock_docs(dual)
        dual.left_viewer.canvas.set_zoom(1.0)
        dual._sync_right_to_left()
        self.assertEqual(dual.right_viewer.edit_zoom.text(), "Δ +0%")

    def test_delta_stays_constant_on_fit(self):
        dual = DualPdfViewerWidget()
        dual.show()
        self.setup_mock_docs(dual, right_size=(200, 200))
        dual.left_viewer.canvas.set_zoom(1.0)
        dual._sync_right_to_left()
        self.assertEqual(dual.right_viewer.edit_zoom.text(), "Δ +0%")
        dual.right_viewer.canvas.set_zoom(0.6) 
        self.assertAlmostEqual(dual._zoom_delta, 0.1, places=2)
        dual.left_viewer.btn_fit.setChecked(True)
        dual._on_fit_clicked(dual.left_viewer, dual.right_viewer)
        self.assertEqual(dual.right_viewer.edit_zoom.text(), "Δ +10%")

    def test_zoom_in_from_fit_mode_delta_increase(self):
        dual = DualPdfViewerWidget()
        dual.show()
        self.setup_mock_docs(dual)
        from unittest.mock import MagicMock
        for v in [dual.left_viewer, dual.right_viewer]:
            v.view.viewport = MagicMock()
            v.view.viewport().width.return_value = 87 
            v.view.viewport().height.return_value = 1000
        dual.left_viewer.btn_fit.setChecked(True)
        dual._on_fit_clicked(dual.left_viewer, dual.right_viewer)
        self.assertEqual(dual.right_viewer.edit_zoom.text(), "Δ +0%")
        # In linked mode, zoom_in uses 1% step for precision
        dual.right_viewer.zoom_in()
        self.assertAlmostEqual(dual._zoom_delta, 0.01, places=2)
        self.assertEqual(dual.right_viewer.edit_zoom.text(), "Δ +1%")

if __name__ == "__main__":
    unittest.main()
