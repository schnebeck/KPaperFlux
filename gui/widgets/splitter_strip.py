from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QPushButton, QSizePolicy, QGraphicsDropShadowEffect, QMenu
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QMimeData, QPoint, QPropertyAnimation, pyqtProperty, QTimer
from PyQt6.QtGui import QPixmap, QIcon, QCursor, QColor, QDrag, QAction, QPainter, QPen, QBrush
import fitz  # PyMuPDF for thumbnails
import os
import json

class SplitDividerWidget(QWidget):
    """
    A clickable divider between pages (Vertical bar for horizontal layout).
    Supports Toggle State (Active/Inactive).
    """
    split_requested = pyqtSignal()
    
    def __init__(self, page_index_before: int, parent=None):
        super().__init__(parent)
        self.page_index_before = page_index_before
        self.is_active = False # State: Is this a cut point?
        self.is_boundary = False # If True, cannot be disabled
        
        self.setFixedWidth(40) # Wider to fit 28px icon comfortably
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Visual line (Vertical)
        self.line = QFrame()
        self.line.setFrameShape(QFrame.Shape.VLine)
        self.line.setStyleSheet("background-color: transparent; border-left: 2px dashed #ccc;")
        self.line.setFixedWidth(2)
        
        # Scissor Icon
        self.icon_label = QLabel("✂")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("color: #666; font-size: 20px; background: white; border-radius: 12px; border: 1px solid #ddd;")
        self.icon_label.setFixedSize(28, 28)
        self.icon_label.setVisible(False)
        self.icon_label.setToolTip(self.tr("Click to Toggle Split"))
        
        # Centering container
        container = QWidget()
        l_layout = QHBoxLayout(container)
        l_layout.setContentsMargins(19, 0, 0, 0) # Center the 2px line in 40px width (approx 19px padding)
        l_layout.addWidget(self.line)
        self.layout.addWidget(container)
        
        self.icon_label.setParent(self) 
        
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet("background: transparent;")
        
    def set_active(self, active: bool):
        self.is_active = active
        if active:
             if self.is_boundary:
                  self.line.setStyleSheet("background-color: transparent; border-left: 2px solid #555;")
                  self.icon_label.setStyleSheet("color: white; font-size: 20px; background: #555; border: 1px solid #555; border-radius: 12px;")
             else:
                  self.line.setStyleSheet("background-color: transparent; border-left: 2px solid #d32f2f;")
                  self.icon_label.setStyleSheet("color: white; font-size: 20px; background: #d32f2f; border: 1px solid #d32f2f; border-radius: 12px;")
             self.icon_label.setVisible(True)
        else:
             self.line.setStyleSheet("background-color: transparent; border-left: 2px dashed #ccc;")
             self.icon_label.setStyleSheet("color: #666; font-size: 20px; background: white; border-radius: 12px; border: 1px solid #ddd;")
             self.icon_label.setVisible(False)

    def resizeEvent(self, event):
        if self.icon_label:
            self.icon_label.move(
                (self.width() - self.icon_label.width()) // 2,
                (self.height() - self.icon_label.height()) // 2
            )
        super().resizeEvent(event)
        
    def enterEvent(self, event):
        if not self.is_active:
            self.line.setStyleSheet("background-color: transparent; border-left: 2px dashed #d32f2f;")
            self.icon_label.setVisible(True)
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        if not self.is_active:
            self.line.setStyleSheet("background-color: transparent; border-left: 2px dashed #ccc;")
            self.icon_label.setVisible(False)
        super().leaveEvent(event)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_boundary:
                 return # Fixed split at file boundary
            # Toggle State
            self.set_active(not self.is_active)
            self.split_requested.emit()

class DragPlaceholderWidget(QWidget):
    """
    A placeholder that expands/shrinks to show where a page will be dropped.
    """
    def __init__(self, target_width: int, is_static=False, parent=None):
        super().__init__(parent)
        self.target_width = target_width
        # v28.8: Support static width on creation to avoid start-animation
        initial_w = target_width if is_static else 0
        self.setFixedWidth(initial_w)
        self.setStyleSheet("background: rgba(0, 120, 215, 40); border: 2px dashed #0078d7; border-radius: 5px;")
        
        self._animation = QPropertyAnimation(self, b"width_property")
        self._animation.setDuration(250) 
        
        if is_static:
            self.show() # V28.10: Critical to avoid flicker
        
    @pyqtProperty(int)
    def width_property(self):
        return self.width()
        
    @width_property.setter
    def width_property(self, value):
        self.setFixedWidth(value)

    def expand(self):
        print(f"[DEBUG] Placeholder Animation: EXPAND (target={self.target_width})")
        self._animation.stop()
        self._animation.setStartValue(self.width())
        self._animation.setEndValue(self.target_width)
        self.show()
        self._animation.start()

    def expand_instantly(self):
        """Skip animation and set target width immediately."""
        print(f"[DEBUG] Placeholder: INSTANT EXPAND (width={self.target_width})")
        self._animation.stop()
        self.setFixedWidth(self.target_width)
        self.show()

    def shrink_and_delete(self):
        print(f"[DEBUG] Placeholder Animation: SHRINK (current={self.width()})")
        self._animation.stop()
        self._animation.setStartValue(self.width())
        self._animation.setEndValue(0)
        self._animation.finished.connect(self.deleteLater)
        self._animation.start()

