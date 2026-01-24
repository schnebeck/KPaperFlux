import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from gui.widgets.splitter_strip import SplitterStripWidget, PageThumbnailWidget
from gui.splitter_dialog import SplitterDialog
from PyQt6.QtWidgets import QApplication

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

class TestBatchSplitterLogic(unittest.TestCase):
    
    @patch('gui.widgets.splitter_strip.fitz')
    def test_multi_file_loading(self, mock_fitz):
        """Verify that multiple files are loaded into a single stream with boundaries."""
        mock_doc = MagicMock()
        mock_doc.page_count = 2
        mock_fitz.open.return_value = mock_doc
        
        strip = SplitterStripWidget()
        paths = ["file1.pdf", "file2.pdf"]
        
        with patch('os.path.exists', return_value=True):
            strip.load_from_paths(paths)
            
        # Expectation: 
        # Page 1 (File 1)
        # Divider (Split - inactive)
        # Page 2 (File 1)
        # Divider (Boundary - active)
        # Page 1 (File 2)
        # Divider (Split - inactive)
        # Page 2 (File 2)
        
        # Total widgets: 4 thumbnails + 3 dividers = 7
        self.assertEqual(strip.content_layout.count(), 7)
        
        # Check active split at boundary (index 3 is the divider between file 1 and 2)
        boundary_div = strip.content_layout.itemAt(3).widget()
        self.assertTrue(boundary_div.is_active)
        
    def test_instruction_generation_batch(self):
        """Verify that scraped instructions correctly map to source files."""
        dialog = SplitterDialog(None)
        dialog.mode = "IMPORT"
        
        # Mocking 3 thumbnails from 2 files
        t1 = MagicMock(spec=PageThumbnailWidget)
        t1.page_info = {"file_path": "a.pdf", "page": 1}
        t1._page_num = 1
        t1.current_rotation = 0
        t1.is_deleted = False
        
        t2 = MagicMock(spec=PageThumbnailWidget)
        t2.page_info = {"file_path": "a.pdf", "page": 2}
        t2._page_num = 2
        t2.current_rotation = 90
        t2.is_deleted = False
        
        t3 = MagicMock(spec=PageThumbnailWidget)
        t3.page_info = {"file_path": "b.pdf", "page": 1}
        t3._page_num = 1
        t3.current_rotation = 0
        t3.is_deleted = False
        
        from gui.widgets.splitter_strip import SplitDividerWidget
        
        # d1 (inactive split), d2 (active split)
        d1 = MagicMock(spec=SplitDividerWidget)
        d1.is_active = False
        d2 = MagicMock(spec=SplitDividerWidget)
        d2.is_active = True
        
        # Mock layout to return these widgets
        mock_layout = MagicMock()
        mock_layout.count.return_value = 5
        
        widgets = [t1, d1, t2, d2, t3]
        def get_widget(i):
            m = MagicMock()
            m.widget.return_value = widgets[i]
            return m
            
        mock_layout.itemAt.side_effect = get_widget
        dialog.strip.content_layout = mock_layout
        
        instructions = dialog._scrape_instructions()
        
        # Expectation: 2 docs
        self.assertEqual(len(instructions), 2)
        
        # Doc 1: Pages from a.pdf (p1, p2 rotated)
        self.assertEqual(len(instructions[0]["pages"]), 2)
        self.assertEqual(instructions[0]["pages"][0]["file_path"], "a.pdf")
        self.assertEqual(instructions[0]["pages"][1]["rotation"], 90)
        
        # Doc 2: Page from b.pdf
        self.assertEqual(len(instructions[1]["pages"]), 1)
        self.assertEqual(instructions[1]["pages"][0]["file_path"], "b.pdf")

if __name__ == '__main__':
    unittest.main()
