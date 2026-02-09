"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/pdf_viewer.py
Version:        1.3.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    High-performance PDF viewer based on fitz (PyMuPDF). 
                Supports side-by-side comparison, synchronous scrolling, 
                text extraction, and automated match analysis.
------------------------------------------------------------------------------
"""
from typing import List, Optional, Tuple, Callable, Any, Union
from pathlib import Path
import tempfile
import sys
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QMessageBox, QLineEdit, QSplitter, QGraphicsDropShadowEffect, QScrollArea
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QSize, QRect, QPoint, QEvent, 
    QPropertyAnimation, QEasingCurve, QObject
)
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QGuiApplication, 
    QIntValidator, QPalette, QWheelEvent, QPen, QMouseEvent, 
    QResizeEvent, QPaintEvent, QCloseEvent
)

import fitz

from core.models.virtual import SourceReference

class ToastOverlay(QLabel):
    """
    Floating notification overlay for non-intrusive user feedback.
    """
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(120, 35)
        self.hide()
        
        # Style
        bg_color = self.palette().color(QPalette.ColorRole.ToolTipBase).name()
        text_color = self.palette().color(QPalette.ColorRole.ToolTipText).name()
        self.setStyleSheet(f"""
            background: {bg_color}; 
            color: {text_color}; 
            border: 1px solid #adb5bd; 
            border-radius: 6px; 
            font-weight: bold;
        """)
        
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(400)

    def show_message(self, text: str, pos: QPoint) -> None:
        """
        Displays a temporary message with a fade-out effect.
        
        Args:
            text: The message to display.
            pos: The local position where the toast should appear.
        """
        self.setText(text)
        self.move(pos.x() - self.width() // 2, pos.y() - 50)
        self.show()
        self.raise_()
        QTimer.singleShot(1500, self.hide)

class PdfDisplayLabel(QLabel):
    """
    Specialized display component for the PDF canvas.
    Handles exact word-level highlighting and mouse interaction states.
    """
    text_selected = pyqtSignal(QRect)
    selection_preview = pyqtSignal(QRect)  # Live preview during dragging
    word_double_clicked = pyqtSignal(QPoint)
    clicked_empty = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.selection_start: Optional[QPoint] = None
        self.selection_end: Optional[QPoint] = None
        self.is_selecting = False
        self.is_double_click_drag = False
        self.double_click_pos: Optional[QPoint] = None
        self.highlight_pdf_rects: List[fitz.Rect] = []  # Stored in PDF points
        self.coord_converter: Optional[Callable[[float, float], QPoint]] = None
        
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def set_pdf_highlights(self, fitz_rects: List[fitz.Rect]) -> None:
        """
        Updates the list of word rectangles to highlight.
        
        Args:
            fitz_rects: List of fitz.Rect objects in PDF coordinate space.
        """
        self.highlight_pdf_rects = fitz_rects
        self.update()

    def clear_selection(self) -> None:
        """Clears all visual selection markers and states."""
        self.highlight_pdf_rects = []
        self.selection_start = None
        self.selection_end = None
        self.is_double_click_drag = False
        self.double_click_pos = None
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handles initial mouse press to start selection or clear previous state."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if this press follows a recent double-click
            is_near_dbl = False
            if self.double_click_pos:
                if (event.pos() - self.double_click_pos).manhattanLength() < 10:
                    is_near_dbl = True
            
            if is_near_dbl:
                # Maintain word-selection mode
                self.is_double_click_drag = True
            else:
                # Fresh start -> Clear everything
                self.highlight_pdf_rects = [] 
                self.is_double_click_drag = False
                self.double_click_pos = None

            self.selection_start = event.pos()
            self.selection_end = event.pos()
            self.is_selecting = True
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handles mouse movement to update selection previews."""
        if self.is_selecting:
            self.selection_end = event.pos()
            rect = QRect(self.selection_start, self.selection_end).normalized()
            
            # Activate word-drag mode if distance from double-click is sufficient
            if self.double_click_pos:
                dist = (event.pos() - self.double_click_pos).manhattanLength()
                if dist > 1:
                    if not self.is_double_click_drag:
                        self.is_double_click_drag = True
            
            if self.is_double_click_drag:
                # Real-time update for word highlighting (editor style)
                self.selection_preview.emit(rect)
            
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Finalizes the selection and triggers extraction signals."""
        if self.is_selecting:
            self.is_selecting = False
            
            if self.selection_start is not None and self.selection_end is not None:
                rect = QRect(self.selection_start, self.selection_end).normalized()
                dist = (self.selection_end - self.selection_start).manhattanLength()
                
                if self.is_double_click_drag:
                    # Finalize word-flow selection if significant movement occurred
                    if dist > 5:
                        self.text_selected.emit(rect)
                elif rect.width() > 3 and rect.height() > 3:
                    # Finalize box selection
                    self.text_selected.emit(rect)
                else:
                    # Single click clears selection unless a word was just highlighted
                    if dist < 2 and not self.highlight_pdf_rects:
                        self.clicked_empty.emit()
            
            self.selection_start = None
            self.selection_end = None
            self.update()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handles double-click to immediately select the word under the cursor."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_click_pos = event.pos()
            self.selection_start = event.pos()
            self.selection_end = event.pos()
            self.is_selecting = True
            self.word_double_clicked.emit(event.pos())
            self.update()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draws persistent word highlights and active selection boxes."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        
        # 1. Persistent word highlights (projected from PDF points)
        if self.highlight_pdf_rects and self.coord_converter:
            brush_color = QColor(
                highlight_color.red(), 
                highlight_color.green(), 
                highlight_color.blue(), 
                130
            )
            pen_color = QColor(
                highlight_color.red(), 
                highlight_color.green(), 
                highlight_color.blue(), 
                200
            )
            painter.setBrush(brush_color)
            painter.setPen(pen_color)
            
            for pr in self.highlight_pdf_rects:
                tl = self.coord_converter(pr.x0, pr.y0)
                br = self.coord_converter(pr.x1, pr.y1)
                rect = QRect(tl, br)
                painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 2, 2)
                
        # 2. Active selection box (only in standard box-selection mode)
        if (self.is_selecting and 
            self.selection_start is not None and 
            self.selection_end is not None):
            
            rect = QRect(self.selection_start, self.selection_end).normalized()
            if not self.is_double_click_drag:
                pen = QPen(highlight_color, 1)
                painter.setPen(pen)
                painter.setBrush(QColor(
                    highlight_color.red(), 
                    highlight_color.green(), 
                    highlight_color.blue(), 
                    50
                ))
                painter.drawRect(rect)

class PdfCanvas(QScrollArea):
    """
    Main canvas for PDF display. Manages rendering and text extraction.
    """
    page_changed = pyqtSignal(int)
    zoom_changed = pyqtSignal(float)
    resized = pyqtSignal()

    FIT_FIXED_FRAME = 15.0    
    FIT_COMFORT_SCALE = 1.0
    SUPERSAMPLING = 3.0 

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.setBackgroundRole(QPalette.ColorRole.Mid)
        self.viewport().setBackgroundRole(QPalette.ColorRole.Mid)
        self.setFrameShape(QFrame.Shape.NoFrame)
        
        self.display_label = PdfDisplayLabel()
        self.display_label.coord_converter = self._get_widget_coords
        self.display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display_label.setBackgroundRole(QPalette.ColorRole.Mid)
        self.display_label.setAutoFillBackground(True)
        
        # Connect signals
        self.display_label.text_selected.connect(self.extract_text_from_rect)
        self.display_label.selection_preview.connect(self.preview_text_selection)
        self.display_label.word_double_clicked.connect(self.extract_word_at_pos)
        self.display_label.clicked_empty.connect(self.display_label.clear_selection)
        
        self.setWidget(self.display_label)
        
        # UI overlays
        self.toast = ToastOverlay(self)
        
        self.doc: Optional[fitz.Document] = None
        self.current_page_idx = 0
        self.zoom_factor = 1.0
        self.rotation = 0

    def show_copy_feedback(self, widget_pos: QPoint) -> None:
        """Displays toast notification for successful copy action."""
        canvas_pos = self.mapFromGlobal(self.display_label.mapToGlobal(widget_pos))
        self.toast.show_message("Copied!", canvas_pos)

    def set_document(self, fitz_doc: Optional[fitz.Document]) -> None:
        """
        Loads a new PDF document into the canvas.
        
        Args:
            fitz_doc: The fitz Document object to load or None to clear.
        """
        self.doc = fitz_doc
        self.current_page_idx = 0
        self.rotation = 0 # Reset rotation on new document
        if self.doc:
            self.render_current_page()
        else:
            self.display_label.setPixmap(QPixmap())

    def jump_to_page(self, index: int, block_signals: bool = False) -> None:
        """
        Navigates to the specified page.
        
        Args:
            index: 0-indexed page number.
            block_signals: If True, page_changed signal is not emitted.
        """
        if self.doc and 0 <= index < len(self.doc):
            self.current_page_idx = index
            self.display_label.clear_selection()
            self.rotation = 0 # Reset visual rotation when changing page
            if not block_signals:
                self.page_changed.emit(index)
            self.render_current_page()

    def set_rotation(self, rotation: int) -> None:
        """Sets the visual rotation for the current page."""
        self.rotation = rotation % 360
        self.render_current_page()

    def set_zoom(self, factor: float, block_signals: bool = False) -> None:
        """
        Sets the zoom factor for rendering.
        
        Args:
            factor: Zoom multiplier (e.g. 1.0 for 100%).
            block_signals: If True, zoom_changed signal is not emitted.
        """
        factor = max(0.1, min(10.0, factor))
        if abs(factor - self.zoom_factor) > 0.0001:
            self.zoom_factor = factor
            if not block_signals:
                self.zoom_changed.emit(factor)
            self.render_current_page()

    def render_current_page(self) -> None:
        """Renders the current page as a pixmap and updates the display."""
        if not self.doc:
            self.display_label.clear()
            return

        self.display_label.setUpdatesEnabled(False)
        try:
            page = self.doc[self.current_page_idx]
            dpr = self.devicePixelRatioF()
            mat = fitz.Matrix(
                self.zoom_factor * dpr * self.SUPERSAMPLING, 
                self.zoom_factor * dpr * self.SUPERSAMPLING
            ).prerotate(self.rotation)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            qimg = QImage(
                pix.samples, 
                pix.width, 
                pix.height, 
                pix.stride, 
                QImage.Format.Format_RGB888
            ).copy()
            qimg.setDevicePixelRatio(dpr * self.SUPERSAMPLING)
            self.display_label.setPixmap(QPixmap.fromImage(qimg))
        finally:
            self.display_label.setUpdatesEnabled(True)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handles mouse wheel for scrolling and Ctrl+Wheel for zooming."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            self.set_zoom(self.zoom_factor * (1.1 if delta > 0 else 0.9))
            event.accept()
        else:
            super().wheelEvent(event)

    def _get_pdf_coords(self, pos: QPoint) -> Optional[Tuple[float, float]]:
        """Maps widget coordinates (logical pixels) to PDF points."""
        if not self.doc:
            return None
        pixmap = self.display_label.pixmap()
        if not pixmap:
            return None
        dpr_total = pixmap.devicePixelRatio()
        
        # Pixmap size in logical pixels
        pw_logic = pixmap.width() / dpr_total
        ph_logic = pixmap.height() / dpr_total
        
        # Centering offset in the label
        offset_x = (self.display_label.width() - pw_logic) / 2
        offset_y = (self.display_label.height() - ph_logic) / 2
        
        pdf_x = (pos.x() - offset_x) / self.zoom_factor
        pdf_y = (pos.y() - offset_y) / self.zoom_factor
        return pdf_x, pdf_y

    def _get_widget_coords(self, pdf_x: float, pdf_y: float) -> QPoint:
        """Maps PDF points to widget coordinates (logical pixels)."""
        pixmap = self.display_label.pixmap()
        if not pixmap:
            return QPoint(0, 0)
        dpr_total = pixmap.devicePixelRatio()
        
        pw_logic = pixmap.width() / dpr_total
        ph_logic = pixmap.height() / dpr_total
        
        offset_x = (self.display_label.width() - pw_logic) / 2
        offset_y = (self.display_label.height() - ph_logic) / 2
        
        return QPoint(
            int(pdf_x * self.zoom_factor + offset_x), 
            int(pdf_y * self.zoom_factor + offset_y)
        )

    def extract_word_at_pos(self, pos: QPoint) -> None:
        """Extracts and copies the word at the specified position."""
        if not self.doc:
            return
        coords = self._get_pdf_coords(pos)
        if not coords:
            return
            
        page = self.doc[self.current_page_idx]
        for w in page.get_text("words"):
            if w[0] <= coords[0] <= w[2] and w[1] <= coords[1] <= w[3]:
                QGuiApplication.clipboard().setText(w[4])
                self.display_label.set_pdf_highlights([fitz.Rect(w[0], w[1], w[2], w[3])])
                self.show_copy_feedback(pos)
                return

    def _get_selection_data(self, qrect: QRect) -> Tuple[List[fitz.Rect], str]:
        """Calculates highlighted rectangles and combined text for a selection area."""
        p1 = self._get_pdf_coords(qrect.topLeft())
        p2 = self._get_pdf_coords(qrect.bottomRight())
        if not p1 or not p2:
            return [], ""
        
        fitz_rect = fitz.Rect(p1[0], p1[1], p2[0], p2[1])
        page = self.doc[self.current_page_idx]
        words = page.get_text("words")  # List of (x0, y0, x1, y1, text, block, line, word_no)

        selected_rects = []
        selected_text = []

        if self.display_label.is_double_click_drag:
            # Word-flow selection (logical reading order)
            start_idx = -1
            end_idx = -1
            for i, w in enumerate(words):
                w_rect = fitz.Rect(w[0], w[1], w[2], w[3])
                if w_rect.intersects(fitz_rect):
                    if start_idx == -1:
                        start_idx = i
                    end_idx = i
            
            if start_idx != -1:
                for i in range(start_idx, end_idx + 1):
                    w = words[i]
                    selected_rects.append(fitz.Rect(w[0], w[1], w[2], w[3]))
                    selected_text.append(w[4])
        else:
            # Box-selection (intersecting rectangles only)
            for w in words:
                w_rect = fitz.Rect(w[0], w[1], w[2], w[3])
                if w_rect.intersects(fitz_rect):
                    selected_rects.append(w_rect)
                    selected_text.append(w[4])
        
        return selected_rects, " ".join(selected_text)

    def preview_text_selection(self, qrect: QRect) -> None:
        """Updates live selection highlights without affecting clipboard."""
        if not self.doc:
            return
        rects, _ = self._get_selection_data(qrect)
        if rects:
            self.display_label.set_pdf_highlights(rects)

    def extract_text_from_rect(self, qrect: QRect) -> None:
        """Finalizes selection, copies text, and shows feedback."""
        if not self.doc:
            return
        rects, text = self._get_selection_data(qrect)
        if rects:
            QGuiApplication.clipboard().setText(text)
            self.display_label.set_pdf_highlights(rects)
            self.show_copy_feedback(qrect.center())
        else:
            self.display_label.clear_selection()

    def get_page_count(self) -> int:
        """Returns the total number of pages in the current document."""
        return len(self.doc) if self.doc else 0

    def get_page_size(self, index: int) -> QSize:
        """Returns the size of the specified page in points."""
        if self.doc and 0 <= index < len(self.doc):
            r = self.doc[index].rect
            return QSize(int(r.width), int(r.height))
        return QSize(0, 0)

    def get_manual_fit_factor(self) -> float:
        """Calculates the zoom factor required to fit the current page to the view."""
        if not self.doc:
            return 1.0
        page_rect = self.doc[self.current_page_idx].rect
        
        # Use viewport size but fallback to widget size if layout hasn't settled
        v_size = self.viewport().size()
        if v_size.width() < 100:
            v_size = self.size()
        
        if page_rect.width <= 0 or v_size.width() <= 0:
            return 1.0
            
        # Account for typical scrollbar width (approx 20px) to prevent toggle-flicker
        padding = self.FIT_FIXED_FRAME * 2 + 5
        avail_w = max(10, v_size.width() - padding)
        avail_h = max(10, v_size.height() - padding)
        
        factor = min(avail_w / page_rect.width, avail_h / page_rect.height)
        return factor * self.FIT_COMFORT_SCALE

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handles widget resize to re-trigger 'Fit' calculation if active."""
        super().resizeEvent(event)
        self.resized.emit()

    def _find_viewer_parent(self) -> Optional['PdfViewerWidget']:
        """Traverses parent chain to find the controlling viewer widget."""
        p = self.parent()
        while p:
            if isinstance(p, PdfViewerWidget):
                return p
            p = p.parent()
        return None

