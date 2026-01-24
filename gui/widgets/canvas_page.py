from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QSizePolicy, QFrame, QHBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QImage, QTransform
import fitz

class ControlsOverlay(QWidget):
    """Floating controls for the CanvasPageWidget."""
    def __init__(self, parent=None, callback_rotate=None, callback_delete=None):
        super().__init__(parent)
        self.callback_rotate = callback_rotate
        self.callback_delete = callback_delete
        self._init_ui()
        
    def _init_ui(self):
        self.setStyleSheet("background: rgba(0, 0, 0, 150); border-radius: 5px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        btn_rot = QPushButton("↻")
        btn_rot.setFixedSize(30, 30)
        btn_rot.clicked.connect(self.callback_rotate)
        btn_rot.setStyleSheet("background: white; color: black; border-radius: 15px; font-weight: bold;")
        btn_rot.setToolTip("Rotate 90°")
        
        btn_del = QPushButton("🗑")
        btn_del.setFixedSize(30, 30)
        btn_del.clicked.connect(self.callback_delete)
        btn_del.setStyleSheet("background: #ff4444; color: white; border-radius: 15px; font-weight: bold;")
        btn_del.setToolTip("Delete Page")
        
        layout.addWidget(btn_rot)
        layout.addWidget(btn_del)
        
        self.adjustSize()

class CanvasPageWidget(QWidget):
    """
    High-Fidelity Page Renderer (Poppler/Fitz) with Overlay UI.
    Supports:
    - Dynamic Rotation (Visual only)
    - Logical Deletion
    - Consistent Zoom (Long-Edge Fit)
    """
    state_changed = pyqtSignal()
    
    # Target height rationale: Standard 1080p screen has ~900px usable height.
    # We target fitting the LONG edge to roughly 900px to ensure it fits on screen without massive scrolling.
    TARGET_LONG_EDGE = 900 
    
    def __init__(self, page_data, parent=None):
        """
        :param page_data: Dict or Object containing:
               - file_path: str (Physical path)
               - page_index: int (0-based)
               - rotation: int (0, 90, 180, 270)
               - is_deleted: bool
        """
        super().__init__(parent)
        self.page_data = page_data
        
        # State
        self.rotation = page_data.get("rotation", 0)
        self.is_deleted = page_data.get("is_deleted", False)
        
        self.file_path = page_data.get("file_path")
        self.page_index = page_data.get("page_index")
        
        self.original_pixmap = None 
        
        self._init_ui()
        self._render_initial()
        
    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Container for Image + Overlays
        self.canvas_container = QWidget()
        self.canvas_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.canvas_container.setStyleSheet("background: transparent;") # Render background on image or parent
        
        # Image Label
        self.lbl_image = QLabel(self.canvas_container)
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setStyleSheet("border: 1px solid #ccc; background: white;")
        
        # --- Controls Overlay (Floating) ---
        self.controls = ControlsOverlay(
            self.canvas_container, 
            callback_rotate=self.rotate_right,
            callback_delete=self.toggle_delete
        )
        self.controls.hide() # Show on hover? Or always? User asked for "fixes Overlay" -> Visible.
        self.controls.show()
        
        # --- Deleted Overlay ---
        self.delete_overlay = QFrame(self.canvas_container)
        self.delete_overlay.setStyleSheet("background: rgba(200, 50, 50, 180);")
        self.delete_overlay.hide()
        
        l = QVBoxLayout(self.delete_overlay)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("DELETED")
        lbl.setStyleSheet("color: white; font-weight: bold; font-size: 24px; border: 2px solid white; padding: 10px; border-radius: 5px;")
        btn_restore = QPushButton("Restore")
        btn_restore.clicked.connect(self.toggle_delete)
        l.addWidget(lbl)
        l.addWidget(btn_restore)
        
        # Page Number Badge (Top-Left)
        self.page_badge = QLabel(f"P {self.page_index + 1}", self.canvas_container)
        self.page_badge.setStyleSheet("background: rgba(0,0,0,150); color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;")
        self.page_badge.show()
        
        self.layout.addWidget(self.canvas_container)
        
    def _render_initial(self):
        if not self.file_path: return
        try:
            doc = fitz.open(self.file_path)
            page = doc.load_page(self.page_index)
            # Render High Res (Standard DPI 72 * 2.5 ~ 180 DPI) for crisp zoom
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
            
            img_format = QImage.Format.Format_RGB888
            qt_img = QImage(pix.samples, pix.width, pix.height, pix.stride, img_format)
            self.original_pixmap = QPixmap.fromImage(qt_img)
            doc.close()
            self.refresh_view()
        except Exception as e:
            print(f"Error rendering: {e}")
            
    def refresh_view(self):
        if not self.original_pixmap: return
        
        # 1. Rotation (Logic: Rotate the Source High-Res Pixmap)
        transform = QTransform().rotate(self.rotation)
        rotated_pix = self.original_pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
        
        # 2. Scaling (Logic: Fit Longest Side to Target)
        # This ensures that Portrait and Landscape pages have consistent visual scale ("Text size remains same")
        # and fits nicely on screen.
        w = rotated_pix.width()
        h = rotated_pix.height()
        long_side = max(w, h)
        
        if long_side > self.TARGET_LONG_EDGE:
            scaled_pix = rotated_pix.scaled(
                self.TARGET_LONG_EDGE, 
                self.TARGET_LONG_EDGE, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            scaled_pix = rotated_pix
            
        self.lbl_image.setPixmap(scaled_pix)
        self.lbl_image.resize(scaled_pix.size())
        
        # Resize Container to fit Image
        self.canvas_container.setFixedSize(scaled_pix.size())
        
        # 3. Update Overlays State
        if self.is_deleted:
            self.delete_overlay.resize(scaled_pix.size())
            self.delete_overlay.show()
            self.delete_overlay.raise_()
            self.controls.hide()
        else:
            self.delete_overlay.hide()
            self.controls.show()
            self.controls.raise_()
            self.page_badge.raise_()
            
        self._update_overlay_positions()
        self.state_changed.emit()
            
    def _update_overlay_positions(self):
        """Position overlays relative to the image size."""
        w = self.canvas_container.width()
        h = self.canvas_container.height()
        
        # Controls: Top Right
        cw = self.controls.width()
        ch = self.controls.height()
        self.controls.move(w - cw - 10, 10)
        
        # Page Badge: Top Left
        self.page_badge.move(10, 10)
        
        # Deleted Overlay: Fill
        if self.is_deleted:
            self.delete_overlay.resize(w, h)
            
    def rotate_right(self):
        self.rotation = (self.rotation + 90) % 360
        self.page_data["rotation"] = self.rotation
        self.refresh_view()
        
    def toggle_delete(self):
        self.is_deleted = not self.is_deleted
        self.page_data["is_deleted"] = self.is_deleted
        self.refresh_view()
        
    def resizeEvent(self, event):
        self._update_overlay_positions()
        super().resizeEvent(event)
