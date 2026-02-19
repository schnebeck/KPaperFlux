import logging
import tempfile
import os
from datetime import datetime
from typing import Any, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTextEdit, 
    QLabel, QFrame, QScrollArea, QPushButton, QMainWindow, QStackedWidget
)
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtCore import Qt, pyqtSignal, QMarginsF, QEvent
from PyQt6.QtGui import QFont, QTextDocument, QPageLayout
try:
    from PyQt6.QtPrintSupport import QPrinter
except ImportError:
    QPrinter = None

from core.models.virtual import VirtualDocument as Document
from core.semantic_renderer import SemanticRenderer
from core.pdf_renderer import ProfessionalPdfRenderer
from gui.widgets.workflow_controls import WorkflowControlsWidget
from gui.pdf_viewer import PdfViewerWidget
from gui.workers import SemanticRenderingWorker

logger = logging.getLogger("KPaperFlux.Audit")

class AuditWindow(QMainWindow):
    """
    A non-modal window for side-by-side verification of document vs. extracted data.
    """
    closed = pyqtSignal()
    workflow_triggered = pyqtSignal(str, str, bool) # action, target, is_auto

    def __init__(self, pipeline=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("KPaperFlux - Audit & Verification"))
        self.resize(1300, 900)
        
        self.pipeline = pipeline
        self.renderer = SemanticRenderer(locale="de") # Force DE for these specific requirements
        self.current_doc = None
        self.temp_files = []
        self._render_worker = None
        
        self._init_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 1. Left: Original Document (Real PDF Viewer)
        self.pdf_viewer = PdfViewerWidget(pipeline=self.pipeline)
        self.pdf_viewer.set_toolbar_policy('audit')
        # Keep toolbar visible for consistency
        self.pdf_viewer.btn_split.hide()
        
        # 2. Right Pane (Stack for PDF/Fallback)
        self.right_container = QWidget()
        right_layout = QVBoxLayout(self.right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.right_stack = QStackedWidget()
        
        # Fallback Render View (Markdown/HTML)
        self.render_view = QTextEdit()
        self.render_view.setReadOnly(True)
        self.render_view.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                color: #2c3e50;
                font-size: 14px;
                padding: 20px;
            }
        """)
        
        # Premium Render View (Generated PDF)
        self.rendered_pdf_viewer = PdfViewerWidget(pipeline=self.pipeline, is_slave=True)
        self.rendered_pdf_viewer.set_toolbar_policy('audit')
        # Symmetrical look: Keep toolbar
        self.rendered_pdf_viewer.btn_split.hide()
        self.rendered_pdf_viewer.btn_save.hide()
        
        # Loading / Progress View
        self.loading_view = QWidget()
        loading_layout = QVBoxLayout(self.loading_view)
        self.lbl_loading = QLabel()
        self.lbl_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_loading.setStyleSheet("""
            font-size: 18px; 
            font-weight: 500; 
            color: #1565c0; 
            background: white;
            padding: 40px;
        """)
        loading_layout.addStretch()
        loading_layout.addWidget(self.lbl_loading)
        loading_layout.addStretch()

        self.right_stack.addWidget(self.rendered_pdf_viewer) # 0
        self.right_stack.addWidget(self.render_view)         # 1
        self.right_stack.addWidget(self.loading_view)        # 2
        right_layout.addWidget(self.right_stack)

        self.splitter.addWidget(self.pdf_viewer)
        self.splitter.addWidget(self.right_container)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        
        layout.addWidget(self.splitter, stretch=1)

        # Bottom: Centered Controls
        self.controls_frame = QFrame()
        self.controls_frame.setFixedHeight(60)
        self.controls_frame.setStyleSheet("background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 4px;")
        controls_layout = QHBoxLayout(self.controls_frame)
        
        controls_layout.addStretch(1) # Left Stretch
        
        self.workflow_controls = WorkflowControlsWidget()
        self.workflow_controls.transition_triggered.connect(self.workflow_triggered.emit)
        controls_layout.addWidget(self.workflow_controls)

        self.btn_close = QPushButton()
        self.btn_close.setFixedWidth(120)
        self.btn_close.clicked.connect(self.close)
        self.btn_close.hide() # Hidden by default
        controls_layout.addWidget(self.btn_close)
        
        controls_layout.addStretch(1) # Right Stretch (Centers everything in between)
        
        layout.addWidget(self.controls_frame)
        
        self.retranslate_ui()
        
        # Default to Fit Zoom for Audit
        self.pdf_viewer.set_fit_mode(True)
        self.rendered_pdf_viewer.set_fit_mode(True)

    def changeEvent(self, event: QEvent) -> None:
        """Handle language change events."""
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self) -> None:
        """Updates all UI strings for on-the-fly localization."""
        self.setWindowTitle(self.tr("KPaperFlux - Audit & Verification"))
        self.btn_close.setText(self.tr("Close"))
        self.lbl_loading.setText(self.tr("Generating comparison document..."))
        if not self.current_doc:
             self.render_view.setPlainText(self.tr("No document selected."))

    def set_debug_mode(self, enabled: bool):
        """Hides workflow controls and shows only a close button."""
        self.workflow_controls.setVisible(not enabled)
        self.btn_close.setVisible(enabled)
        if enabled:
            self.setWindowTitle(f"DEBUG: {self.windowTitle()}")

    def display_document(self, doc: Document):
        """Updates the audit view with a new document's data."""
        if not doc:
            self.render_view.setPlainText(self.tr("No document selected."))
            self.pdf_viewer.clear()
            return

        # Load PDF
        self.pdf_viewer.load_document(doc)

        # Render Semantic Data
        if doc.semantic_data:
            self.right_stack.setCurrentWidget(self.loading_view)
            
            # Create a temp file for the PDF
            fd, pdf_path = tempfile.mkstemp(suffix=".pdf", prefix="audit_render_")
            os.close(fd)
            self.temp_files.append(pdf_path)

            # Cleanup previous worker if any
            if self._render_worker and self._render_worker.isRunning():
                self._render_worker.terminate()
                self._render_worker.wait()

            self._render_worker = SemanticRenderingWorker(
                doc.semantic_data, 
                pdf_path, 
                locale=self.renderer.locale,
                parent=self
            )
            self._render_worker.finished.connect(lambda p: self._on_rendering_finished(p))
            self._render_worker.error.connect(lambda e: self._on_rendering_failed(e, doc.semantic_data))
            self._render_worker.start()
        else:
            self.render_view.setHtml("<div style='text-align: center; padding-top: 100px; color: #666; font-style: italic;'>"
                                     "Keine semantischen Daten vorhanden.</div>")
            self.right_stack.setCurrentWidget(self.render_view)

    def _on_rendering_finished(self, pdf_path: str):
        """Called when background PDF generation is done."""
        # CRITICAL: Don't pass a UUID here, otherwise the viewer tries to load from DB/Vault
        # instead of the raw path.
        self.rendered_pdf_viewer.load_document(pdf_path)
        self.right_stack.setCurrentWidget(self.rendered_pdf_viewer)

    def _on_rendering_failed(self, error_msg: str, semantic_data: Any):
        """Fallback if PDF generation fails."""
        logger.error(f"Professional PDF rendering failed: {error_msg}")
        try:
            html_content = self.renderer.render_as_html(semantic_data)
            self.render_view.setHtml(html_content)
        except Exception as e:
            logger.warning(f"HTML rendering fallback failed: {e}")
            md_content = self.renderer.render_as_markdown(semantic_data)
            self.render_view.setMarkdown(md_content)
        self.right_stack.setCurrentWidget(self.render_view)

        # Prepare flat data for requirement check (Sync with MetadataEditor)
        wf_data = getattr(doc.semantic_data, "workflow", None)
        rule_id = wf_data.rule_id if wf_data else None
        current_step = wf_data.current_step if wf_data else "NEW"
        
        now = datetime.now()
        doc_data_for_wf = {
            "total_gross": doc.total_amount,
            "iban": doc.iban,
            "sender_name": doc.sender_name,
            "doc_date": doc.doc_date,
            "doc_number": doc.doc_number,
            "AGE_DAYS": 0,
            "DAYS_IN_STATE": 0,
            "DAYS_UNTIL_DUE": 999
        }
        
        try:
            if doc.created_at:
                doc_data_for_wf["AGE_DAYS"] = (now - datetime.fromisoformat(doc.created_at)).days
            
            if wf_data and wf_data.history:
                last_ts = wf_data.history[-1].timestamp
                doc_data_for_wf["DAYS_IN_STATE"] = (now - datetime.fromisoformat(last_ts)).days
                
            if doc.due_date:
                dd_str = doc.due_date
                if len(dd_str) == 10: dd_str += "T00:00:00"
                doc_data_for_wf["DAYS_UNTIL_DUE"] = (datetime.fromisoformat(dd_str) - now).days
        except Exception as e:
            logger.debug(f"Time calculation failed: {e}")

        self.workflow_controls.update_workflow(rule_id, current_step, doc_data_for_wf)
        
        self.setWindowTitle(f"Audit: {doc.original_filename or doc.uuid}")


    def closeEvent(self, event):
        # Cleanup worker
        if self._render_worker and self._render_worker.isRunning():
            self._render_worker.terminate()
            self._render_worker.wait()
            
        # Cleanup temp files
        for f in self.temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except: pass
        self.temp_files = []
        
        self.closed.emit()
        super().closeEvent(event)
