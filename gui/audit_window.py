from core.logger import get_logger, get_silent_logger
logger = get_logger("gui.audit_window")
import tempfile
import os
from datetime import datetime
from typing import Any, Dict, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTextEdit, 
    QLabel, QFrame, QScrollArea, QPushButton, QMainWindow, QStackedWidget
)
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtCore import Qt, pyqtSignal, QMarginsF, QEvent, QSettings
from PyQt6.QtGui import QFont, QTextDocument, QPageLayout
try:
    from PyQt6.QtPrintSupport import QPrinter
except ImportError as e:
    import sys
    logger.error(f"Critical internal import failed in audit_window.py (PyQt6.QtPrintSupport): {e}")
    sys.exit(1)

from core.models.virtual import VirtualDocument as Document
from core.semantic_renderer import SemanticRenderer
from core.pdf_renderer import ProfessionalPdfRenderer
from core.workflow import build_workflow_data
from gui.widgets.workflow_controls import WorkflowControlsWidget
from gui.pdf_viewer import PdfViewerWidget
from gui.workers import SemanticRenderingWorker

logger = get_logger("Audit")

class AuditWindow(QMainWindow):
    """
    A non-modal window for side-by-side verification of document vs. extracted data.
    """
    closed = pyqtSignal()
    workflow_triggered = pyqtSignal(str, str, str, bool)  # rule_id, action, target, is_auto

    def __init__(self, pipeline=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("KPaperFlux - Audit and Verification"))
        self.resize(1300, 900)
        
        self.pipeline = pipeline
        self.renderer = SemanticRenderer(locale="de") # Force DE for these specific requirements
        self.current_doc = None
        self.temp_files = []
        self._render_worker = None
        
        self._init_ui()
        self.read_settings()

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
        
        controls_layout.addStretch(1)  # Left Stretch

        self._workflow_controls: Dict[str, WorkflowControlsWidget] = {}
        self.workflow_controls_container = QWidget()
        self._workflow_controls_layout = QHBoxLayout(self.workflow_controls_container)
        self._workflow_controls_layout.setContentsMargins(0, 0, 0, 0)
        self._workflow_controls_layout.setSpacing(4)
        controls_layout.addWidget(self.workflow_controls_container)

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
        self.setWindowTitle(self.tr("KPaperFlux - Audit and Verification"))
        self.btn_close.setText(self.tr("Close"))
        self.lbl_loading.setText(self.tr("Generating comparison document..."))
        if not self.current_doc:
             self.render_view.setPlainText(self.tr("No document selected."))

    def set_debug_mode(self, enabled: bool):
        """Hides workflow controls and shows only a close button."""
        self.workflow_controls_container.setVisible(not enabled)
        self.btn_close.setVisible(enabled)
        if enabled:
            self.setWindowTitle(f"DEBUG: {self.windowTitle()}")

    def write_settings(self):
        """Saves current window layout to persistent storage."""
        settings = QSettings()
        settings.beginGroup("AuditWindow")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("splitter", self.splitter.saveState())
        settings.endGroup()

    def read_settings(self):
        """Restores window layout from persistent storage."""
        settings = QSettings()
        settings.beginGroup("AuditWindow")
        
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
            
        splitter_state = settings.value("splitter")
        if splitter_state:
            self.splitter.restoreState(splitter_state)
            
        settings.endGroup()

    def display_document(self, doc: Document):
        """Updates the audit view with a new document's data."""
        if not doc:
            self.render_view.setPlainText(self.tr("No document selected."))
            self.pdf_viewer.clear()
            return

        # Load PDF
        self.current_doc = doc
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

        # Update Workflow & Title Immediately
        self._refresh_workflow_controls()
        self.setWindowTitle(f"Audit: {doc.original_filename or doc.uuid}")

    def _refresh_workflow_controls(self):
        """Updates workflow control widgets based on current_doc's workflows dict."""
        doc = self.current_doc
        if not doc:
            return

        now = datetime.now()
        workflows = doc.semantic_data.workflows if doc.semantic_data else {}

        # Remove stale controls
        for rid in set(self._workflow_controls) - set(workflows):
            ctrl = self._workflow_controls.pop(rid)
            ctrl.setParent(None)

        # Add/update controls
        for rid, wf_info in workflows.items():
            if rid not in self._workflow_controls:
                ctrl = WorkflowControlsWidget()
                ctrl.transition_triggered.connect(self.workflow_triggered.emit)
                self._workflow_controls[rid] = ctrl
                self._workflow_controls_layout.addWidget(ctrl)

            days_in_state = 0
            try:
                entered_ts = wf_info.current_step_entered_at or (
                    wf_info.history[-1].timestamp if wf_info.history else None
                )
                if entered_ts:
                    days_in_state = (now - datetime.fromisoformat(entered_ts)).days
            except Exception as e:
                logger.debug(f"DAYS_IN_STATE skipped for {rid}: {e}")

            wf_doc_data = build_workflow_data(doc, days_in_state)
            self._workflow_controls[rid].update_workflow(rid, wf_info.current_step, wf_doc_data)

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


    def closeEvent(self, event):
        self.write_settings()
        
        # Cleanup worker
        if self._render_worker and self._render_worker.isRunning():
            self._render_worker.terminate()
            self._render_worker.wait()
            
        # Cleanup temp files
        for f in self.temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception as e:
                get_silent_logger().debug(f"Audit: Could not remove temp file {f}: {e}")
        self.temp_files = []
        
        self.closed.emit()
        super().closeEvent(event)
