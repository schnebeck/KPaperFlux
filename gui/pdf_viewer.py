
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox, QFrame, QMenu
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtCore import QUrl, Qt, QPoint, QPointF, pyqtSignal
from pathlib import Path

class PdfViewerWidget(QWidget):
    """
    Modern PDF Viewer using QtPdf (Qt6).
    """
    stamp_requested = pyqtSignal(str)
    tags_update_requested = pyqtSignal(list)
    reprocess_requested = pyqtSignal(list)
    export_requested = pyqtSignal(list)
    delete_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.current_uuid = None
        self.document = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(5, 5, 5, 5)
        
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setFixedWidth(30)
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setFixedWidth(30)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        
        self.lbl_zoom = QLabel("100%")
        
        self.btn_fit = QPushButton(self.tr("Fit"))
        self.btn_fit.setCheckable(True)
        self.btn_fit.clicked.connect(self.toggle_fit)
        
        # Navigation
        self.btn_prev = QPushButton("<")
        self.btn_prev.setFixedWidth(30)
        self.btn_prev.clicked.connect(self.prev_page)
        
        self.spin_page = QSpinBox()
        self.spin_page.setKeyboardTracking(False) # Jump only on Enter/FocusOut
        self.spin_page.valueChanged.connect(self.jump_to_page)
        
        self.lbl_total = QLabel("/ 0")
        
        self.btn_next = QPushButton(">")
        self.btn_next.setFixedWidth(30)
        self.btn_next.clicked.connect(self.next_page)
        
        toolbar.addStretch()
        toolbar.addWidget(QLabel(self.tr("Page:")))
        toolbar.addWidget(self.btn_prev)
        toolbar.addWidget(self.spin_page)
        toolbar.addWidget(self.lbl_total)
        toolbar.addWidget(self.btn_next)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        toolbar.addWidget(line)
        
        toolbar.addWidget(QLabel(self.tr("Zoom:")))
        toolbar.addWidget(self.btn_zoom_out)
        toolbar.addWidget(self.lbl_zoom)
        toolbar.addWidget(self.btn_zoom_in)
        toolbar.addWidget(self.btn_fit)
        toolbar.addStretch()
        
        layout.addLayout(toolbar)
        layout.addWidget(self.view)
        
        # Connect signals
        self.view.zoomFactorChanged.connect(self.update_zoom_label)
        
        # Context Menu
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_context_menu)
        
        # Navigator
        self.nav = self.view.pageNavigator()
        self.nav.currentPageChanged.connect(self.on_page_changed)
        
        self.document.statusChanged.connect(self.on_document_status)
        
    def load_document(self, file_path: str, uuid: str = None):
        if not file_path:
            self.clear()
            return
            
        self.current_uuid = uuid
            
        path = Path(file_path).resolve()
        if not path.exists():
            self.clear()
            return
            
        try:
            # Re-create document to ensure fresh load and avoid "No file name" warnings from load("")
            # and to guarantee that the viewer picks up changes (caching issues).
            if self.document:
                self.view.setDocument(None) # Detach first
                self.document.deleteLater()
                self.document = None
                
            self.document = QPdfDocument(self)
            self.document.statusChanged.connect(self.on_document_status)
            
            # Note: We set document AFTER loading? No, QPdfView needs it. 
            # But maybe load first?
            # Qt docs say: setDocument then load usually works.
            
            self.view.setDocument(self.document)
            self.view.setPageMode(QPdfView.PageMode.MultiPage)
            
            # Re-acquire navigator
            self.nav = self.view.pageNavigator()
            # Disconnect old signals if any (safe due to try/except block below or recreation)
            try:
                self.nav.currentPageChanged.disconnect(self.on_page_changed)
            except Exception:
                pass
            self.nav.currentPageChanged.connect(self.on_page_changed)
            
            self.document.load(str(path))
        except Exception as e:
            print(f"Error loading PDF: {e}")
            self.clear()

    def unload(self):
        """Release the document file lock."""
        self.clear()
            
    def on_document_status(self, status):
        if status == QPdfDocument.Status.Ready:
            count = self.document.pageCount()
            self.lbl_total.setText(f"/ {count}")
            self.spin_page.blockSignals(True)
            self.spin_page.setRange(1, count)
            self.spin_page.setValue(1)
            self.spin_page.blockSignals(False)
            self.enable_controls(True)
        else:
            self.enable_controls(False)
            
    def enable_controls(self, enabled: bool):
        self.btn_zoom_in.setEnabled(enabled)
        self.btn_zoom_out.setEnabled(enabled)
        self.btn_fit.setEnabled(enabled)
        self.btn_prev.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)
        self.spin_page.setEnabled(enabled)
            
    def clear(self):
        # QPdfDocument doesn't have close/clear easily.
        # Load empty?
        # Re-instantiate is cleaner but heavy.
        # But we can hide view or disable controls
        self.current_uuid = None
        self.lbl_total.setText("/ 0")
        self.spin_page.setRange(0, 0)
        self.spin_page.clear()
        self.enable_controls(False)
        self.lbl_zoom.setText("-")

    def zoom_in(self):
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.btn_fit.setChecked(False)
        current = self.view.zoomFactor()
        self.view.setZoomFactor(current * 1.2)
        
    def zoom_out(self):
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.btn_fit.setChecked(False)
        current = self.view.zoomFactor()
        self.view.setZoomFactor(current / 1.2)
        
    def toggle_fit(self, checked):
        if checked:
            self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        else:
            self.view.setZoomMode(QPdfView.ZoomMode.Custom)
            # Restore current factor? Or keep what Fit set?
            # Usually keep factor.
        
    def update_zoom_label(self, factor):
        self.lbl_zoom.setText(f"{int(factor * 100)}%")
        
    def prev_page(self):
        curr = self.nav.currentPage()
        if curr > 0:
            self.nav.jump(curr - 1, QPointF(), self.nav.currentZoom())
        
    def next_page(self):
        curr = self.nav.currentPage()
        if curr < self.document.pageCount() - 1:
            self.nav.jump(curr + 1, QPointF(), self.nav.currentZoom())
        
    def jump_to_page(self, page_num):
        # 0-indexed internally
        if 1 <= page_num <= self.document.pageCount():
            self.nav.jump(page_num - 1, QPointF(), self.nav.currentZoom())
            
    def on_page_changed(self, page):
        self.spin_page.blockSignals(True)
        self.spin_page.setValue(page + 1)
        self.spin_page.blockSignals(False)

    def show_context_menu(self, pos: QPoint):
        if not self.current_uuid:
            return
            
        menu = QMenu(self)
        
        reprocess_action = menu.addAction(self.tr("Reprocess / Re-Analyze"))
        tags_action = menu.addAction(self.tr("Manage Tags..."))
        stamp_action = menu.addAction(self.tr("Stamp..."))
        menu.addSeparator()
        export_action = menu.addAction(self.tr("Export Document..."))
        menu.addSeparator()
        delete_action = menu.addAction(self.tr("Delete Document"))
        
        action = menu.exec(self.view.mapToGlobal(pos))
        
        if action == reprocess_action:
            self.reprocess_requested.emit([self.current_uuid])
        elif action == tags_action:
            self.tags_update_requested.emit([self.current_uuid])
        elif action == stamp_action:
            self.stamp_requested.emit(self.current_uuid)
        elif action == export_action:
            self.export_requested.emit([self.current_uuid])
        elif action == delete_action:
            self.delete_requested.emit(self.current_uuid)
