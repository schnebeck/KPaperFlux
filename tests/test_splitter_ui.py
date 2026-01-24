
import sys
import os
import unittest

# Hardcode project root
project_root = "/home/schnebeck/Dokumente/Projects/KPaperFlux"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print(f"DEBUG: sys.path: {sys.path}")

try:
    import gui.widgets.splitter_strip
    print("DEBUG: Successfully imported gui.widgets.splitter_strip")
except ImportError as e:
    print(f"DEBUG: Import Failed: {e}")
    # List files to debug
    print(f"DEBUG: Content of gui/widgets: {os.listdir(os.path.join(project_root, 'gui/widgets'))}")

from PyQt6.QtWidgets import QApplication
from gui.widgets.splitter_strip import PageThumbnailWidget, ControlsOverlay

app = QApplication.instance() or QApplication(sys.argv)

class TestSplitterUI(unittest.TestCase):
    def test_soft_delete_logic(self):
        print("Testing Soft Delete...")
        page_info = {"page": 1, "rotation": 0}
        widget = PageThumbnailWidget(page_info, pipeline=None)
        
        self.assertFalse(widget.is_deleted)
        # Check initial style
        
        widget.toggle_delete()
        self.assertTrue(widget.is_deleted)
        # Check overlay visibility logic (mocked or state check)
        
        widget.toggle_delete()
        self.assertFalse(widget.is_deleted)
        print("Soft Delete Logic OK")

    def test_styling(self):
        print("Testing Styling...")
        # Provide dummy callbacks
        controls = ControlsOverlay(callback_rotate=lambda: None, callback_delete=lambda: None)
        # Check button sizes
        from PyQt6.QtWidgets import QPushButton
        btns = [c for c in controls.children() if isinstance(c, QPushButton)]
        for btn in btns:
            if btn.width() != 40:
                 print(f"FAILURE: Button width is {btn.width()}, expected 40")
                 self.fail("Button size incorrect")
            assert btn.width() == 40
            
            # Verify Shadow
            effect = btn.graphicsEffect()
            if not effect:
                print("FAILURE: No Graphics Effect (Shadow) found on button")
                self.fail("Missing Shadow Effect")
            from PyQt6.QtWidgets import QGraphicsDropShadowEffect
            assert isinstance(effect, QGraphicsDropShadowEffect)
            
        print("Styling & Shadow OK")

if __name__ == '__main__':
    unittest.main()