class ReliefButton(QPushButton):
    """
    A button that draws itself with a high-contrast white relief 'outline'.
    It draws everything twice: once slightly thick in white, and once centered in blue-grey.
    """
    def __init__(self, icon_text, parent=None):
        super().__init__(icon_text, parent)
        self.setFixedSize(42, 42) # Slightly larger for the relief boundary
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.AntiAliasing if hasattr(QPainter, "AntiAliasing") else QPainter.RenderHint.Antialiasing)
        
        # Geometry
        rect = self.rect()
        circle_rect = rect.adjusted(3, 3, -3, -3)
        
        # 1. Background (Internal "Ghost" Fill)
        bg_color = QColor(255, 255, 255, 40) # 85% transparent white
        if self.underMouse():
            bg_color = QColor(255, 255, 255, 120) 
        
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(circle_rect)
        
        # Shared properties
        main_color = QColor("#5a7d9a")
        text = self.text()
        text_rect = rect.translated(0, 2)
        font = self.font()
        font.setWeight(900)
        font.setPointSize(24)
        painter.setFont(font)
        
        # --- PHASE 1: WHITE RELIEF (ALL) ---
        
        # White Circle
        white_pen = QPen(Qt.GlobalColor.white)
        white_pen.setWidth(5)
        painter.setPen(white_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(circle_rect)
        
        # White Text Outline
        painter.setPen(Qt.GlobalColor.white)
        for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1), (-1, 0), (1, 0), (0, -1), (0, 1)]:
            painter.drawText(text_rect.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, text)
            
        # --- PHASE 2: BLUE-GREY CORE (ALL) ---
        
        # Blue-grey Circle
        blue_pen = QPen(main_color)
        blue_pen.setWidth(2)
        painter.setPen(blue_pen)
        painter.drawEllipse(circle_rect)
        
        # Blue-grey Text Core
        painter.setPen(main_color)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)
        
        painter.end()

class ControlsOverlay(QWidget):
    """Floating controls for the Thumbnail."""
    def __init__(self, parent=None, callback_rotate=None, callback_delete=None, callback_drag=None):
        super().__init__(parent)
        self.callback_rotate = callback_rotate
        self.callback_delete = callback_delete
        self.callback_drag = callback_drag
        self._init_ui()
        
    def _init_ui(self):
        # Transparent barrier so it doesn't block image view, but spans width
        self.setStyleSheet("QToolTip { color: #ffffff; background-color: #000000; border: 1px solid white; font-weight: bold; }")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # ROTATE BUTTON (Top Left)
        btn_rot = ReliefButton("↻")
        btn_rot.clicked.connect(self.callback_rotate)
        btn_rot.setToolTip("Rotate 90°")
        layout.addWidget(btn_rot)
        
        layout.addStretch()

        # MOVE HANDLE (Middle)
        self.btn_move = ReliefButton("↔")
        self.btn_move.setToolTip("Drag to Move Page")
        layout.addWidget(self.btn_move)

        layout.addStretch()
        
        # DELETE BUTTON (Top Right)
        btn_del = ReliefButton("✕")
        btn_del.clicked.connect(self.callback_delete)
        btn_del.setToolTip("Delete / Restore Page")
        layout.addWidget(btn_del)
        
        # Size Policy: Expanding Width
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

