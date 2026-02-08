from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QMessageBox, QLineEdit, QSplitter, QGraphicsDropShadowEffect, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize, QRect, QPoint, QEvent
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QGuiApplication, QIntValidator, QPalette, QWheelEvent
import fitz
import os
import tempfile
import sys

from core.models.virtual import SourceReference

class PdfDisplayLabel(QLabel):
    """
    Spezialisierte Anzeige-Komponente für das PDF-Bild.
    Zeichnet die exakten Wort-Highlights der Selektion.
    """
    text_selected = pyqtSignal(QRect)
    word_double_clicked = pyqtSignal(QPoint)
    clicked_empty = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.highlight_rects = [] # Liste von QRects für die Wort-Hinterlegung
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def set_highlights(self, rects):
        """Setzt die Liste der einzufärbenden Wort-Rechtecke."""
        self.highlight_rects = rects
        self.update()

    def clear_selection(self):
        """Löscht alle visuellen Markierungen."""
        self.highlight_rects = []
        self.selection_start = None
        self.selection_end = None
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selection_start = event.pos()
            self.selection_end = event.pos()
            self.is_selecting = True
            # Bei Klick erst mal alles visuell zurücksetzen
            self.clear_selection()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.selection_end = event.pos()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_selecting:
            self.is_selecting = False
            # Guard: Sicherstellen, dass Start und Ende nicht None sind
            if self.selection_start is not None and self.selection_end is not None:
                rect = QRect(self.selection_start, self.selection_end).normalized()
                
                # Wenn der Rahmen signifikant groß ist -> Selektion auslösen
                if rect.width() > 5 and rect.height() > 5:
                    self.text_selected.emit(rect)
                else:
                    # Nur ein Klick -> Deselektion
                    self.clicked_empty.emit()
            
            self.selection_start = None
            self.selection_end = None
            self.update()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.word_double_clicked.emit(event.pos())
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        
        # 1. Zeichne die exakten Wort-Highlights (hinterlegter Text)
        if self.highlight_rects:
            # Etwas transparenter für die Wort-Hinterlegung
            brush_color = QColor(highlight_color.red(), highlight_color.green(), highlight_color.blue(), 80)
            painter.setBrush(brush_color)
            painter.setPen(Qt.PenStyle.NoPen)
            for r in self.highlight_rects:
                painter.drawRect(r)
                
        # 2. Zeichne den aktiven Auswahlrahmen während des Ziehens
        if self.is_selecting and self.selection_start is not None and self.selection_end is not None:
            painter.setPen(QColor(highlight_color.red(), highlight_color.green(), highlight_color.blue(), 200))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRect(self.selection_start, self.selection_end).normalized())

