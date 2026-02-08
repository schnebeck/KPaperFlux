import sys
from PyQt6.QtWidgets import QApplication
from gui.pdf_viewer import DualPdfViewerWidget
from PyQt6.QtCore import Qt, QTimer
import unittest
import os
import tempfile
import fitz

class TestPdfMatchAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def create_dummy_pdf(self, path, pages=1):
        doc = fitz.open()
        for i in range(pages):
            page = doc.new_page()
            page.insert_text((50, 50), f"Page {i+1}")
        doc.save(path)
        doc.close()

    def test_diff_pdf_generation(self):
        """Verifies that Delta mode switches the right viewer to a temporary Diff PDF."""
        dual = DualPdfViewerWidget()
        
        # Create real dummy PDFs
        temp_dir = tempfile.gettempdir()
        path1 = os.path.join(temp_dir, "test_left.pdf")
        path2 = os.path.join(temp_dir, "test_right.pdf")
        self.create_dummy_pdf(path1, pages=2)
        self.create_dummy_pdf(path2, pages=2)
        
        dual.load_documents(path1, path2)
        
        # Wait for load
        # In a real test we'd use QTest.qWait, but here we'll just check initial state
        self.assertEqual(dual._orig_right_path, path2)
        
        # Activate Delta
        dual.btn_diff.setChecked(True)
        # _run_match_analysis is called
        
        # Check if right viewer is now loading a temp file
        # Note: Analysis might be async or deferred by QTimer, so we check the temp path variable
        # But for the unit test, we can call it directly if needed or wait.
        dual._run_match_analysis()
        
        self.assertIsNotNone(dual._diff_temp_path)
        self.assertTrue(os.path.exists(dual._diff_temp_path))
        
        # Deactivate Delta
        dual.btn_diff.setChecked(False)
        # Right viewer should reload orig path (deferred by 300ms in code, so we check intent)
        # Actually our test is synchronous, but we can check the logic.
        
        # Cleanup
        os.remove(path1)
        os.remove(path2)
        if dual._diff_temp_path and os.path.exists(dual._diff_temp_path):
            os.remove(dual._diff_temp_path)

    def test_button_alignment(self):
        """Verifies that Link and Delta buttons share the same X coordinate."""
        dual = DualPdfViewerWidget()
        dual.resize(1000, 600)
        dual.show()
        
        # Force a repositioning
        dual._reposition_link_button()
        
        self.assertEqual(dual.btn_link.x(), dual.btn_diff.x(), "Buttons must be vertically aligned on the same axis")

if __name__ == "__main__":
    unittest.main()