class PageThumbnailWidget(QWidget):
    """
    Displays a single page thumbnail with Overlay UI. Supports Lazy Loading.
    """
    rotated = pyqtSignal()
    delete_toggled = pyqtSignal()
    selection_requested = pyqtSignal(object, object) # (widget, modifiers)
    drag_started = pyqtSignal(object) # (widget)
    aspect_ratio_changed = pyqtSignal() # New: Signal when AR is detected or changed

    def __init__(self, page_info: dict, pipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.page_info = page_info 
        
        self._page_num = page_info.get("page", 1)
        self.current_rotation = page_info.get("rotation", 0)
        
        # Soft Delete State
        self.is_deleted = False
        self.is_selected = False

        # Default A4 Aspect Ratio (Width / Height) = 1 / sqrt(2) ~= 0.707
        self.aspect_ratio = 0.707 
        if self.current_rotation in [90, 270]:
            self.aspect_ratio = 1.0 / self.aspect_ratio

        self.loaded = False
        self.original_pixmap = None
        
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(0, 0)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Container
        self.img_container = QWidget()
        self.img_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.img_container.setMinimumSize(0, 0)
        self.img_layout = QVBoxLayout(self.img_container)
        self.img_layout.setContentsMargins(0,0,0,0)
        self.img_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_img = QLabel()
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_img.setStyleSheet("border: none; background: transparent;")
        self.lbl_img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.lbl_img.setMinimumSize(0, 0) 
        self.lbl_img.setText("Loading...") 
        
        self.img_layout.addWidget(self.lbl_img)
        self.layout.addWidget(self.img_container)
        
        # Deletion Overlay (Red X)
        self.del_overlay = QLabel(self.img_container)
        self.del_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.del_overlay.setStyleSheet("background: rgba(255, 200, 200, 150); color: red; font-size: 60px; font-weight: bold;")
        self.del_overlay.setText("❌")
        # Ensure click-through
        self.del_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.del_overlay.hide()

        self.lbl_num = QLabel(str(self._page_num), self.img_container)
        self.lbl_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_num.setStyleSheet("background: rgba(0,0,0,100); color: white; border-radius: 10px; font-weight: bold; padding: 2px 8px;")
        self.lbl_num.adjustSize()
        
        self.controls = ControlsOverlay(
            self.img_container,
            callback_rotate=self.rotate_right,
            callback_delete=self.toggle_delete
        )
        self.controls.btn_move.installEventFilter(self)
        self.controls.show()
        
        self.last_drawn_height = 0
        
    def load_content(self) -> None:
        """Lazy load the actual image content."""
        if self.loaded: return
        
        # Render
        pix = self._fetch_pixmap()
        if not pix.isNull():
            self.original_pixmap = pix
            self.loaded = True
            
            # Update AR from Real Content
            if pix.height() > 0:
                 real_ar = pix.width() / pix.height()
                 base_ar = real_ar
                 if self.current_rotation in [90, 270]:
                     self.aspect_ratio = 1.0 / base_ar
                 else:
                     self.aspect_ratio = base_ar
                     
            self.aspect_ratio_changed.emit()
            self.last_drawn_height = 0 
            self.resizeEvent(None)
        else:
            self.lbl_img.setText("Error")
            
    def unload_content(self):
        if not self.loaded: return
        self.original_pixmap = None
        self.lbl_img.clear()
        self.lbl_img.setText("Loading...")
        self.loaded = False
        
    def _fetch_pixmap(self) -> QPixmap:
        try:
            path = None
            if "raw_path" in self.page_info:
                path = self.page_info["raw_path"]
            elif "file_path" in self.page_info: # Consistency
                path = self.page_info["file_path"]
            elif self.pipeline:
                path = self.pipeline.vault.get_file_path(self.page_info["file_uuid"])
                
            if not path or not os.path.exists(path): return QPixmap()
            
            doc = fitz.open(path)
            # page is 1-based
            page = doc.load_page(self.page_info["page"] - 1)
            # Standard render scaling
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            
            from PyQt6.QtGui import QImage
            img_format = QImage.Format.Format_RGB888
            qt_img = QImage(pix.samples, pix.width, pix.height, pix.stride, img_format)
            return QPixmap.fromImage(qt_img)
        except Exception as e:
            print(f"Render Error p{self._page_num}: {e}")
            return QPixmap()
    def rotate_right(self):
        # Allow rotation even if deleted
        self.current_rotation = (self.current_rotation + 90) % 360
        self.page_info["rotation"] = self.current_rotation
        
        # Invert AR
        self.aspect_ratio = 1.0 / self.aspect_ratio
        self.aspect_ratio_changed.emit() # Notify parent
        
        self.last_drawn_height = 0 
        self.resizeEvent(None)
        self.rotated.emit()
        
    def toggle_delete(self):
        self.is_deleted = not self.is_deleted
        self.page_info["is_deleted"] = self.is_deleted 
        
        if self.is_deleted:
            self.del_overlay.show()
            self.del_overlay.raise_()       # Raise X
            self.controls.raise_()          # Raise Controls ABOVE X
            self.lbl_img.setStyleSheet("border: 1px solid red; background: #ffeeee; opacity: 0.5;")
        else:
            self.del_overlay.hide()
            self.lbl_img.setStyleSheet("border: none; background: transparent;")
            
        self.resizeEvent(None)
        self.delete_toggled.emit()

    def set_selected(self, selected: bool):
        self.is_selected = selected
        if selected:
            self.lbl_img.setStyleSheet("border: 3px solid #0078d7; background: transparent;")
        elif self.is_deleted:
            self.lbl_img.setStyleSheet("border: 1px solid red; background: #ffeeee; opacity: 0.5;")
        else:
            self.lbl_img.setStyleSheet("border: none; background: transparent;")

    def eventFilter(self, obj, event):
        if obj == self.controls.btn_move:
            from PyQt6.QtCore import QEvent
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.drag_started.emit(self)
                    return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selection_requested.emit(self, event.modifiers())
        super().mousePressEvent(event)
        
    def sizeHint(self):
        # We "wish" for a healthy default height. This allows the window to grow
        # back towards this size if shrunk.
        h = 400 
        return QSize(int(h * self.aspect_ratio), h)

    def minimumSizeHint(self):
        # Crucial for shrinking: must be small!
        return QSize(10, 10)

    def resizeEvent(self, event):
        h = self.height()

        # 2. Image Rendering
        if self.loaded and self.original_pixmap and not self.original_pixmap.isNull():
             if (h > 10) and (abs(h - self.last_drawn_height) > 2 or self.last_drawn_height == 0):
                self.last_drawn_height = h
                
                from PyQt6.QtGui import QTransform
                transformed = self.original_pixmap.transformed(QTransform().rotate(self.current_rotation), Qt.TransformationMode.SmoothTransformation)
                
                scaled = transformed.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                
                self.lbl_img.setPixmap(scaled)
        
        # 3. Overlay
        if self.is_deleted:
            self.del_overlay.resize(self.size())
            self.del_overlay.move(0,0)
            self.del_overlay.raise_()

        # Update Controls GEOMETRY to fill TOP BAR
        self.controls.resize(self.width(), 60) # Tall enough for 40px buttons + padding
        self.controls.move(0, 0) # Top of unit
        self.controls.raise_() # ALWAYS TOP

        # Page Number Bottom Center
        self.lbl_num.raise_()
        n_w = self.lbl_num.width()
        n_h = self.lbl_num.height()
        self.lbl_num.move((self.width() - n_w) // 2, self.height() - n_h - 5)
        
        if event: super().resizeEvent(event)

class SplitterStripWidget(QWidget):
    """
    The main Filmstrip widget (Horizontal). supports Lazy Loading.
    """
    split_action_triggered = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_uuid = None
        self.pipeline = None
        self.undo_stack = [] # List of (type, data)
        self.selected_widgets = []
        self.last_selected_widget = None
        self.drag_placeholder = None
        self.import_mode = False
        self.is_dragging = False # TRACKER
        
        # Auto-scroll support
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(20)
        self._scroll_timer.timeout.connect(self._handle_auto_scroll)
        self._auto_scroll_speed = 0
        
        self.init_ui()
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Hook Scroll for Lazy Loading
        self.scroll.horizontalScrollBar().valueChanged.connect(self.on_scroll_changed)
        self.scroll.horizontalScrollBar().sliderReleased.connect(self.on_scroll_changed) # Ensure final update
        
        self.content_widget = QWidget()
        self.content_layout = QHBoxLayout(self.content_widget)
        self.content_layout.setSpacing(0)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.scroll.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll)
        
        # v28.5: Tastatur-Events abfangen (Focus-Problem lösen)
        self.scroll.installEventFilter(self)
        
    def showEvent(self, event):
        """Final scaling sweep when the widget is actually displayed."""
        super().showEvent(event)
        QTimer.singleShot(0, self._force_thumbnail_resize)
        
    def resizeEvent(self, event):
        """When the main strip resizes, ensure thumbnails recalculate their size."""
        super().resizeEvent(event)
        # Force thumbnails interested in resizing
        QTimer.singleShot(0, self._force_thumbnail_resize)

    def _force_thumbnail_resize(self):
        """Iterate all thumbnails and force them to match the current viewport height."""
        # Available height in viewport minus contents margins (10 top + 10 bottom = 20)
        # We use a bit more buffer to avoid scrollbars
        viewport = self.scroll.viewport()
        if not viewport: return
        
        h = viewport.height() - 25 
        if h < 50: return 
        
        layout_changed = False
        
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, PageThumbnailWidget):
                    # Explicitly set the size based on aspect ratio
                    target_w = int(h * w.aspect_ratio)
                    
                    # Optimization: Only trigger update if size actually changes
                    if w.width() != target_w or w.height() != h:
                        w.setFixedSize(target_w, h)
                        w.last_drawn_height = 0 # Force redraw of internal pixmap
                        w.update()
                        layout_changed = True

        # --- FIX: Zwinge das Layout zur Neuberechnung der Positionen ---
        if layout_changed:
            self.content_layout.invalidate()
            self.content_layout.activate()
            self.content_widget.adjustSize() # Wichtig für die ScrollArea!
    def load_document(self, pipeline, entity_uuid: str):
        self.current_uuid = entity_uuid
        self.pipeline = pipeline
        self._clear_layout()
        
        if not pipeline: return
        
        try:
             v_doc = pipeline.logical_repo.get_by_uuid(entity_uuid)
             if not v_doc or not v_doc.source_mapping: return
             file_uuid = v_doc.source_mapping[0].file_uuid
             
             path = pipeline.vault.get_file_path(file_uuid)
             if not path: return
             
             doc = fitz.open(path)
             page_count = doc.page_count
             doc.close()
             
             flat_pages = [{"file_uuid": file_uuid, "page": p+1, "rotation": 0} for p in range(page_count)]
             
             self._populate_strip(flat_pages)
             
        except Exception as e:
             print(f"Error resolving file context: {e}")

    def load_from_path(self, file_path: str):
        self.current_uuid = "PENDING_IMPORT"
        self.pipeline = None # No pipeline needed for raw path
        self._clear_layout()
        
        if not file_path or not os.path.exists(file_path): return
        
        try:
             doc = fitz.open(file_path)
             page_count = doc.page_count
             doc.close()
             
             flat_pages = [{"file_uuid": "RAW", "page": p+1, "rotation": 0, "raw_path": file_path} for p in range(page_count)]
             self._populate_strip(flat_pages)
        except Exception as e:
            print(f"Error loading raw file: {e}")

    def load_from_paths(self, file_paths: list[str]) -> None:
        """Load multiple raw files into a single continuous stream."""
        self.current_uuid = "BATCH_IMPORT"
        self.pipeline = None
        self._clear_layout()
        
        all_pages = []
        for f_idx, path in enumerate(file_paths):
            if not path or not os.path.exists(path): continue
            try:
                doc = fitz.open(path)
                count = doc.page_count
                doc.close()
                
                for p in range(count):
                    all_pages.append({
                        "file_uuid": f"FILE_{f_idx}", # Internal reference
                        "file_path": path,
                        "page": p + 1,
                        "rotation": 0,
                        "is_boundary": (p == 0 and f_idx > 0) # Mark first page of subsequent files
                    })
            except Exception as e:
                print(f"Error loading {path}: {e}")
                
        self._populate_strip(all_pages)

    def _populate_strip(self, flat_pages: list[dict]) -> None:
        """Create placeholders."""
        for i, pg_info in enumerate(flat_pages):
            # 1. Automatic Split before boundary files
            if pg_info.get("is_boundary"):
                div = SplitDividerWidget(page_index_before=i-1)
                div.is_boundary = True # Locked
                div.set_active(True) # Default split at file boundaries
                div.split_requested.connect(lambda idx=i-1, d=div: self.on_split_clicked(idx, d))
                self.content_layout.addWidget(div)

            # 2. Thumbnail
            thumb = PageThumbnailWidget(pg_info, self.pipeline)
            thumb.rotated.connect(lambda t=thumb: self.record_action("ROTATE", t))
            thumb.delete_toggled.connect(lambda t=thumb: self.record_action("DELETE", t))
            thumb.selection_requested.connect(self.on_selection_requested)
            thumb.drag_started.connect(self.on_drag_started)
            thumb.aspect_ratio_changed.connect(self._force_thumbnail_resize) # New: Link for instant width sync
            self.content_layout.addWidget(thumb)
            
            # 3. Intermediate Dividers (Manual Splits)
            # Only if NOT a boundary (handled above) and NOT the very last page
            if i < len(flat_pages) - 1:
                # Check if next page is a boundary
                if not flat_pages[i+1].get("is_boundary"):
                    div = SplitDividerWidget(page_index_before=i)
                    div.split_requested.connect(lambda idx=i, d=div: self.on_split_clicked(idx, d))
                    self.content_layout.addWidget(div)
        
        # Trigger initial load and Instant Height Scaling
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._force_thumbnail_resize) # Trigger immediate height-mastered sizing
        QTimer.singleShot(100, self.on_scroll_changed)

    def on_scroll_changed(self):
        """Determine visible widgets and load/unload content."""
        scroll_x = self.scroll.horizontalScrollBar().value()
        viewport_w = self.scroll.viewport().width()
        
        buffer = 500 # Load 500px ahead/behind
        
        min_vis = scroll_x - buffer
        max_vis = scroll_x + viewport_w + buffer
        
        count = self.content_layout.count()
        for i in range(count):
            item = self.content_layout.itemAt(i)
            if not item: continue
            w = item.widget()
            if not w: continue
            
            if isinstance(w, PageThumbnailWidget):
                geo = w.geometry()
                is_visible = (geo.right() > min_vis) and (geo.left() < max_vis)
                if is_visible:
                    w.load_content()
                else:
                    w.unload_content()

    def _clear_layout(self):
        while self.content_layout.count():
             child = self.content_layout.takeAt(0)
             if child.widget(): child.widget().deleteLater()
        self.selected_widgets = []
        self.last_selected_widget = None

    def remove_thumbnail(self, widget):
        pass

    def on_split_clicked(self, index, widget=None):
        if widget:
            self.record_action("SPLIT", widget)
        self.split_action_triggered.emit(index)

    def record_action(self, action_type: str, data):
        self.undo_stack.append((action_type, data))
        self.split_action_triggered.emit(-1)

    def on_selection_requested(self, widget, modifiers):
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if widget in self.selected_widgets:
                widget.set_selected(False)
                self.selected_widgets.remove(widget)
            else:
                widget.set_selected(True)
                self.selected_widgets.append(widget)
            self.last_selected_widget = widget
        elif modifiers & Qt.KeyboardModifier.ShiftModifier and self.last_selected_widget:
            all_thumbs = []
            for i in range(self.content_layout.count()):
                w = self.content_layout.itemAt(i).widget()
                if isinstance(w, PageThumbnailWidget):
                    all_thumbs.append(w)
            
            try:
                idx1 = all_thumbs.index(self.last_selected_widget)
                idx2 = all_thumbs.index(widget)
                start, end = min(idx1, idx2), max(idx1, idx2)
                
                for w in self.selected_widgets:
                    w.set_selected(False)
                self.selected_widgets = []
                
                for i in range(start, end + 1):
                    t = all_thumbs[i]
                    t.set_selected(True)
                    self.selected_widgets.append(t)
            except ValueError:
                pass
        else:
            for w in self.selected_widgets:
                w.set_selected(False)
            widget.set_selected(True)
            self.selected_widgets = [widget]
            self.last_selected_widget = widget

    def on_drag_started(self, widget):
        if widget not in self.selected_widgets:
            self.on_selection_requested(widget, Qt.KeyboardModifier.NoModifier)
        
        # Check: Single Segment in Import Mode
        if self.import_mode and len(self.selected_widgets) > 1:
            if not self._is_selection_in_single_segment():
                return

        # --- 1. GRENZEN BESTIMMEN (Objekt-basiert) ---
        current_idx = self.content_layout.indexOf(self.selected_widgets[0])
        
        # Statt Indizes merken wir uns die WIDGETS (Scheren), die die Grenzen bilden.
        self.drag_boundary_left_widget = None
        self.drag_boundary_right_widget = None

        # Suche Grenze nach LINKS
        for i in range(current_idx - 1, -1, -1):
            w = self.content_layout.itemAt(i).widget()
            if isinstance(w, SplitDividerWidget) and (w.is_active or w.is_boundary):
                self.drag_boundary_left_widget = w
                break
        
        # Suche Grenze nach RECHTS
        for i in range(current_idx + 1, self.content_layout.count()):
            w = self.content_layout.itemAt(i).widget()
            if isinstance(w, SplitDividerWidget) and (w.is_active or w.is_boundary):
                self.drag_boundary_right_widget = w
                break

        # --- 2. DRAG VORBEREITEN ---
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText("KPaperFlux_Page_Move")
        drag.setMimeData(mime)
        
        # Pixmap setzen (Visualisierung am Mauszeiger)
        if widget.original_pixmap:
            px = widget.lbl_img.pixmap()
            if not px.isNull():
                drag.setPixmap(px)
                
                # --- FIX: Offset berechnen statt Mitte erzwingen ---
                cursor_pos = QCursor.pos()
                
                # Hotspot relativ zum Thumbnail-Widget (0,0 ist oben links vom Bild)
                hotspot = widget.mapFromGlobal(cursor_pos)
                
                # Clamp: Sicherstellen, dass Hotspot innerhalb der Bildgrenzen liegt
                hotspot.setX(max(0, min(hotspot.x(), px.width())))
                hotspot.setY(max(0, min(hotspot.y(), px.height())))
                
                drag.setHotSpot(hotspot)

        # --- 3. LÜCKE ERZEUGEN & ORIGINAL VERSTECKEN ---
        from PyQt6.QtWidgets import QApplication
        
        # Scroll-Position merken
        h_bar = self.scroll.horizontalScrollBar()
        saved_scroll_val = h_bar.value()
        
        self.content_widget.setUpdatesEnabled(False)
        try:
            # v28.5: Capture state for Undo
            self._drag_old_state = []
            for w in self.selected_widgets:
                self._drag_old_state.append((w, self.content_layout.indexOf(w)))

            # Breite berechnen
            total_width = sum(w.width() for w in self.selected_widgets)
            spacing = self.content_layout.spacing()
            if len(self.selected_widgets) > 1:
                total_width += spacing * (len(self.selected_widgets) - 1)
            self.drag_placeholder_width = total_width
            
            # Placeholder erstellen (Lücke)
            self.drag_placeholder = DragPlaceholderWidget(
                self.drag_placeholder_width, 
                is_static=True, 
                parent=self.content_widget
            )

            # Originale verstecken (NICHT LÖSCHEN, nur unsichtbar machen)
            # Wir ersetzen das ERSTE Widget durch den Placeholder
            first_w = self.selected_widgets[0]
            start_idx = self.content_layout.indexOf(first_w)
            
            # Atomic Swap: Original raus (hide), Placeholder rein
            self.content_layout.insertWidget(start_idx, self.drag_placeholder)
            
            for w in self.selected_widgets:
                w.hide()
                # Wir nehmen sie temporär aus dem Layout, damit die Indizes sauber bleiben
                self.content_layout.removeWidget(w)

            self.content_layout.invalidate()
            self.content_layout.activate()
            h_bar.setValue(saved_scroll_val)
            
        finally:
            self.content_widget.setUpdatesEnabled(True)
            self.content_widget.updateGeometry()
            QApplication.processEvents()

        # --- 4. DRAG STARTEN ---
        self.is_dragging = True
        drag_result = drag.exec(Qt.DropAction.MoveAction)
        
        # --- 5. CLEANUP NACH DROP ---
        self.is_dragging = False
        self._finalize_drop()
        

    def dragEnterEvent(self, event):
        if event.mimeData().text() == "KPaperFlux_Page_Move":
            event.acceptProposedAction()
            # Placeholder is now handled atomically in on_drag_started
        super().dragEnterEvent(event)

    def _is_selection_in_single_segment(self) -> bool:
        """Check if all selected widgets are between the same boundary dividers."""
        if not self.selected_widgets: return True
        
        # Map widgets to segments
        segments = []
        curr_segment = 0
        widget_to_seg = {}
        
        for i in range(self.content_layout.count()):
            w = self.content_layout.itemAt(i).widget()
            if isinstance(w, SplitDividerWidget) and (getattr(w, 'is_boundary', False) or getattr(w, 'is_active', False)):
                curr_segment += 1
            widget_to_seg[w] = curr_segment
            
        if self.selected_widgets[0] not in widget_to_seg: return True
        target_seg = widget_to_seg.get(self.selected_widgets[0])
        for w in self.selected_widgets:
            if widget_to_seg.get(w) != target_seg:
                return False
        return True

    def dragMoveEvent(self, event):
        if event.mimeData().text() == "KPaperFlux_Page_Move" and self.drag_placeholder:
            event.acceptProposedAction()
            
            # Mausposition relativ zum Content-Widget
            pos = event.position().toPoint()
            local_pos = self.content_widget.mapFrom(self, pos)
            
            self._check_and_slide_gap(local_pos)
            self._update_auto_scroll_velocity(pos) # Auto-Scroll Logik
        else:
            super().dragMoveEvent(event)

    def _check_and_slide_gap(self, mouse_pos):
        """
        Prüft Nachbarn auf 80% Überlappung und verschiebt die Lücke.
        """
        if not self.drag_placeholder: return

        # Aktueller Index der Lücke
        gap_idx = self.content_layout.indexOf(self.drag_placeholder)
        
        # --- GRENZEN DYNAMISCH BERECHNEN ---
        # Wir fragen die Grenz-Scheren, wo sie JETZT gerade sind.
        idx_min = 0 
        idx_max = self.content_layout.count()

        if self.drag_boundary_left_widget:
            limit_idx = self.content_layout.indexOf(self.drag_boundary_left_widget)
            if limit_idx != -1: 
                idx_min = limit_idx + 1

        if self.drag_boundary_right_widget:
            limit_idx = self.content_layout.indexOf(self.drag_boundary_right_widget)
            if limit_idx != -1: 
                idx_max = limit_idx

        # --- A. NACHBAR RECHTS SUCHEN ---
        neighbor_right = None
        idx_right = -1
        
        for i in range(gap_idx + 1, idx_max): 
            if i >= self.content_layout.count(): break
            w = self.content_layout.itemAt(i).widget()
            if isinstance(w, PageThumbnailWidget) and w.isVisible():
                neighbor_right = w
                idx_right = i
                break 
                
        # --- B. NACHBAR LINKS SUCHEN ---
        neighbor_left = None
        idx_left = -1
        
        for i in range(gap_idx - 1, idx_min - 1, -1):
            if i < 0: break
            w = self.content_layout.itemAt(i).widget()
            if isinstance(w, PageThumbnailWidget) and w.isVisible():
                neighbor_left = w
                idx_left = i
                break

        # --- C. PRÜFUNG: BEWEGUNG NACH RECHTS (Nachbar ist rechts von uns) ---
        if neighbor_right:
            geo = neighbor_right.geometry()
            # KORREKTUR: Wir wollen swappen, wenn wir EINDRINGEN.
            # Wenn wir von links kommen, reicht es, 20% in den Nachbarn reinzuziehen.
            threshold_x = geo.x() + (geo.width() * 0.2) 
            
            if mouse_pos.x() > threshold_x:
                self._slide_gap_to(idx_right + 1) # Hinter den Nachbarn
                return

        # --- D. PRÜFUNG: BEWEGUNG NACH LINKS (Nachbar ist links von uns) ---
        if neighbor_left:
            geo = neighbor_left.geometry()
            # KORREKTUR: Wir kommen von rechts (Werte werden kleiner).
            # Wir wollen swappen, wenn wir die rechte Kante um 20% unterschritten haben.
            # Also bei 80% der Breite des Nachbarn stehen.
            threshold_x = geo.x() + (geo.width() * 0.8) 
            
            if mouse_pos.x() < threshold_x:
                self._slide_gap_to(idx_left) # Vor den Nachbarn
                return

    def _slide_gap_to(self, new_index):
        """Führt den eigentlichen Layout-Move aus."""
        if new_index < 0 or new_index > self.content_layout.count():
            return
            
        self.content_widget.setUpdatesEnabled(False)
        try:
            self.content_layout.insertWidget(new_index, self.drag_placeholder)
            self.content_layout.invalidate()
            self.content_layout.activate()
            self.content_widget.updateGeometry()
        finally:
            self.content_widget.setUpdatesEnabled(True)

    def _update_auto_scroll_velocity(self, pos):
        """Calculate scroll speed based on proximity to edges."""
        # pos is in SplitterStripWidget coordinates
        margin = 60
        w = self.width()
        
        if pos.x() < margin:
            # Scroll left: speed depends on how deep into margin
            self._auto_scroll_speed = -int(((margin - pos.x()) / margin) * 30) - 2
        elif pos.x() > w - margin:
            # Scroll right
            self._auto_scroll_speed = int(((pos.x() - (w - margin)) / margin) * 30) + 2
        else:
            self._auto_scroll_speed = 0
            
        if self._auto_scroll_speed != 0:
            if not self._scroll_timer.isActive():
                self._scroll_timer.start()
        else:
            self._scroll_timer.stop()

    def _handle_auto_scroll(self):
        hbar = self.scroll.horizontalScrollBar()
        old_val = hbar.value()
        hbar.setValue(old_val + self._auto_scroll_speed)
        
        # Also need to update drag position/insertion index since viewport content moved!
        # We can trigger a dummy dragMoveEvent or just call _get_insertion_index
        if self._auto_scroll_speed != 0:
            # Fetch current cursor pos relative to widget
            p = self.mapFromGlobal(QCursor.pos())
            local_p = self.content_widget.mapFrom(self, p)
            
            self._check_and_slide_gap(local_p)

    def dragLeaveEvent(self, event):
        self._scroll_timer.stop()
        # V28.5: We DON'T delete the placeholder here.
        # This prevents the gap from closing when the mouse momentarily
        # leaves the strip area (e.g. dragging 'trapped' pages upwards).
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        # v28.5: Internal D&D is handled by _finalize_drop in on_drag_started.
        if event.mimeData().text() == "KPaperFlux_Page_Move":
            event.acceptProposedAction()
        super().dropEvent(event)

    def _finalize_drop(self):
        """Wird aufgerufen, wenn drag.exec() zurückkehrt."""
        self._scroll_timer.stop()
        self._auto_scroll_speed = 0

        # 1. Wo ist die Lücke gelandet?
        final_idx = -1
        if self.drag_placeholder:
            final_idx = self.content_layout.indexOf(self.drag_placeholder)
            self.content_layout.removeWidget(self.drag_placeholder)
            self.drag_placeholder.deleteLater()
            self.drag_placeholder = None
        
        if final_idx == -1:
            self._show_selection()
            return

        # 2. Originale an dieser Position einfügen
        self.content_widget.setUpdatesEnabled(False)
        try:
            for i, w in enumerate(self.selected_widgets):
                self.content_layout.insertWidget(final_idx + i, w)
                w.show()
            
            # --- FIX: BOUNDARY FLAG TRANSFER -----------------------------------
            # Wir müssen sicherstellen, dass die Seite, die jetzt ganz vorne im 
            # Segment steht, das "is_boundary"-Flag erbt.
            
            # A. Grenzen des aktuellen Segments finden (wo haben wir gerade gearbeitet?)
            seg_start_index = 0
            if self.drag_boundary_left_widget:
                idx = self.content_layout.indexOf(self.drag_boundary_left_widget)
                if idx != -1: seg_start_index = idx + 1
            
            seg_end_index = self.content_layout.count()
            if self.drag_boundary_right_widget:
                idx = self.content_layout.indexOf(self.drag_boundary_right_widget)
                if idx != -1: seg_end_index = idx
            
            # B. Alle Seiten in diesem Segment scannen
            segment_pages = []
            boundary_flag_detected = False
            
            for i in range(seg_start_index, seg_end_index):
                item = self.content_layout.itemAt(i)
                if not item: continue
                w = item.widget()
                
                # Nur Thumbnails beachten
                if isinstance(w, PageThumbnailWidget):
                    segment_pages.append(w)
                    # Hatte IRGENDEINE Seite hier drin vorher das Boundary-Flag?
                    if w.page_info.get("is_boundary", False):
                        boundary_flag_detected = True
                        w.page_info["is_boundary"] = False # Erstmal löschen
            
            # C. Dem neuen "Kopf" das Flag geben
            if segment_pages and boundary_flag_detected:
                # Die erste Seite im visuellen Layout ist jetzt der Chef
                segment_pages[0].page_info["is_boundary"] = True
            
            # -------------------------------------------------------------------

            # 3. NORMALIZE
            self._rebuild_dividers()
            
        finally:
            self.content_widget.setUpdatesEnabled(True)
            
        # 4. UNDO
        if hasattr(self, '_drag_old_state') and self._drag_old_state:
            self.record_action("MOVE", (list(self.selected_widgets), self._drag_old_state))
            self._drag_old_state = []

        self.on_scroll_changed()
        print("[DEBUG] Drop Finalized & Normalized.")


    def _rebuild_dividers(self):
        """
        Garbage Collection for the layout:
        1. Snapshots the current order of thumbnails and the state of manual cuts.
        2. Removes ALL dividers from the layout.
        3. Re-inserts fresh dividers cleanly between thumbnails based on the new order.
        """
        # 1. Snapshot: Identify thumbnails and their manual cut states
        thumbnails = []
        active_manual_cuts = set() # Stores INDICES of thumbnails that had an active cut after them
        
        current_visual_index = -1
        
        # Iterate to capture state BEFORE clearing dividers
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if not item: continue
            w = item.widget()
            
            if isinstance(w, PageThumbnailWidget):
                thumbnails.append(w)
                current_visual_index += 1
            elif isinstance(w, SplitDividerWidget):
                # If we find an active manual cut, remember it was associated with the PREVIOUS thumbnail index
                if w.is_active and not w.is_boundary:
                    active_manual_cuts.add(current_visual_index)

        # 2. Nuke Dividers (Atomically)
        self.content_widget.setUpdatesEnabled(False)
        try:
            # Remove ALL dividers. We iterate backwards to safely remove items.
            for i in reversed(range(self.content_layout.count())):
                item = self.content_layout.itemAt(i)
                if not item: continue
                w = item.widget()
                
                if isinstance(w, SplitDividerWidget):
                    self.content_layout.removeWidget(w)
                    w.deleteLater() # destroy the object
                elif isinstance(w, PageThumbnailWidget):
                    # We remove thumbnails from layout temporarily to re-add them in strict order
                    self.content_layout.removeWidget(w)
            
            # 3. Rebuild: Interleave structure cleanly
            for i, thumb in enumerate(thumbnails):
                
                # A. Boundary Split (BEFORE thumbnail if it is a file start)
                if thumb.page_info.get("is_boundary"):
                    div = SplitDividerWidget(page_index_before=i-1)
                    div.is_boundary = True
                    div.set_active(True)
                    div.split_requested.connect(lambda idx=i-1, d=div: self.on_split_clicked(idx, d))
                    self.content_layout.addWidget(div)
                
                # B. The Thumbnail
                self.content_layout.addWidget(thumb)
                thumb.show() # Ensure it's visible
                
                # C. Manual Split (AFTER thumbnail)
                # Only add if not the last item
                if i < len(thumbnails) - 1:
                    next_thumb = thumbnails[i+1]
                    if not next_thumb.page_info.get("is_boundary"):
                        div = SplitDividerWidget(page_index_before=i)
                        
                        # Restore manual cut state if it existed at this visual index
                        if i in active_manual_cuts:
                            div.set_active(True)
                            
                        div.split_requested.connect(lambda idx=i, d=div: self.on_split_clicked(idx, d))
                        self.content_layout.addWidget(div)
                        
        finally:
            self.content_widget.setUpdatesEnabled(True)
            self.content_layout.invalidate()
            self.content_layout.activate()

    def eventFilter(self, obj, event):
        # v28.5: Tastatur-Steuerung für die ScrollArea abfangen
        from PyQt6.QtCore import QEvent
        if obj == self.scroll and event.type() == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True # Wir haben das Event verarbeitet
            
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        # Schrittweite bestimmen: Thumbnail-Breite + Trenner-Breite
        thumb_w = 250
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, PageThumbnailWidget):
                    thumb_w = w.width()
                    break
        
        spacing = self.content_layout.spacing()
        # Ein "Blatt-Schritt" ist Thumbnail + Trenner (40px)
        step = thumb_w + spacing + 40 
        
        viewport_w = self.scroll.viewport().width()
        hbar = self.scroll.horizontalScrollBar()
        
        if event.key() == Qt.Key.Key_Left:
            hbar.setValue(hbar.value() - step)
        elif event.key() == Qt.Key.Key_Right:
            hbar.setValue(hbar.value() + step)
        elif event.key() in [Qt.Key.Key_Up, Qt.Key.Key_PageUp]:
            hbar.setValue(hbar.value() - viewport_w)
        elif event.key() in [Qt.Key.Key_Down, Qt.Key.Key_PageDown]:
            hbar.setValue(hbar.value() + viewport_w)
        elif event.key() == Qt.Key.Key_Home:
            hbar.setValue(0)
        elif event.key() == Qt.Key.Key_End:
            hbar.setValue(hbar.maximum())
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        if not self.selected_widgets:
            return
            
        menu = QMenu(self)
        
        rotate_action = menu.addAction(self.tr("Rotate selection (90° CW)"))
        rotate_action.triggered.connect(self._rotate_selected_right)
        
        delete_action = menu.addAction(self.tr("Delete selection"))
        delete_action.triggered.connect(self._delete_selected)
        
        menu.addSeparator()
        
        reverse_action = menu.addAction(self.tr("Reverse sorting (Selection)"))
        reverse_action.triggered.connect(self._reverse_selected_sorting)
        
        menu.exec(event.globalPos())

    def _reverse_selected_sorting(self):
        if not self.selected_widgets:
            return
            
        if self.import_mode and not self._is_selection_in_single_segment():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, self.tr("Invalid Selection"), 
                                self.tr("In Import Mode, you can only reverse pages within a single document segment."))
            return
            
        layout_items = []
        for i in range(self.content_layout.count()):
            layout_items.append(self.content_layout.itemAt(i).widget())
            
        # Get indices of selected thumbnails
        selected_indices = sorted([layout_items.index(w) for w in self.selected_widgets if w in layout_items])
        
        if not selected_indices:
            return
            
        orig_widgets = [layout_items[i] for i in selected_indices]
        rev_widgets = list(reversed(orig_widgets))
        
        undo_info = (selected_indices, orig_widgets)
        
        # Remove from layout
        for w in orig_widgets:
            self.content_layout.removeWidget(w)
            
        # Re-insert in reversed order at original indices
        for i, w in enumerate(rev_widgets):
            self.content_layout.insertWidget(selected_indices[i], w)
                
        # --- FIX: Rebuild Dividers ---
        self._rebuild_dividers()
        
        self.record_action("REVERSE", undo_info)
        self.on_scroll_changed()

    def _delete_selected(self):
        if not self.selected_widgets:
            return
        
        # Snapshot state for undo: technically we just need the list of widgets
        # since toggle_delete() is reversible.
        widgets = list(self.selected_widgets)
        for w in widgets:
            w.toggle_delete()
            
        self.record_action("DELETE_SELECTION", widgets)

    def _rotate_selected_right(self):
        if not self.selected_widgets:
            return
            
        widgets = list(self.selected_widgets)
        for w in widgets:
            w.rotate_right()
            
        self.record_action("ROTATE_SELECTION", widgets)

    def revert_last_edit(self):
        if not self.undo_stack:
            return
            
        action_type, data = self.undo_stack.pop()
        from PyQt6.QtCore import QSignalBlocker
        
        if action_type == "SPLIT":
            blocker = QSignalBlocker(data)
            data.set_active(not data.is_active)
            blocker.unblock()
        elif action_type == "ROTATE":
            blocker = QSignalBlocker(data)
            data.rotate_right()
            data.rotate_right()
            data.rotate_right()
            blocker.unblock()
        elif action_type == "DELETE":
            blocker = QSignalBlocker(data)
            data.toggle_delete()
            blocker.unblock()
        elif action_type == "MOVE":
            widgets_to_move, old_state = data
            for w in widgets_to_move:
                self.content_layout.removeWidget(w)
            old_state.sort(key=lambda x: x[1])
            for w, idx in old_state:
                self.content_layout.insertWidget(idx, w)
            self._rebuild_dividers() # Normalize after undoing move
        elif action_type == "REVERSE":
            indices, orig_widgets = data
            curr_widgets = []
            for idx in indices:
                curr_widgets.append(self.content_layout.itemAt(idx).widget())
            for w in curr_widgets:
                self.content_layout.removeWidget(w)
            for i, w in enumerate(orig_widgets):
                self.content_layout.insertWidget(indices[i], w)
            self._rebuild_dividers() # Normalize after undoing reverse
        elif action_type == "DELETE_SELECTION":
            # data is list of widgets
            for w in data:
                blocker = QSignalBlocker(w)
                w.toggle_delete()
                blocker.unblock()
        elif action_type == "ROTATE_SELECTION":
            # data is list of widgets
            for w in data:
                blocker = QSignalBlocker(w)
                w.rotate_right()
                w.rotate_right()
                w.rotate_right()
                blocker.unblock()
            
        self.split_action_triggered.emit(-1)
        self._force_thumbnail_resize()
    
    def get_active_splits(self) -> list[int]:
        splits = []
        for i in range(self.content_layout.count()):
             item = self.content_layout.itemAt(i)
             if item and item.widget() and isinstance(item.widget(), SplitDividerWidget):
                 div = item.widget()
                 if div.is_active:
                     splits.append(div.page_index_before + 1)
        return sorted(splits)

    def _show_selection(self):
        """Restore visibility of selected widgets."""
        for w in self.selected_widgets:
            w.show()