class PdfCanvas(QScrollArea):
    """
    Haupt-Leinwand für das PDF. Verwaltet Rendering und die intelligente Textextraktion.
    """
    page_changed = pyqtSignal(int)
    zoom_changed = pyqtSignal(float)

    FIT_FIXED_FRAME = 15.0    
    FIT_COMFORT_SCALE = 1.0
    SUPERSAMPLING = 3.0 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.setBackgroundRole(QPalette.ColorRole.Mid)
        self.viewport().setBackgroundRole(QPalette.ColorRole.Mid)
        self.setFrameShape(QFrame.Shape.NoFrame)
        
        self.display_label = PdfDisplayLabel()
        self.display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display_label.setBackgroundRole(QPalette.ColorRole.Mid)
        self.display_label.setAutoFillBackground(True)
        
        # Signale verbinden
        self.display_label.text_selected.connect(self.extract_text_from_rect)
        self.display_label.word_double_clicked.connect(self.extract_word_at_pos)
        self.display_label.clicked_empty.connect(self.display_label.clear_selection)
        
        self.setWidget(self.display_label)
        
        # Kopier-Hinweis
        self.copy_hint = QLabel("Kopiert!", self)
        self.copy_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.copy_hint.setFixedSize(80, 30)
        self.copy_hint.hide()
        tip_bg = self.palette().color(QPalette.ColorRole.ToolTipBase).name()
        tip_text = self.palette().color(QPalette.ColorRole.ToolTipText).name()
        self.copy_hint.setStyleSheet(f"background: {tip_bg}; color: {tip_text}; border: 1px solid #adb5bd; border-radius: 5px; font-weight: bold;")
        
        self.doc = None
        self.current_page_idx = 0
        self.zoom_factor = 1.0

    def show_copy_feedback(self, widget_pos):
        canvas_pos = self.mapFromGlobal(self.display_label.mapToGlobal(widget_pos))
        self.copy_hint.move(canvas_pos.x() - 40, canvas_pos.y() - 40)
        self.copy_hint.show()
        self.copy_hint.raise_()
        QTimer.singleShot(1000, self.copy_hint.hide)

    def set_document(self, fitz_doc):
        self.doc = fitz_doc
        self.current_page_idx = 0
        print(f"[DEBUG_CANVAS] Dokument geladen: {len(fitz_doc)} Seiten.", flush=True)
        self.render_current_page()

    def jump_to_page(self, index, block_signals=False):
        if self.doc and 0 <= index < len(self.doc):
            self.current_page_idx = index
            self.display_label.clear_selection()
            if not block_signals:
                self.page_changed.emit(index)
            self.render_current_page()

    def set_zoom(self, factor, block_signals=False):
        factor = max(0.1, min(10.0, factor))
        if abs(factor - self.zoom_factor) > 0.0001:
            self.zoom_factor = factor
            if not block_signals:
                self.zoom_changed.emit(factor)
            self.render_current_page()

    def render_current_page(self):
        if not self.doc:
            self.display_label.clear()
            return
        self.display_label.setUpdatesEnabled(False)
        try:
            page = self.doc[self.current_page_idx]
            dpr = self.devicePixelRatioF()
            mat = fitz.Matrix(self.zoom_factor * dpr * self.SUPERSAMPLING, self.zoom_factor * dpr * self.SUPERSAMPLING)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            qimg.setDevicePixelRatio(dpr * self.SUPERSAMPLING)
            self.display_label.setPixmap(QPixmap.fromImage(qimg))
        finally:
            self.display_label.setUpdatesEnabled(True)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            self.set_zoom(self.zoom_factor * (1.1 if delta > 0 else 0.9))
            event.accept()
        else:
            super().wheelEvent(event)

    def _get_pdf_coords(self, pos: QPoint):
        if not self.doc: return None
        pixmap = self.display_label.pixmap()
        if not pixmap: return None
        dpr_total = pixmap.devicePixelRatio()
        offset_x = (self.display_label.width() - (pixmap.width() / dpr_total)) / 2
        offset_y = (self.display_label.height() - (pixmap.height() / dpr_total)) / 2
        return (pos.x() - offset_x) / self.zoom_factor, (pos.y() - offset_y) / self.zoom_factor

    def _get_widget_coords(self, pdf_x, pdf_y):
        """Rechnet PDF-Punkte zurück in Widget-Pixel (für Highlighting)."""
        pixmap = self.display_label.pixmap()
        if not pixmap: return QPoint(0, 0)
        dpr_total = pixmap.devicePixelRatio()
        offset_x = (self.display_label.width() - (pixmap.width() / dpr_total)) / 2
        offset_y = (self.display_label.height() - (pixmap.height() / dpr_total)) / 2
        return QPoint(int(pdf_x * self.zoom_factor + offset_x), int(pdf_y * self.zoom_factor + offset_y))

    def extract_word_at_pos(self, pos):
        if not self.doc: return
        coords = self._get_pdf_coords(pos)
        if not coords: return
        page = self.doc[self.current_page_idx]
        for w in page.get_text("words"):
            if w[0] <= coords[0] <= w[2] and w[1] <= coords[1] <= w[3]:
                QGuiApplication.clipboard().setText(w[4])
                # Visuelles Highlight für das Wort setzen
                p_tl = self._get_widget_coords(w[0], w[1])
                p_br = self._get_widget_coords(w[2], w[3])
                self.display_label.set_highlights([QRect(p_tl, p_br)])
                self.show_copy_feedback(pos)
                return

    def extract_text_from_rect(self, qrect):
        """Findet alle Wörter im Bereich und markiert sie einzeln."""
        if not self.doc: return
        p1 = self._get_pdf_coords(qrect.topLeft())
        p2 = self._get_pdf_coords(qrect.bottomRight())
        if not p1 or not p2: return
        
        fitz_rect = fitz.Rect(p1[0], p1[1], p2[0], p2[1])
        page = self.doc[self.current_page_idx]
        
        # Alle Wörter finden, die im Selektions-Rechteck liegen
        words_in_rect = []
        full_text = []
        for w in page.get_text("words"):
            # Prüfen ob Wort-Zentrum oder Box das Rechteck schneidet
            w_rect = fitz.Rect(w[0], w[1], w[2], w[3])
            if w_rect.intersects(fitz_rect):
                # Umrechnung zurück in Widget-Pixel für die Anzeige
                tl = self._get_widget_coords(w[0], w[1])
                br = self._get_widget_coords(w[2], w[3])
                words_in_rect.append(QRect(tl, br))
                full_text.append(w[4])
        
        if words_in_rect:
            QGuiApplication.clipboard().setText(" ".join(full_text))
            self.display_label.set_highlights(words_in_rect)
            self.show_copy_feedback(qrect.center())
            print(f"[DEBUG_SELECTION] {len(words_in_rect)} Wörter markiert.", flush=True)

    def get_page_count(self): return len(self.doc) if self.doc else 0

    def get_page_size(self, index):
        if self.doc and 0 <= index < len(self.doc):
            r = self.doc[index].rect
            return QSize(int(r.width), int(r.height))
        return QSize(0, 0)

    def get_manual_fit_factor(self) -> float:
        if not self.doc: return 1.0
        page_rect = self.doc[self.current_page_idx].rect
        view_size = self.viewport().size()
        if page_rect.width <= 0 or view_size.width() <= 0: return 1.0
        avail_w = max(10, view_size.width() - (self.FIT_FIXED_FRAME * 2))
        avail_h = max(10, view_size.height() - (self.FIT_FIXED_FRAME * 2))
        return min(avail_w / page_rect.width, avail_h / page_rect.height) * self.FIT_COMFORT_SCALE

    def resizeEvent(self, event):
        super().resizeEvent(event)
        viewer = self._find_viewer_parent()
        if viewer and viewer.is_fit_mode: QTimer.singleShot(50, viewer._on_viewport_resized)

    def _find_viewer_parent(self):
        p = self.parent()
        while p:
            if isinstance(p, PdfViewerWidget): return p
            p = p.parent()
        return None

