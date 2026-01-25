from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QSpinBox, QFrame, QMessageBox, QFileDialog, QSizePolicy
)
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtCore import QUrl, Qt, QPointF, pyqtSignal, QSettings, QTemporaryFile
from pathlib import Path
import fitz
import os
import shutil
import tempfile

class PdfViewerWidget(QWidget):
    """
    High-Performance PDF Viewer / Editor.
    Uses QPdfView for fluid zooming/navigation and fitz for real-time virtual document previews.
    """
    # Signals
    stamp_requested = pyqtSignal(str)
    tags_update_requested = pyqtSignal(list)
    reprocess_requested = pyqtSignal(list)
    export_requested = pyqtSignal(list)
    delete_requested = pyqtSignal(str)
    split_requested = pyqtSignal(str)
    
    def __init__(self, pipeline=None, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.current_uuid = None
        
        # State
        self.temp_pdf_path = None
        self.current_pages_data = [] # List of {file_path, page_index, rotation}
        
        # UI Components
        self.document = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        
        # Style: White Background for document area
        self.view.setStyleSheet("background-color: white; border: none;")
        
        self._init_ui()
        self.restore_zoom_state()
        
    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Toolbar
        self.toolbar = QWidget()
        self.toolbar.setStyleSheet("background: #f0f0f0; border-bottom: 1px solid #ccc;")
        self.toolbar_layout = QHBoxLayout(self.toolbar)
        self.toolbar_layout.setContentsMargins(10, 5, 10, 5)
        
        # --- Group 1: Navigation ---
        self.btn_prev = QPushButton("<")
        self.btn_prev.setFixedSize(30,30)
        self.btn_prev.clicked.connect(self.prev_page)
        
        self.spin_page = QSpinBox()
        self.spin_page.setFixedSize(60, 30)
        self.spin_page.setKeyboardTracking(False)
        self.spin_page.valueChanged.connect(self.jump_to_page)
        
        self.lbl_total = QLabel("/ 0")
        
        self.btn_next = QPushButton(">")
        self.btn_next.setFixedSize(30,30)
        self.btn_next.clicked.connect(self.next_page)
        
        # --- Group 2: Zoom ---
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setFixedSize(30, 30)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setFixedWidth(40)
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setFixedSize(30, 30)
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setCheckable(True)
        self.btn_fit.setFixedSize(50, 30)
        self.btn_fit.clicked.connect(self.toggle_fit)
        
        # --- Group 3: Stage 0 Actions ---
        self.btn_rotate = QPushButton("↻")
        self.btn_rotate.setFixedSize(35, 30)
        self.btn_rotate.setToolTip("Rotate Page")
        self.btn_rotate.clicked.connect(self.rotate_current_page)
        
        self.btn_delete = QPushButton("🗑")
        self.btn_delete.setFixedSize(35, 30)
        self.btn_delete.setToolTip("Delete Page")
        self.btn_delete.clicked.connect(self.delete_current_page)
        self.btn_delete.setStyleSheet("background: #ffeeee; color: #cc0000;")
        
        self.btn_split = QPushButton("✂")
        self.btn_split.setFixedSize(35, 30)
        self.btn_split.setToolTip("Split Document")
        self.btn_split.clicked.connect(self.on_split_clicked)
        
        self.btn_save = QPushButton("💾 Save *")
        self.btn_save.setFixedSize(80, 30)
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_save.setStyleSheet("background: #4CAF50; color: white; font-weight: bold;")
        self.btn_save.setVisible(False)

        # Assemble Toolbar
        self.toolbar_layout.addWidget(self.btn_prev)
        self.toolbar_layout.addWidget(self.spin_page)
        self.toolbar_layout.addWidget(self.lbl_total)
        self.toolbar_layout.addWidget(self.btn_next)
        
        self._add_separator()
        
        self.toolbar_layout.addWidget(self.btn_zoom_out)
        self.toolbar_layout.addWidget(self.lbl_zoom)
        self.toolbar_layout.addWidget(self.btn_zoom_in)
        self.toolbar_layout.addWidget(self.btn_fit)
        
        self._add_separator()
        
        self.toolbar_layout.addWidget(self.btn_rotate)
        self.toolbar_layout.addWidget(self.btn_delete)
        self.toolbar_layout.addWidget(self.btn_split)
        
        # Ensure toolbar doesn't prevent shrinking
        self.toolbar.setMinimumWidth(0)
        self.toolbar_layout.setStretch(12, 1) # Add stretch after buttons
        
        self.toolbar_layout.addStretch()
        self.toolbar_layout.addWidget(self.btn_save)
        
        self.main_layout.addWidget(self.toolbar)
        self.main_layout.addWidget(self.view)
        
        # Connect Signals
        self.view.zoomFactorChanged.connect(self.update_zoom_label)
        self.nav = self.view.pageNavigator()
        self.nav.currentPageChanged.connect(self.on_page_changed)
        self.document.statusChanged.connect(self.on_document_status)
        
        self.enable_controls(False)

    def _add_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        self.toolbar_layout.addWidget(line)

    def load_document(self, file_path_or_uuid, uuid: str = None, initial_page: int = 1):
        """Standard entry point from MainWindow."""
        self.clear()
        
        if uuid:
            self.current_uuid = uuid
        else:
            # If it's a string and NOT an existing path, assume it's a UUID
            if isinstance(file_path_or_uuid, str) and not os.path.exists(file_path_or_uuid):
                self.current_uuid = file_path_or_uuid
                
        if self.pipeline and self.current_uuid:
            if not self._load_from_entity(self.current_uuid):
                # Fallback: Try loading as physical file from vault
                path = self.pipeline.vault.get_file_path(self.current_uuid)
                if path and os.path.exists(path):
                    self._load_from_raw_path(path)
        elif isinstance(file_path_or_uuid, str) and os.path.exists(file_path_or_uuid):
            self._load_from_raw_path(file_path_or_uuid)

    def _load_from_entity(self, entity_uuid) -> bool:
        """Returns True if successfully loaded as entity."""
        v_doc = self.pipeline.logical_repo.get_by_uuid(entity_uuid)
        if not v_doc or not v_doc.source_mapping:
            return False
            
        self.current_pages_data = []
        for ref in v_doc.source_mapping:
            phys_path = self.pipeline.vault.get_file_path(ref.file_uuid)
            if not phys_path: continue
            
            for p_num in ref.pages:
                self.current_pages_data.append({
                    "file_path": phys_path,
                    "file_uuid": ref.file_uuid,
                    "page_index": p_num - 1,
                    "rotation": getattr(ref, 'rotation', 0)
                })
        
        self._refresh_preview()
        return True

    def _load_from_raw_path(self, path):
        try:
            doc = fitz.open(path)
            self.current_pages_data = []
            for i in range(doc.page_count):
                self.current_pages_data.append({
                    "file_path": path,
                    "file_uuid": None,
                    "page_index": i,
                    "rotation": 0
                })
            doc.close()
            self._refresh_preview()
        except:
            pass

    def _refresh_preview(self):
        """Generate temporary PDF and update viewer."""
        if not self.current_pages_data:
            self.clear()
            return
            
        # 1. Create Preview PDF using fitz
        try:
            preview_doc = fitz.open()
            for pg in self.current_pages_data:
                src = fitz.open(pg["file_path"])
                preview_doc.insert_pdf(src, from_page=pg["page_index"], to_page=pg["page_index"])
                
                # Apply Rotation to the LAST page added
                new_page = preview_doc[-1]
                if pg["rotation"] != 0:
                    new_page.set_rotation(pg["rotation"])
                src.close()
            
            # Save to temp
            fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix="kpf_preview_")
            os.close(fd)
            preview_doc.save(temp_path)
            preview_doc.close()
            
            # 2. Load into QPdfView
            # QtPdf locks the file, so we must be careful with previous temp files
            self._swap_pdf_document(temp_path)
            
            # Cleanup old temp file after swap? 
            # Note: We keep the PATH to the CURRENT temp file to delete it later
            if self.temp_pdf_path and os.path.exists(self.temp_pdf_path):
                 try: os.remove(self.temp_pdf_path)
                 except: pass
            self.temp_pdf_path = temp_path
            
        except Exception as e:
            print(f"Error refreshing preview: {e}")

    def _swap_pdf_document(self, path):
        """Safely swap the document in the viewer."""
        # Detach and re-create to ensure no locks/ghosts
        self.view.setDocument(None)
        if self.document:
            self.document.deleteLater()
            
        self.document = QPdfDocument(self)
        self.document.statusChanged.connect(self.on_document_status)
        self.view.setDocument(self.document)
        self.document.load(path)
        
        # Re-acquire navigator
        self.nav = self.view.pageNavigator()
        self.nav.currentPageChanged.connect(self.on_page_changed)

    def on_document_status(self, status):
        if status == QPdfDocument.Status.Ready:
            count = self.document.pageCount()
            self.lbl_total.setText(f"/ {count}")
            self.spin_page.blockSignals(True)
            self.spin_page.setRange(1, count)
            # Maintain current page if possible
            curr = self.nav.currentPage()
            self.spin_page.setValue(curr + 1)
            self.spin_page.blockSignals(False)
            self.enable_controls(True)
            self.restore_zoom_state()
            
            # Show/Hide split
            self.btn_split.setVisible(count > 1)
            
        elif status == QPdfDocument.Status.Error:
            self.enable_controls(False)

    def enable_controls(self, enabled: bool):
        for btn in [self.btn_prev, self.btn_next, self.btn_zoom_in, self.btn_zoom_out, 
                    self.btn_fit, self.btn_rotate, self.btn_delete, self.spin_page]:
            btn.setEnabled(enabled)

    # --- Actions ---
    def rotate_current_page(self):
        idx = self.nav.currentPage()
        if 0 <= idx < len(self.current_pages_data):
            self.current_pages_data[idx]["rotation"] = (self.current_pages_data[idx]["rotation"] + 90) % 360
            self.btn_save.setVisible(True)
            self._refresh_preview()
            
    def delete_current_page(self):
        idx = self.nav.currentPage()
        if 0 <= idx < len(self.current_pages_data):
            if len(self.current_pages_data) <= 1:
                QMessageBox.warning(self, "Warning", "Cannot delete the last page. Delete the entire document from the list instead.")
                return
            self.current_pages_data.pop(idx)
            self.btn_save.setVisible(True)
            self._refresh_preview()

    def on_split_clicked(self):
        if self.current_uuid:
            self.split_requested.emit(self.current_uuid)

    def save_changes(self):
        if not self.pipeline or not self.current_uuid:
            return
            
        from core.models.virtual import SourceReference
        new_mapping = []
        
        current_file_uuid = None
        current_rot = -1
        current_pages = []
        
        for pg in self.current_pages_data:
            f_uuid = pg["file_uuid"]
            p_num = pg["page_index"] + 1
            rot = pg["rotation"]
            
            if f_uuid != current_file_uuid or rot != current_rot:
                if current_pages:
                    new_mapping.append(SourceReference(current_file_uuid, current_pages, current_rot))
                current_file_uuid = f_uuid
                current_rot = rot
                current_pages = [p_num]
            else:
                current_pages.append(p_num)
                
        if current_pages:
            new_mapping.append(SourceReference(current_file_uuid, current_pages, current_rot))
            
        try:
            self.pipeline.update_entity_structure(self.current_uuid, new_mapping)
            self.btn_save.setVisible(False)
            QMessageBox.information(self, "Saved", "Document changes saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    # --- Zoom / Nav ---
    def prev_page(self):
        curr = self.nav.currentPage()
        if curr > 0: self.nav.jump(curr - 1, QPointF(), self.nav.currentZoom())

    def next_page(self):
        curr = self.nav.currentPage()
        if curr < self.document.pageCount() - 1:
             self.nav.jump(curr + 1, QPointF(), self.nav.currentZoom())

    def jump_to_page(self, page_num):
        if 1 <= page_num <= self.document.pageCount():
            self.nav.jump(page_num - 1, QPointF(), self.nav.currentZoom())

    def on_page_changed(self, page):
        self.spin_page.blockSignals(True)
        self.spin_page.setValue(page + 1)
        self.spin_page.blockSignals(False)

    def zoom_in(self):
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.btn_fit.setChecked(False)
        self.view.setZoomFactor(self.view.zoomFactor() * 1.2)

    def zoom_out(self):
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.btn_fit.setChecked(False)
        self.view.setZoomFactor(self.view.zoomFactor() / 1.2)

    def toggle_fit(self, checked):
        if checked:
            self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        else:
            self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.save_zoom_state()

    def update_zoom_label(self, factor):
        self.lbl_zoom.setText(f"{int(factor * 100)}%")
        self.save_zoom_state()

    def save_zoom_state(self):
        settings = QSettings("KPaperFlux", "PdfViewer")
        settings.setValue("zoomFactor", self.view.zoomFactor())
        settings.setValue("zoomMode", self.view.zoomMode().value)

    def restore_zoom_state(self):
        settings = QSettings("KPaperFlux", "PdfViewer")
        try:
            factor = float(settings.value("zoomFactor", 1.0))
            mode_val = int(settings.value("zoomMode", QPdfView.ZoomMode.Custom.value))
            mode = QPdfView.ZoomMode(mode_val)
            self.view.setZoomMode(mode)
            if mode == QPdfView.ZoomMode.Custom:
                self.view.setZoomFactor(factor)
            self.btn_fit.setChecked(mode == QPdfView.ZoomMode.FitInView)
        except:
            pass

    def clear(self):
        self.view.setDocument(None)
        if self.document:
             self.document.deleteLater()
             self.document = None
        self.current_uuid = None
        self.current_pages_data = []
        self.lbl_total.setText("/ 0")
        self.spin_page.setRange(0, 0)
        self.enable_controls(False)
        self.btn_save.setVisible(False)
        self.btn_split.setVisible(False)
        
        if self.temp_pdf_path and os.path.exists(self.temp_pdf_path):
             try: os.remove(self.temp_pdf_path)
             except: pass
             self.temp_pdf_path = None

    def __del__(self):
        """Force cleanup of temp files."""
        if self.temp_pdf_path and os.path.exists(self.temp_pdf_path):
             try: os.remove(self.temp_pdf_path)
             except: pass
