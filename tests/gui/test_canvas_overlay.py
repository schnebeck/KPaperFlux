import sys
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QSize, Qt
from gui.widgets.canvas_page import CanvasPageWidget

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

class TestCanvasLayout(unittest.TestCase):
    def setUp(self):
        self.page_data = {
            "file_path": "dummy.pdf",
            "page_index": 0,
            "rotation": 0,
            "is_deleted": False
        }
        
    @patch('gui.widgets.canvas_page.fitz')
    def test_aspect_ratio_and_overlay(self, mock_fitz):
        """
        Verify that:
        1. The rendered image respects the aspect ratio of the source PDF.
        2. The widget size matches the image size (no extra padding causing 'square' look).
        3. The overlay controls are positioned INSIDE the image, not pushing layout.
        """
        # 1. Setup Mock PDF (Portrait: 100w x 200h) -> AR 0.5
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.load_page.return_value = mock_page
        
        # Mock Pixmap behavior
        # We simulate a HIGH RES render (e.g. scale 2.5) -> 250w x 500h
        # But for aspect ratio check, we care about final sizing.
        mock_pix = MagicMock()
        mock_pix.width = 250
        mock_pix.height = 500
        mock_pix.stride = 250 * 3
        mock_pix.samples = bytes(250 * 500 * 3) # Mock buffer
        mock_page.get_pixmap.return_value = mock_pix
        
        # 2. Instantiate Widget
        # We need to ensure logic uses QImage properly with mocked buffer.
        # This might segfault if buffer is GC'd? Python bytes is safe.
        
        widget = CanvasPageWidget(self.page_data)
        
        # 3. Verify Scale Logic
        # TARGET_LONG_EDGE = 900. 
        # Source 250x500 is < 900, so it should NOT scale if we follow logic "long_side > TARGET".
        # Checking logic in refresh_view:
        # if long_side > self.TARGET_LONG_EDGE: scaled... else scaled = rotated_pix
        # So it remains 250x500.
        
        # Force refresh and show
        widget._render_initial()
        widget.show()
        
        # Check Layout Structure (Confirm Header Removed)
        self.assertEqual(widget.layout.count(), 1, "Main layout should only have canvas container (Header removed)")
        self.assertIsNone(widget.canvas_container.layout(), "Canvas container should use absolute positioning (No Layout)")
        
        # Check Container Size
        container_size = widget.canvas_container.size()
        expected_size = QSize(250, 500)
        
        print(f"Container Size: {container_size}, Expected: {expected_size}")
        self.assertEqual(container_size, expected_size, "Container should match image size strictly")
        
        # 4. Check Overlay Positioning
        # Controls should be at Top Right (approx width-controls_width, 10)
        controls = widget.controls
        c_geo = controls.geometry()
        
        # Assert control is inside valid rect
        self.assertTrue(c_geo.right() <= 250, "Controls should be within width")
        self.assertTrue(c_geo.top() >= 0, "Controls should be inside top")
        # For visibility test in headless, we check isHidden() is False or property
        self.assertFalse(controls.isHidden(), "Controls should be visible (not hidden)")
        
        # 5. Test Rotation 90 deg (Landscape)
        # 250x500 -> 500x250
        widget.rotate_right()
        
        new_size = widget.canvas_container.size()
        self.assertEqual(new_size, QSize(500, 250), "Rotated size matches landscape aspect")
        
        # Controls should move
        c_geo_new = widget.controls.geometry()
        self.assertTrue(c_geo_new.right() <= 500)
        
        # 6. Test Upscaling/Downscaling Logic (If simulated huge image)
        
    @patch('gui.widgets.canvas_page.fitz')
    def test_large_image_scaling(self, mock_fitz):
        # 1000x2000 source -> Should scale to fit 900h
        # AR 0.5 -> 450x900
        
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.load_page.return_value = mock_page
        
        mock_pix = MagicMock()
        mock_pix.width = 1000
        mock_pix.height = 2000 
        mock_pix.stride = 1000 * 3
        mock_pix.samples = bytes(1000 * 2000 * 3)
        mock_page.get_pixmap.return_value = mock_pix
        
        widget = CanvasPageWidget(self.page_data)
        
        # Expected: Height=900, Width=450
        target_h = 900
        target_w = 450
        
        c_size = widget.canvas_container.size()
        self.assertEqual(c_size.height(), target_h)
        self.assertEqual(c_size.width(), target_w)
        
        # Aspect Ratio Check
        ar = c_size.width() / c_size.height()
        self.assertAlmostEqual(ar, 0.5, delta=0.01)

if __name__ == '__main__':
    unittest.main()