class DualPdfViewerWidget(QWidget):
    """
    Central controller for the dual PDF comparison view.
    Manages synchronization, match analysis, and layout.
    """
    close_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(0)
        
        self._sync_active = False 
        self._zoom_delta = 0.0

        # Persistent path memory
        self._orig_left_path: Optional[Path] = None
        self._orig_right_path: Optional[Path] = None
        self._diff_temp_path: Optional[Path] = None
        self._diff_worker = None

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        mid_color = self.palette().color(QPalette.ColorRole.Mid).name()
        self.splitter.setStyleSheet(f"QSplitter::handle {{ background: {mid_color}; width: 1px; }}")
        
        pipeline = getattr(parent, 'pipeline', None)
        self.left_viewer = PdfViewerWidget(pipeline=pipeline, controller=self, is_slave=False)
        self.right_viewer = PdfViewerWidget(pipeline=pipeline, controller=self, is_slave=True)
        
        from core.utils.hybrid_engine import HybridEngine
        self.engine = HybridEngine()

        self.splitter.addWidget(self.left_viewer)
        self.splitter.addWidget(self.right_viewer)
        self.layout_main.addWidget(self.splitter)

        # Add symmetry: "Close" button on right, invisible spacer on left
        self.btn_close = QPushButton(self.tr("Close"))
        self.btn_close.setFixedWidth(80)
        self.btn_close.setFixedHeight(30)
        self.btn_close.clicked.connect(self.close_requested.emit)
        self.right_viewer.toolbar.layout().addWidget(self.btn_close)
        
        # Symmetrical spacer for the left viewer
        self.left_spacer = QWidget()
        self.left_spacer.setFixedWidth(80)
        self.left_viewer.toolbar.layout().addWidget(self.left_spacer)

        self._init_floating_buttons()
        self._setup_sync_connections()
        self.btn_diff.toggled.connect(self._on_diff_toggled)
        self.splitter.handle(1).installEventFilter(self)
        QTimer.singleShot(200, self._reposition_link_button)

    def eventFilter(self, source: QObject, event: QEvent) -> bool:
        """Positions the floating link button when the splitter handle moves."""
        if source == self.splitter.handle(1) and event.type() == QEvent.Type.Move:
            self._reposition_link_button()
        return super().eventFilter(source, event)

    def _init_floating_buttons(self) -> None:
        """Initializes overlay control buttons."""
        highlight = self.palette().color(QPalette.ColorRole.Highlight).name()
        btn_bg = self.palette().color(QPalette.ColorRole.Button).name()
        
        self.btn_link = QPushButton("∞", self)
        self.btn_link.setCheckable(True)
        self.btn_link.setChecked(True)
        self.btn_link.setFixedSize(28, 28)
        self.btn_link.setStyleSheet(f"""
            QPushButton {{ background: {btn_bg}; border: 1px solid #adb5bd; border-radius: 14px; color: #6c757d; font-size: 18px; }}
            QPushButton:checked {{ background: {highlight}; color: white; border-color: {highlight}; }}
        """)
        
        self.btn_diff = QPushButton("Δ", self)
        self.btn_diff.setCheckable(True)
        self.btn_diff.setFixedSize(28, 28)
        self.btn_diff.setStyleSheet(f"""
            QPushButton {{ background: {btn_bg}; border: 1px solid #adb5bd; border-radius: 14px; color: #dc3545; font-size: 16px; font-weight: bold; }}
            QPushButton:checked {{ background: #dc3545; color: white; border-color: #a71d2a; }}
        """)

        for btn in [self.btn_link, self.btn_diff]:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(8)
            shadow.setOffset(0, 1)
            shadow.setColor(QColor(0, 0, 0, 80))
            btn.setGraphicsEffect(shadow)
        
        self.btn_link.toggled.connect(self._on_link_toggled)

    def _on_link_toggled(self, checked: bool) -> None:
        """Updates synchronization state between viewers."""
        self.left_viewer.set_sync_active(checked)
        self.right_viewer.set_sync_active(checked)
        if checked:
            self._sync_right_to_left()

    def stop(self) -> None:
        """Gracefully terminates background threads and clears references."""
        if self._diff_worker:
            worker = self._diff_worker
            print(f"[DualPdfViewer] Stopping background worker. Status: {worker.isRunning()}")
            if worker.isRunning():
                worker.cancel()
                print("[DualPdfViewer] Cancellation requested. Waiting for thread...")
                if not worker.wait(5000): # Wait up to 5 seconds
                    print("[DualPdfViewer] Worker stuck. Forcing termination!")
                    worker.terminate()
                    worker.wait()
                print("[DualPdfViewer] Background thread stopped.")
            self._diff_worker = None
            
        self.left_viewer.canvas.doc = None
        self.right_viewer.canvas.doc = None

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensures background threads are stopped before widget destruction."""
        self.stop()
        super().closeEvent(event)

    def _setup_sync_connections(self) -> None:
        """Wires up visual synchronization signals."""
        self.left_viewer.canvas.page_changed.connect(self._on_master_page_changed)
        self.right_viewer.canvas.page_changed.connect(self._on_slave_page_changed)
        self.left_viewer.canvas.zoom_changed.connect(self._on_master_zoom_changed)
        
        self.left_viewer.canvas.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll('v', v, True)
        )
        self.left_viewer.canvas.horizontalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll('h', v, True)
        )
        self.right_viewer.canvas.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll('v', v, False)
        )
        self.right_viewer.canvas.horizontalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll('h', v, False)
        )
        
        self.left_viewer.fit_toggled.connect(self._on_master_fit_toggled)
        self.right_viewer.fit_toggled.connect(self._on_slave_fit_toggled)

    def _activate_slave_zoom_receiver(self) -> None:
        """Enables feedback from slave zoom manually (avoiding circular loops)."""
        try:
            self.right_viewer.canvas.zoom_changed.disconnect(self._on_slave_zoom_changed)
        except (RuntimeError, TypeError):
            pass
        self.right_viewer.canvas.zoom_changed.connect(self._on_slave_zoom_changed)

    def _reposition_link_button(self) -> None:
        """Centers overlay buttons on the splitter handle."""
        handle = self.splitter.handle(1)
        if not handle:
            return
        pos = self.splitter.mapTo(self, handle.pos())
        center_x = pos.x() + (handle.width() // 2)
        self.btn_link.move(center_x - 14, (self.height() // 2) - 14)
        self.btn_diff.move(center_x - 14, 60)
        self.btn_link.raise_()
        self.btn_diff.raise_()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Triggers UI layout recalculations on widget resize."""
        super().resizeEvent(event)
        self._reposition_link_button()

    def _on_master_page_changed(self, page: int) -> None:
        """Syncs right viewer to left viewer's page."""
        if self.btn_link.isChecked() and not self._sync_active:
            self._sync_active = True
            try:
                self.right_viewer.canvas.jump_to_page(page, block_signals=True)
                self.right_viewer.update_ui_state(page)
                self._sync_right_to_left()
            finally:
                self._sync_active = False

    def _on_slave_page_changed(self, page: int) -> None:
        """Syncs left viewer to right viewer's page."""
        if self.btn_link.isChecked() and not self._sync_active:
            self._sync_active = True
            try:
                self.left_viewer.canvas.jump_to_page(page, block_signals=True)
                self.left_viewer.update_ui_state(page)
                self._sync_right_to_left()
            finally:
                self._sync_active = False

    def _on_master_zoom_changed(self, factor: float) -> None:
        """Recalculates slave zoom factor when master changes."""
        if self.btn_link.isChecked() and not self._sync_active:
            self._sync_right_to_left()

    def _on_slave_zoom_changed(self, factor: float) -> None:
        """Maintains relative zoom offset when slave viewer is zoomed directly."""
        if self._sync_active or not self.btn_link.isChecked():
            return
        m_canvas = self.left_viewer.canvas
        s_canvas = self.right_viewer.canvas
        p_m = m_canvas.get_page_size(m_canvas.current_page_idx)
        p_s = s_canvas.get_page_size(s_canvas.current_page_idx)
        
        if p_m.width() < 10 or p_s.width() < 10:
            return
            
        expected_zoom = m_canvas.zoom_factor * (p_m.width() / p_s.width())
        self._zoom_delta = factor - expected_zoom
        if abs(self._zoom_delta) < 0.005:
            self._zoom_delta = 0.0
        self.right_viewer.update_zoom_label(factor)

    def _sync_right_to_left(self) -> None:
        """Calculates and applies the correct zoom for the right viewer relative to master."""
        m, s = self.left_viewer, self.right_viewer
        
        # SYMMETRY: We use the master's available space as the reference
        if m.is_fit_mode:
            m_zoom = m.canvas.get_manual_fit_factor()
            # If we are linked, we ensure it also fits in the slave (just in case of tiny differences)
            s_zoom_fit = s.canvas.get_manual_fit_factor()
            m_zoom = min(m_zoom, s_zoom_fit)
            
            m.canvas.set_zoom(m_zoom, block_signals=True)
            m.update_zoom_label(m_zoom)
        else:
            m_zoom = m.canvas.zoom_factor
        
        p_m = m.canvas.get_page_size(m.canvas.current_page_idx)
        p_s = s.canvas.get_page_size(s.canvas.current_page_idx)
        
        if p_m.width() > 10 and p_s.width() > 10:
            ratio = p_m.width() / p_s.width()
            target_zoom = (m_zoom * ratio) + self._zoom_delta
        else:
            target_zoom = m_zoom
        
        # Apply to slave
        s.canvas.set_zoom(target_zoom, block_signals=True)
        s.is_fit_mode = m.is_fit_mode
        s.btn_fit.blockSignals(True)
        s.btn_fit.setChecked(m.is_fit_mode)
        s.btn_fit.blockSignals(False)
        s.update_zoom_label(target_zoom)

    def _sync_scroll(self, orient: str, value: int, m_is_src: bool) -> None:
        """Synchronizes scrollbar positions based on percentage."""
        if self._sync_active or not self.btn_link.isChecked():
            return
        self._sync_active = True
        try:
            src = self.left_viewer.canvas if m_is_src else self.right_viewer.canvas
            dst = self.right_viewer.canvas if m_is_src else self.left_viewer.canvas
            s_bar = src.verticalScrollBar() if orient == 'v' else src.horizontalScrollBar()
            d_bar = dst.verticalScrollBar() if orient == 'v' else dst.horizontalScrollBar()
            
            if s_bar.maximum() > 0:
                d_bar.setValue(int((s_bar.value() / s_bar.maximum()) * d_bar.maximum()))
        finally:
            self._sync_active = False

    def load_documents(self, left_path_raw: str, right_path_raw: str) -> None:
        """
        Loads the specified documents into both viewers.
        
        Args:
            left_path_raw: Absolute path to the master document.
            right_path_raw: Absolute path to the comparison document.
        """
        try:
            self.right_viewer.canvas.zoom_changed.disconnect(self._on_slave_zoom_changed)
        except (RuntimeError, TypeError):
            pass
            
        self._zoom_delta = 0.0 
        self._orig_left_path = Path(left_path_raw)
        self._orig_right_path = Path(right_path_raw)
        self._diff_temp_path = None

        self.left_viewer.load_document(str(self._orig_left_path))
        self.right_viewer.load_document(str(self._orig_right_path))
        
        # Debounced sync sequence to ensure layout has settled
        QTimer.singleShot(100, self._sync_right_to_left)
        QTimer.singleShot(400, self._sync_right_to_left)
        QTimer.singleShot(800, self._sync_right_to_left) 
        QTimer.singleShot(1200, self._start_background_diff)
        
        # Activate sync receiver after initial load
        QTimer.singleShot(500, lambda: (
            self._activate_slave_zoom_receiver(), 
            self._reposition_link_button()
        ))

    def _on_diff_toggled(self, checked: bool) -> None:
        """Swaps standard document with the processed diff document."""
        if checked:
            if self._diff_temp_path:
                self.right_viewer.load_document(str(self._diff_temp_path))
                QTimer.singleShot(200, self._sync_right_to_left)
        else:
            if self._orig_right_path:
                self.right_viewer.load_document(str(self._orig_right_path))
                QTimer.singleShot(200, self._sync_right_to_left)

    def _start_background_diff(self) -> None:
        """Initializes the background process for document comparison."""
        if self._diff_worker or not self._orig_left_path or not self._orig_right_path:
            return
        from gui.workers import MatchAnalysisWorker
        self._diff_worker = MatchAnalysisWorker(
            str(self._orig_left_path), 
            str(self._orig_right_path), 
            self.engine,
            parent=self
        )
        self._diff_worker.finished.connect(self._on_diff_ready)
        self._diff_worker.start()

    def _on_diff_ready(self, path: str) -> None:
        """Callback for diff worker completion."""
        self._diff_temp_path = Path(path)
        if self.btn_diff.isChecked():
            self.right_viewer.load_document(str(self._diff_temp_path))
            QTimer.singleShot(200, self._sync_right_to_left)

    def _on_master_fit_toggled(self, is_fit: bool) -> None:
        """Propagates Fit state from master to slave."""
        if self.btn_link.isChecked():
            self.right_viewer.set_fit_mode(is_fit, block_signals=True)
            self._sync_right_to_left()

    def _on_slave_fit_toggled(self, is_fit: bool) -> None:
        """Propagates Fit state from slave to master."""
        if self.btn_link.isChecked():
            self.left_viewer.set_fit_mode(is_fit, block_signals=True)
            self._sync_right_to_left()