class DualPdfViewerWidget(QWidget):
    """
    Zentraler Controller für die Vergleichsansicht.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        self._sync_active = False 
        self._zoom_delta = 0.0

        # Memory for Match Analysis
        self._orig_left_path = None
        self._orig_right_path = None
        self._diff_temp_path = None
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
        self.layout.addWidget(self.splitter)

        self._init_floating_buttons()
        self._setup_sync_connections()
        self.btn_diff.toggled.connect(self._on_diff_toggled)
        self.splitter.handle(1).installEventFilter(self)
        QTimer.singleShot(200, self._reposition_link_button)

    def eventFilter(self, source, event):
        if source == self.splitter.handle(1) and event.type() == QEvent.Type.Move:
            self._reposition_link_button()
        return super().eventFilter(source, event)

    def _init_floating_buttons(self):
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
            shadow.setColor(QColor(0,0,0,80))
            btn.setGraphicsEffect(shadow)
        self.btn_link.toggled.connect(self._on_link_toggled)

    def _on_link_toggled(self, checked):
        self.left_viewer.set_sync_active(checked)
        self.right_viewer.set_sync_active(checked)
        if checked: self._sync_right_to_left()

    def _setup_sync_connections(self):
        self.left_viewer.canvas.page_changed.connect(self._on_master_page_changed)
        self.right_viewer.canvas.page_changed.connect(self._on_slave_page_changed)
        self.left_viewer.canvas.zoom_changed.connect(self._on_master_zoom_changed)
        self.left_viewer.canvas.verticalScrollBar().valueChanged.connect(lambda v: self._sync_scroll('v', v, True))
        self.left_viewer.canvas.horizontalScrollBar().valueChanged.connect(lambda v: self._sync_scroll('h', v, True))
        self.right_viewer.canvas.verticalScrollBar().valueChanged.connect(lambda v: self._sync_scroll('v', v, False))
        self.right_viewer.canvas.horizontalScrollBar().valueChanged.connect(lambda v: self._sync_scroll('h', v, False))
        self.left_viewer.fit_toggled.connect(self._on_master_fit_toggled)
        self.right_viewer.fit_toggled.connect(self._on_slave_fit_toggled)

    def _activate_slave_zoom_receiver(self):
        try: self.right_viewer.canvas.zoom_changed.disconnect(self._on_slave_zoom_changed)
        except: pass
        self.right_viewer.canvas.zoom_changed.connect(self._on_slave_zoom_changed)

    def _reposition_link_button(self):
        handle = self.splitter.handle(1)
        if not handle: return
        pos = self.splitter.mapTo(self, handle.pos())
        center_x = pos.x() + (handle.width() // 2)
        self.btn_link.move(center_x - 14, (self.height() // 2) - 14)
        self.btn_diff.move(center_x - 14, 60)
        self.btn_link.raise_()
        self.btn_diff.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_link_button()

    def _on_master_page_changed(self, page):
        if self.btn_link.isChecked() and not self._sync_active:
            self._sync_active = True
            try:
                self.right_viewer.canvas.jump_to_page(page, block_signals=True)
                self.right_viewer.update_ui_state(page)
                self._sync_right_to_left()
            finally: self._sync_active = False

    def _on_slave_page_changed(self, page):
        if self.btn_link.isChecked() and not self._sync_active:
            self._sync_active = True
            try:
                self.left_viewer.canvas.jump_to_page(page, block_signals=True)
                self.left_viewer.update_ui_state(page)
                self._sync_right_to_left()
            finally: self._sync_active = False

    def _on_master_zoom_changed(self, factor):
        if self.btn_link.isChecked() and not self._sync_active: self._sync_right_to_left()

    def _on_slave_zoom_changed(self, factor):
        if self._sync_active or not self.btn_link.isChecked(): return
        m_zoom = self.left_viewer.canvas.zoom_factor
        p_m = self.left_viewer.canvas.get_page_size(self.left_viewer.canvas.current_page_idx)
        p_s = self.right_viewer.canvas.get_page_size(self.right_viewer.canvas.current_page_idx)
        if p_m.width() < 10 or p_s.width() < 10: return
        self._zoom_delta = factor - (m_zoom * (p_m.width() / p_s.width()))
        if abs(self._zoom_delta) < 0.005: self._zoom_delta = 0.0
        self.right_viewer.update_zoom_label(factor)

    def _sync_right_to_left(self):
        m, s = self.left_viewer, self.right_viewer
        m_zoom = m.canvas.get_manual_fit_factor() if m.is_fit_mode else m.canvas.zoom_factor
        if m.is_fit_mode: m.canvas.set_zoom(m_zoom, block_signals=True)
        p_m = m.canvas.get_page_size(m.canvas.current_page_idx)
        p_s = s.canvas.get_page_size(s.canvas.current_page_idx)
        ratio = p_m.width() / p_s.width() if p_m.width() > 10 and p_s.width() > 10 else 1.0
        target_zoom = (m_zoom * ratio) + self._zoom_delta
        s.canvas.set_zoom(target_zoom, block_signals=True)
        s.btn_fit.blockSignals(True)
        s.btn_fit.setChecked(m.is_fit_mode)
        s.btn_fit.blockSignals(False)
        s.is_fit_mode = m.is_fit_mode
        s.update_zoom_label(target_zoom)

    def _sync_scroll(self, orient, value, m_is_src):
        if self._sync_active or not self.btn_link.isChecked(): return
        self._sync_active = True
        try:
            src = self.left_viewer.canvas if m_is_src else self.right_viewer.canvas
            dst = self.right_viewer.canvas if m_is_src else self.left_viewer.canvas
            s_bar = src.verticalScrollBar() if orient == 'v' else src.horizontalScrollBar()
            d_bar = dst.verticalScrollBar() if orient == 'v' else dst.horizontalScrollBar()
            if s_bar.maximum() > 0: d_bar.setValue(int((s_bar.value() / s_bar.maximum()) * d_bar.maximum()))
        finally: self._sync_active = False

    def load_documents(self, left_path, right_path):
        try: self.right_viewer.canvas.zoom_changed.disconnect(self._on_slave_zoom_changed)
        except: pass
        self._zoom_delta = 0.0 
        
        self._orig_left_path = left_path
        self._orig_right_path = right_path
        self._diff_temp_path = None # Reset diff on new load

        self.left_viewer.load_document(left_path)
        self.right_viewer.load_document(right_path)
        
        # Start background preparation of the Diff-PDF
        QTimer.singleShot(1000, self._start_background_diff)
        QTimer.singleShot(800, lambda: (self._sync_right_to_left(), self._activate_slave_zoom_receiver(), self._reposition_link_button()))

    def _on_diff_toggled(self, checked):
        if checked:
            if self._diff_temp_path:
                self.right_viewer.load_document(self._diff_temp_path)
                QTimer.singleShot(200, self._sync_right_to_left)
            else:
                # If not ready, we could show a message or just wait for worker
                pass
        else:
            if self._orig_right_path:
                self.right_viewer.load_document(self._orig_right_path)
                QTimer.singleShot(200, self._sync_right_to_left)

    def _start_background_diff(self):
        if self._diff_worker or not self._orig_left_path or not self._orig_right_path: return
        from gui.workers import MatchAnalysisWorker
        self._diff_worker = MatchAnalysisWorker(self._orig_left_path, self._orig_right_path, self.engine)
        self._diff_worker.finished.connect(self._on_diff_ready)
        self._diff_worker.start()

    def _on_diff_ready(self, path):
        self._diff_temp_path = path
        self._diff_worker = None # Worker is done
        if self.btn_diff.isChecked():
            self.right_viewer.load_document(path)
            QTimer.singleShot(200, self._sync_right_to_left)

    def _on_master_fit_toggled(self, is_fit):
        if self.btn_link.isChecked(): self.right_viewer.set_fit_mode(is_fit, block_signals=True), self._sync_right_to_left()

    def _on_slave_fit_toggled(self, is_fit):
        if self.btn_link.isChecked(): self.left_viewer.set_fit_mode(is_fit, block_signals=True), self._sync_right_to_left()

class PdfViewerWidget(QWidget):
    """
    Standard Viewer mit Toolbar und Bearbeitungstools.
    """
    fit_toggled = pyqtSignal(bool)
    document_changed = pyqtSignal()
    split_requested = pyqtSignal(str)
    stamp_requested = pyqtSignal(str)
    tags_update_requested = pyqtSignal(list)
    reprocess_requested = pyqtSignal(list)
    export_requested = pyqtSignal(list)
    delete_requested = pyqtSignal(str)

    def __init__(self, pipeline=None, controller=None, is_slave=False):
        super().__init__()
        self.pipeline = pipeline
        self.controller = controller 
        self.is_slave = is_slave
        self.is_fit_mode = True
        self.sync_active = True 
        self.current_uuid = None
        self.current_pages_data = []
        self.temp_pdf_path = None
        self.canvas = PdfCanvas(self)
        self._init_ui()
        self.canvas.page_changed.connect(self.on_page_changed)
        self.canvas.zoom_changed.connect(self.update_zoom_label)

    def _init_ui(self):
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
        style = f"QLineEdit {{ background: {base}; color: {text}; border: 1px solid #babdbf; border-radius: 3px; padding: 2px 4px; }} QLineEdit:focus {{ border: 1px solid {highlight}; }} QLineEdit:read-only {{ background: {bg}; color: #6c757d; border: 1px solid #ced4da; }}"
        self.btn_prev = QPushButton("⟵")
        self.btn_prev.setFixedSize(30, 30)
        self.btn_prev.clicked.connect(lambda: self.canvas.jump_to_page(self.canvas.current_page_idx - 1))
        self.edit_page = QLineEdit()
        self.edit_page.setFixedSize(45, 30)
        self.edit_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_page.setValidator(QIntValidator(1, 9999))
        self.edit_page.setStyleSheet(style)
        self.edit_page.returnPressed.connect(self.on_page_edited)
        self.btn_next = QPushButton("⟶")
        self.btn_next.setFixedSize(30, 30)
        self.btn_next.clicked.connect(lambda: self.canvas.jump_to_page(self.canvas.current_page_idx + 1))
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setFixedSize(30, 30)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        self.edit_zoom = QLineEdit("100%")
        self.edit_zoom.setFixedSize(65, 30)
        self.edit_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_zoom.setStyleSheet(style)
        self.edit_zoom.returnPressed.connect(self.on_zoom_edited)
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setFixedSize(30, 30)
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setCheckable(True)
        self.btn_fit.setChecked(True)
        self.btn_fit.setFixedSize(50, 30)
        self.btn_fit.clicked.connect(self.toggle_fit)
        self.btn_rotate = QPushButton("↻")
        self.btn_rotate.setFixedSize(30, 30)
        self.btn_rotate.clicked.connect(self.rotate_page)
        self.btn_del = QPushButton("✕")
        self.btn_del.setFixedSize(30, 30)
        self.btn_del.setStyleSheet("color: #da4453; font-weight: bold;")
        self.btn_del.clicked.connect(self.delete_page)
        for w in [self.btn_prev, self.edit_page, self.btn_next, self.btn_zoom_out, self.edit_zoom, self.btn_zoom_in, self.btn_fit, self.btn_rotate, self.btn_del]:
            t_layout.addWidget(w)
        t_layout.addStretch()
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def _on_viewport_resized(self):
        if self.is_fit_mode:
            f = self.canvas.get_manual_fit_factor()
            self.canvas.set_zoom(f, block_signals=True)
            self.update_zoom_label(f)

    def set_sync_active(self, active):
        self.sync_active = active
        self.edit_zoom.setReadOnly(self.is_slave and self.sync_active)
        self.update_zoom_label(self.canvas.zoom_factor)

    def update_ui_state(self, page):
        self.edit_page.blockSignals(True)
        self.edit_page.setText(str(page + 1))
        self.edit_page.blockSignals(False)

    def on_page_changed(self, page): self.update_ui_state(page)

    def on_page_edited(self):
        try: self.canvas.jump_to_page(int(self.edit_page.text()) - 1)
        except: self.update_ui_state(self.canvas.current_page_idx)

    def on_document_status_ready(self):
        self.update_ui_state(self.canvas.current_page_idx)
        if self.is_fit_mode: self.set_fit_mode(True)

    def load_document(self, path_or_uuid, uuid=None, initial_page=1, jump_to_index=-1):
        target_uuid = uuid if uuid else (path_or_uuid if not os.path.exists(str(path_or_uuid)) else None)
        path = str(path_or_uuid)
        if not os.path.exists(path) and self.pipeline and target_uuid:
            doc_obj = self.pipeline.get_document(target_uuid)
            if doc_obj:
                self.current_uuid = target_uuid
                self.current_pages_data = [{"file_path": p.source_path, "page_index": p.source_page_index, "rotation": p.rotation or 0} for p in doc_obj.pages]
                self._refresh_preview()
                return
        if os.path.exists(path):
            self.canvas.set_document(fitz.open(path))
            self.on_document_status_ready()
        idx = jump_to_index if jump_to_index >= 0 else (initial_page - 1 if initial_page > 1 else -1)
        if idx >= 0: QTimer.singleShot(250, lambda: self.canvas.jump_to_page(idx))

    def _refresh_preview(self):
        if not self.current_pages_data: return
        out_doc = fitz.open()
        for item in self.current_pages_data:
            src = fitz.open(item['file_path'])
            if item['page_index'] == -1: out_doc.insert_pdf(src)
            else: out_doc.insert_pdf(src, from_page=item['page_index'], to_page=item['page_index'])
            if item['rotation'] != 0: out_doc[-1].set_rotation(item['rotation'])
            src.close()
        fd, self.temp_pdf_path = tempfile.mkstemp(suffix=".pdf", prefix="kview_")
        os.close(fd)
        out_doc.save(self.temp_pdf_path)
        out_doc.close()
        self.canvas.set_document(fitz.open(self.temp_pdf_path))
        self.on_document_status_ready()

    def rotate_page(self):
        if self.current_pages_data:
            idx = self.canvas.current_page_idx
            self.current_pages_data[idx]['rotation'] = (self.current_pages_data[idx]['rotation'] + 90) % 360
            self._refresh_preview()

    def delete_page(self):
        if self.current_pages_data and len(self.current_pages_data) > 1:
            idx = self.canvas.current_page_idx
            self.current_pages_data.pop(idx)
            self._refresh_preview()

    def toggle_fit(self): self.set_fit_mode(self.btn_fit.isChecked())

    def set_fit_mode(self, is_fit, block_signals=False):
        if is_fit: self.canvas.set_zoom(self.canvas.get_manual_fit_factor(), block_signals=block_signals)
        self.is_fit_mode = is_fit
        self.btn_fit.blockSignals(True)
        self.btn_fit.setChecked(is_fit)
        self.btn_fit.blockSignals(False)
        if not block_signals: 
            self.fit_toggled.emit(is_fit)
            self.update_zoom_label(self.canvas.zoom_factor)

    def on_zoom_edited(self):
        if self.edit_zoom.isReadOnly(): return
        try:
            val = float(self.edit_zoom.text().replace("%", "").strip()) / 100.0
            if 0.1 <= val <= 10.0:
                if self.is_fit_mode: self.set_fit_mode(False)
                self.canvas.set_zoom(val)
        except: self.update_zoom_label(self.canvas.zoom_factor)

    def zoom_in(self):
        if self.is_fit_mode: self.set_fit_mode(False)
        self.canvas.set_zoom(self.canvas.zoom_factor + (0.01 if (self.is_slave and self.sync_active) else 0.1))

    def zoom_out(self):
        if self.is_fit_mode: self.set_fit_mode(False)
        self.canvas.set_zoom(max(0.1, self.canvas.zoom_factor - (0.01 if (self.is_slave and self.sync_active) else 0.1)))

    def update_zoom_label(self, factor):
        if self.is_slave and self.sync_active and self.controller:
            delta = self.controller._zoom_delta
            self.edit_zoom.setText(f"Δ {delta:+.0%}" if abs(delta) >= 0.005 else "Δ 0%")
            self.edit_zoom.setReadOnly(True)
        else:
            self.edit_zoom.setText(f"{factor:.0%}")
            self.edit_zoom.setReadOnly(False)
