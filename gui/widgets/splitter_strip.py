from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QPushButton, QSizePolicy, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QIcon, QCursor, QColor
import fitz  # PyMuPDF for thumbnails
import os

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

class ControlsOverlay(QWidget):
    """Floating controls for the Thumbnail."""
    def __init__(self, parent=None, callback_rotate=None, callback_delete=None):
        super().__init__(parent)
        self.callback_rotate = callback_rotate
        self.callback_delete = callback_delete
        self._init_ui()
        
    def _create_shadow(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(1) 
        shadow.setColor(QColor(0, 0, 0, 255))
        shadow.setOffset(2, 2)
        return shadow

    def _init_ui(self):
        # Transparent barrier so it doesn't block image view, but spans width
        self.setStyleSheet("""
            QToolTip { 
                color: #ffffff; 
                background-color: #000000; 
                border: 1px solid white; 
                font-weight: bold;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        # Add Stretch between buttons to push them to corners
        
        # ROTATE BUTTON (Top Left)
        btn_rot = QPushButton("↻")
        btn_rot.setFixedSize(40, 40)
        btn_rot.clicked.connect(self.callback_rotate)
        btn_rot.setGraphicsEffect(self._create_shadow())
        btn_rot.setStyleSheet("""
            QPushButton {
                background: transparent; 
                color: #ffffff; 
                border: 2px solid #ffffff; 
                border-radius: 20px; 
                font-size: 28px; 
                font-weight: 900;
                padding-bottom: 5px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 80);
                color: #ffffff;
                border-color: #ffffff;
            }
        """)
        btn_rot.setToolTip("Rotate 90°")
        layout.addWidget(btn_rot)
        
        layout.addStretch()
        
        # DELETE BUTTON (Top Right)
        btn_del = QPushButton("🗑")
        btn_del.setFixedSize(40, 40)
        btn_del.clicked.connect(self.callback_delete)
        btn_del.setGraphicsEffect(self._create_shadow())
        btn_del.setStyleSheet("""
            QPushButton {
                background: transparent; 
                color: #ff5555; 
                border: 2px solid #ff5555; 
                border-radius: 20px; 
                font-size: 26px;
                font-weight: bold;
                padding-bottom: 5px;
            }
            QPushButton:hover {
                background: rgba(255, 80, 80, 80);
                color: #ff0000;
                border: 2px solid #ff0000;
            }
        """)
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

    def __init__(self, page_info: dict, pipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.page_info = page_info 
        
        self._page_num = page_info.get("page", 1)
        self.current_rotation = page_info.get("rotation", 0)
        
        # Soft Delete State
        self.is_deleted = False

        # Default A4 Aspect Ratio (Width / Height) = 1 / sqrt(2) ~= 0.707
        self.aspect_ratio = 0.707 
        if self.current_rotation in [90, 270]:
            self.aspect_ratio = 1.0 / self.aspect_ratio

        self.loaded = False
        self.original_pixmap = None
        
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Container
        self.img_container = QWidget()
        self.img_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.img_layout = QVBoxLayout(self.img_container)
        self.img_layout.setContentsMargins(0,0,0,0)
        self.img_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_img = QLabel()
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_img.setStyleSheet("border: 1px solid #ccc; background: white;")
        self.lbl_img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
            self.lbl_img.setStyleSheet("border: 1px solid #ccc; background: white;")
            
        self.resizeEvent(None)
        self.delete_toggled.emit()
        
    def resizeEvent(self, event):
        # Enforce Aspect Ratio Geometry on the WIDGET itself
        h = self.height()
        target_w = int(h * self.aspect_ratio)
        
        if abs(self.minimumWidth() - target_w) > 2:
             self.setMinimumWidth(target_w)
             self.setMaximumWidth(target_w)
             return 

        # 1. Image Rendering
        if self.loaded and self.original_pixmap and not self.original_pixmap.isNull():
             if (h > 10) and (abs(h - self.last_drawn_height) > 2 or self.last_drawn_height == 0):
                self.last_drawn_height = h
                
                from PyQt6.QtGui import QTransform
                transformed = self.original_pixmap.transformed(QTransform().rotate(self.current_rotation), Qt.TransformationMode.SmoothTransformation)
                
                scaled = transformed.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                
                self.lbl_img.setFixedSize(scaled.size())
                self.lbl_img.setPixmap(scaled)
        
        # 2. Overlay
        if self.is_deleted:
            self.del_overlay.resize(self.size())
            self.del_overlay.move(0,0)
            self.del_overlay.raise_()

        # Update Controls GEOMETRY to fill TOP BAR
        # Spanning full width allows buttons to stick to Left and Right
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
        self.undo_stack = [] # List of (type, widget)
        self.init_ui()
        
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
        
        # Debounce timer for scrolling?
        # Direct connection is usually fine for <1000 items if logic is fast.
        
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
            thumb.remove_requested.connect(lambda t=thumb: self.remove_thumbnail(t))
            self.content_layout.addWidget(thumb)
            
            # 3. Intermediate Dividers (Manual Splits)
            # Only if NOT a boundary (handled above) and NOT the very last page
            if i < len(flat_pages) - 1:
                # Check if next page is a boundary
                if not flat_pages[i+1].get("is_boundary"):
                    div = SplitDividerWidget(page_index_before=i)
                    div.split_requested.connect(lambda idx=i, d=div: self.on_split_clicked(idx, d))
                    self.content_layout.addWidget(div)
        
        # Trigger initial load
        # Use QTimer to allow layout to settle
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self.on_scroll_changed)

    def on_scroll_changed(self):
        """Determine visible widgets and load/unload content."""
        scroll_x = self.scroll.horizontalScrollBar().value()
        viewport_w = self.scroll.viewport().width()
        
        buffer = 500 # Load 500px ahead/behind
        
        min_vis = scroll_x - buffer
        max_vis = scroll_x + viewport_w + buffer
        
        # Iterate children
        # count() is fast. itemAt is fast. geometry() is fast.
        count = self.content_layout.count()
        
        for i in range(count):
            item = self.content_layout.itemAt(i)
            if not item: continue
            w = item.widget()
            if not w: continue
            
            if isinstance(w, PageThumbnailWidget):
                # Check visibility
                # Since we are in Horizontal Layout, check x geometry relative to parent content_widget?
                # scroll area scrolls content_widget.
                # So if w.x() is within current visible window of content_widget.
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

    def remove_thumbnail(self, widget):
        # NOT EASILY UNDOABLE in current architecture if we physically remove.
        # But Phase 1 uses soft-delete, so we just toggle it.
        # User said "Revert commands" skip/delete commands.
        pass

    def on_split_clicked(self, index, widget=None):
        if widget:
            self.record_action("SPLIT", widget)
        self.split_action_triggered.emit(index)

    def record_action(self, action_type: str, widget: QWidget):
        self.undo_stack.append((action_type, widget))
        # Signal carries -1 to indicate "Internal Action/Metadata refresh needed"
        self.split_action_triggered.emit(-1)

    def revert_last_edit(self):
        if not self.undo_stack:
            return
            
        action_type, widget = self.undo_stack.pop()
        
        # Disconnect signals temporarily to avoid re-recording
        from PyQt6.QtCore import QSignalBlocker
        blocker = QSignalBlocker(widget)
        
        if action_type == "SPLIT":
            widget.set_active(not widget.is_active)
        elif action_type == "ROTATE":
            # 90 deg right -> 90 deg left = 270 deg right
            widget.rotate_right()
            widget.rotate_right()
            widget.rotate_right()
        elif action_type == "DELETE":
            widget.toggle_delete()
            
        blocker.unblock()
        self.split_action_triggered.emit(-1)
    
    def get_active_splits(self) -> list[int]:
        splits = []
        for i in range(self.content_layout.count()):
             item = self.content_layout.itemAt(i)
             if item and item.widget() and isinstance(item.widget(), SplitDividerWidget):
                 div = item.widget()
                 if div.is_active:
                     splits.append(div.page_index_before + 1)
        return sorted(splits)