class PdfViewerWidget(QWidget):
    """
    Standard PDF viewer component with a toolbar and interactive canvas.
    """
    fit_toggled = pyqtSignal(bool)
    document_changed = pyqtSignal()
    split_requested = pyqtSignal(str)
    stamp_requested = pyqtSignal(str)
    tags_update_requested = pyqtSignal(list)
    reprocess_requested = pyqtSignal(list)
    export_requested = pyqtSignal(list)
    delete_requested = pyqtSignal(str)

    def __init__(
        self, 
        pipeline: Optional[Any] = None, 
        controller: Optional['DualPdfViewerWidget'] = None, 
        is_slave: bool = False
    ) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.controller = controller 
        self.is_slave = is_slave
        self.is_fit_mode = True
        self.sync_active = True 
        self.current_uuid: Optional[str] = None
        self.current_pages_data: List[dict] = []
        self.temp_pdf_path: Optional[Path] = None
        
        # Toolbar Performance Policy (Flex-Approach)
        # Options: 'standard', 'comparison', 'audit'
        self.toolbar_policy = 'comparison' if controller else 'standard'
        
        self.canvas = PdfCanvas(self)
        self._init_ui()
        
        self.canvas.page_changed.connect(self.on_page_changed)
        self.canvas.zoom_changed.connect(self.update_zoom_label)
        self.canvas.resized.connect(self._on_viewport_resized)

    def _init_ui(self) -> None:
        """Constructs the viewer's layout and toolbar."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.toolbar = QFrame()
        self.toolbar.setFixedHeight(40)
        self.toolbar.setBackgroundRole(QPalette.ColorRole.Window)
        self.toolbar.setAutoFillBackground(True)
        
        t_layout = QHBoxLayout(self.toolbar)
        t_layout.setContentsMargins(5, 5, 5, 5)
        t_layout.setSpacing(4)
        
        bg = self.palette().color(QPalette.ColorRole.Window).name()
        base = self.palette().color(QPalette.ColorRole.Base).name()
        text = self.palette().color(QPalette.ColorRole.Text).name()
        highlight = self.palette().color(QPalette.ColorRole.Highlight).name()
        
        style = (
            f"QLineEdit {{ background: {base}; color: {text}; border: 1px solid #babdbf; "
            f"border-radius: 3px; padding: 2px 4px; }} "
            f"QLineEdit:focus {{ border: 1px solid {highlight}; }} "
            f"QLineEdit:read-only {{ background: {bg}; color: #6c757d; border: 1px solid #ced4da; }}"
        )
        
        btn_style = "font-weight: bold; font-size: 14px;"
        
        self.btn_prev = QPushButton("⟵")
        self.btn_prev.setFixedSize(30, 30)
        self.btn_prev.setStyleSheet(btn_style)
        self.btn_prev.clicked.connect(
            lambda: self.canvas.jump_to_page(self.canvas.current_page_idx - 1)
        )
        
        self.edit_page = QLineEdit()
        self.edit_page.setFixedSize(40, 30)
        self.edit_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_page.setValidator(QIntValidator(1, 9999))
        self.edit_page.setStyleSheet(style)
        self.edit_page.returnPressed.connect(self.on_page_edited)

        self.lbl_page_count = QLabel("/ 0")
        self.lbl_page_count.setStyleSheet(f"color: {text}; font-weight: 500; margin-right: 5px;")
        
        self.btn_next = QPushButton("⟶")
        self.btn_next.setFixedSize(30, 30)
        self.btn_next.setStyleSheet(btn_style)
        self.btn_next.clicked.connect(
            lambda: self.canvas.jump_to_page(self.canvas.current_page_idx + 1)
        )
        
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setFixedSize(30, 30)
        self.btn_zoom_out.setStyleSheet(btn_style)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        
        self.edit_zoom = QLineEdit("100%")
        self.edit_zoom.setFixedSize(65, 30)
        self.edit_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_zoom.setStyleSheet(style)
        self.edit_zoom.returnPressed.connect(self.on_zoom_edited)
        
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setFixedSize(30, 30)
        self.btn_zoom_in.setStyleSheet(btn_style)
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setCheckable(True)
        self.btn_fit.setChecked(True)
        self.btn_fit.setFixedSize(50, 30)
        self.btn_fit.setStyleSheet("font-weight: bold;")
        self.btn_fit.clicked.connect(self.toggle_fit)
        
        self.btn_rotate = QPushButton("↻")
        self.btn_rotate.setFixedSize(30, 30)
        self.btn_rotate.setStyleSheet(btn_style)
        self.btn_rotate.setVisible(False) 
        self.btn_rotate.clicked.connect(self.rotate_page)
        
        self.btn_del = QPushButton("✕")
        self.btn_del.setFixedSize(30, 30)
        self.btn_del.setStyleSheet("color: #da4453; font-weight: bold;")
        self.btn_del.setVisible(False) 
        self.btn_del.clicked.connect(self.delete_page)

        # Extension Buttons (Phase 2.0 / Plugins)
        self.btn_split = QPushButton("✂")
        self.btn_split.setFixedSize(30, 30)
        self.btn_split.setVisible(False)
        self.btn_split.setToolTip("Split Document")
        self.btn_split.clicked.connect(lambda: self.split_requested.emit(self.current_uuid))

        self.btn_save = QPushButton("💾")
        self.btn_save.setFixedSize(30, 30)
        self.btn_save.setVisible(False)
        self.btn_save.setToolTip("Save Changes")
        
        controls = [
            self.btn_prev, self.edit_page, self.lbl_page_count, self.btn_next, 
            self.btn_zoom_out, self.edit_zoom, self.btn_zoom_in, 
            self.btn_fit, self.btn_rotate, self.btn_del,
            self.btn_split, self.btn_save
        ]
        for ctrl in controls:
            # Symmetrical Layout Policy: Retain space when hidden
            if isinstance(ctrl, QPushButton):
                p = ctrl.sizePolicy()
                p.setRetainSizeWhenHidden(True)
                ctrl.setSizePolicy(p)
            t_layout.addWidget(ctrl)
            
        t_layout.addStretch()
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def _on_viewport_resized(self) -> None:
        """Callback for viewport resize to recalculate Fit factor."""
        if self.is_fit_mode:
            # Short delay to ensure local layout is stable
            QTimer.singleShot(0, self._apply_delayed_fit)

    def _apply_delayed_fit(self) -> None:
        """Perform delayed fit factor update."""
        if self.is_fit_mode:
            f = self.canvas.get_manual_fit_factor()
            # Link check: avoid redundant updates if slave is managed by master
            block = self.is_slave and self.sync_active
            self.canvas.set_zoom(f, block_signals=block)
            self.update_zoom_label(f)

    def set_sync_active(self, active: bool) -> None:
        """Updates synchronization state and UI responsiveness."""
        self.sync_active = active
        self.edit_zoom.setReadOnly(self.is_slave and self.sync_active)
        self.update_zoom_label(self.canvas.zoom_factor)

    def update_ui_state(self, page: int) -> None:
        """Updates the page number display and total count."""
        self.edit_page.blockSignals(True)
        self.edit_page.setText(str(page + 1))
        self.edit_page.blockSignals(False)
        
        total = self.canvas.get_page_count()
        self.lbl_page_count.setText(f"/ {total}")

    def on_page_changed(self, page: int) -> None:
        """Syncs UI state when page changes in canvas."""
        self.update_ui_state(page)

    def on_page_edited(self) -> None:
        """Handles manual page entry."""
        try:
            target = int(self.edit_page.text()) - 1
            self.canvas.jump_to_page(target)
        except (ValueError, TypeError):
            self.update_ui_state(self.canvas.current_page_idx)

    def on_document_status_ready(self) -> None:
        """Initializes UI once document is loaded."""
        self.update_ui_state(self.canvas.current_page_idx)
        if self.is_fit_mode:
            self.set_fit_mode(True)

    def load_document(
        self, 
        path_or_uuid: Union[str, Path], 
        uuid: Optional[str] = None, 
        initial_page: int = 1, 
        jump_to_index: int = -1
    ) -> None:
        """
        Loads a document by path or UUID.
        
        Args:
            path_or_uuid: File path or unique identifier.
            uuid: Optional explicit UUID.
            initial_page: 1-indexed start page.
            jump_to_index: 0-indexed jump target.
        """
        target_uuid = uuid if uuid else (
            str(path_or_uuid) if not Path(str(path_or_uuid)).exists() else None
        )
        path = Path(str(path_or_uuid))
        
        if not path.exists() and self.pipeline and target_uuid:
            doc_obj = self.pipeline.get_document(target_uuid)
            if doc_obj:
                self.current_uuid = target_uuid
                self.current_pages_data = []
                
                # Flatten the source mapping into a sequential page list
                for ref in doc_obj.source_mapping:
                    phys_file = self.pipeline.physical_repo.get_by_uuid(ref.file_uuid)
                    if phys_file:
                        for p_idx in ref.pages:
                            self.current_pages_data.append({
                                "file_path": phys_file.file_path,
                                "page_index": p_idx - 1,  # DB uses 1-based, Fitz uses 0-based
                                "rotation": ref.rotation or 0
                            })
                
                self._refresh_preview()
                return
                
        if path.exists():
            self.current_pages_data = [] # Clear virtual data if loading direct path
            self.canvas.set_document(fitz.open(str(path)))
            self._update_toolbar_policy()
            self.on_document_status_ready()
            
        idx = jump_to_index if jump_to_index >= 0 else (initial_page - 1 if initial_page > 1 else -1)
        if idx >= 0:
            QTimer.singleShot(250, lambda: self.canvas.jump_to_page(idx))

    def _refresh_preview(self) -> None:
        """Reconstructs the multi-page preview from source fragments."""
        if not self.current_pages_data:
            return
            
        out_doc = fitz.open()
        for item in self.current_pages_data:
            src = fitz.open(item['file_path'])
            if item['page_index'] == -1:
                out_doc.insert_pdf(src)
            else:
                out_doc.insert_pdf(
                    src, 
                    from_page=item['page_index'], 
                    to_page=item['page_index']
                )
            if item['rotation'] != 0:
                out_doc[-1].set_rotation(item['rotation'])
            src.close()
            
        fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix="kview_")
        os.close(fd)
        self.temp_pdf_path = Path(temp_path)
        out_doc.save(str(self.temp_pdf_path))
        out_doc.close()
        
        self.canvas.set_document(fitz.open(str(self.temp_pdf_path)))
        self._update_toolbar_policy()
        self.on_document_status_ready()

    def _update_toolbar_policy(self) -> None:
        """
        Applies UI logic for action buttons based on the set policy.
        
        Policies:
        - 'standard': Full control (List View).
        - 'comparison': Read-only (Side-by-side / Hybrid).
        - 'audit': Rotation only on master (Verification view).
        """
        policy = self.toolbar_policy
        
        # 1. Base Visibility/Activity
        if policy == 'comparison':
            # Side-by-Side (Classic Hybrid/Diff): No structural changes allowed
            self._set_button_visible(self.btn_rotate, False)
            self._set_button_visible(self.btn_del, False)
            self._set_button_visible(self.btn_split, False)
            self._set_button_visible(self.btn_save, False)
            return

        if policy == 'audit':
            # Master can rotate, Slave is locked
            can_rotate = not self.is_slave
            self._set_button_visible(self.btn_rotate, can_rotate)
            self._set_button_visible(self.btn_del, False)
            # Split/Save handled by window usually, but we ensure policy
            self._set_button_visible(self.btn_split, False)
            self._set_button_visible(self.btn_save, False)
            return

        # 'standard' (Standard List View) Context:
        self._set_button_visible(self.btn_rotate, True)
        self.btn_rotate.setEnabled(True)
        
        is_immutable = False
        if self.current_uuid and self.pipeline:
            doc_obj = self.pipeline.get_document(self.current_uuid)
            if doc_obj:
                is_immutable = doc_obj.is_immutable
        
        # UI Policy for Delete:
        self._set_button_visible(self.btn_del, True) 
        
        can_delete = not is_immutable
        if self.current_pages_data:
            can_delete = can_delete and len(self.current_pages_data) > 1
        else:
            can_delete = False 
            
        self.btn_del.setEnabled(can_delete)
        self._set_button_visible(self.btn_split, True)

    def _set_button_visible(self, btn: QPushButton, visible: bool) -> None:
        """Helper to set visibility while ensuring symmetry via size retention."""
        btn.setVisible(visible)
        btn.setEnabled(visible)

    def set_toolbar_policy(self, policy: str) -> None:
        """Updates the viewer policy and refreshes the UI."""
        self.toolbar_policy = policy
        self._update_toolbar_policy()

    def rotate_page(self) -> None:
        """Rotates current page by 90 degrees clockwise."""
        if self.current_pages_data:
            idx = self.canvas.current_page_idx
            if idx < len(self.current_pages_data):
                self.current_pages_data[idx]['rotation'] = (
                    self.current_pages_data[idx]['rotation'] + 90
                ) % 360
                self._refresh_preview()
        else:
            # Direct file rotation (visual only in this session)
            self.canvas.set_rotation((self.canvas.rotation + 90) % 360)

    def delete_page(self) -> None:
        """Removes the current page from the document list."""
        if self.current_pages_data and len(self.current_pages_data) > 1:
            idx = self.canvas.current_page_idx
            self.current_pages_data.pop(idx)
            self._refresh_preview()

    def toggle_fit(self) -> None:
        """Toggles 'Fit to View' mode."""
        self.set_fit_mode(self.btn_fit.isChecked())

    def set_fit_mode(self, is_fit: bool, block_signals: bool = False) -> None:
        """
        Enables or disables Fit mode.
        
        Args:
            is_fit: Target fit state.
            block_signals: If True, fit_toggled signal is not emitted.
        """
        if is_fit:
            self.canvas.set_zoom(self.canvas.get_manual_fit_factor(), block_signals=block_signals)
        self.is_fit_mode = is_fit
        self.btn_fit.blockSignals(True)
        self.btn_fit.setChecked(is_fit)
        self.btn_fit.blockSignals(False)
            
        if not block_signals: 
            self.fit_toggled.emit(is_fit)
            self.update_zoom_label(self.canvas.zoom_factor)

    def on_zoom_edited(self) -> None:
        """Handles manual zoom entry."""
        if self.edit_zoom.isReadOnly():
            return
        try:
            val = float(self.edit_zoom.text().replace("%", "").strip()) / 100.0
            if 0.1 <= val <= 10.0:
                if self.is_fit_mode:
                    self.set_fit_mode(False)
                self.canvas.set_zoom(val)
        except (ValueError, TypeError):
            self.update_zoom_label(self.canvas.zoom_factor)

    def zoom_in(self) -> None:
        """Increments zoom level."""
        if self.is_fit_mode:
            self.set_fit_mode(False)
        step = 0.01 if (self.is_slave and self.sync_active) else 0.1
        self.canvas.set_zoom(self.canvas.zoom_factor + step)

    def zoom_out(self) -> None:
        """Decrements zoom level."""
        if self.is_fit_mode:
            self.set_fit_mode(False)
        step = 0.01 if (self.is_slave and self.sync_active) else 0.1
        self.canvas.set_zoom(max(0.1, self.canvas.zoom_factor - step))

    def clear(self) -> None:
        """Closes the current document and clears the display."""
        self.current_uuid = None
        self.canvas.set_document(None)
        self.update_ui_state(0)
        self.edit_zoom.setText("100%")
        self.btn_fit.setChecked(True)
        self.btn_rotate.setVisible(False)
        self.btn_del.setVisible(False)

    def set_highlight_text(self, text: str) -> None:
        """Triggers text search and highlighting on the current page."""
        # TODO: Implement text search highlighting in PdfCanvas
        pass

    def update_zoom_label(self, factor: float) -> None:
        """Updates the zoom percentage label."""
        if self.is_slave and self.sync_active and self.controller:
            delta = self.controller._zoom_delta
            text = f"Δ {delta:+.0%}" if abs(delta) >= 0.005 else "Δ 0%"
            self.edit_zoom.setText(text)
            self.edit_zoom.setReadOnly(True)
        else:
            self.edit_zoom.setText(f"{factor:.0%}")
            self.edit_zoom.setReadOnly(False)
