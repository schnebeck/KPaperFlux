from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QFrame
from PyQt6.QtGui import QCloseEvent, QIcon
from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from gui.pdf_viewer import DualPdfViewerWidget
import os

class ComparisonDialog(QDialog):
    """
    Modal dialog for side-by-side document comparison.
    Now supports user feedback on the match quality.
    """
    match_assessed = pyqtSignal(bool) # True = Correct, False = Incorrect

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Document Comparison"))
        
        # Settings and Pipeline
        self.settings = QSettings("KPaperFlux", "ComparisonDialog")
        self.pipeline = getattr(parent, 'pipeline', None)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 1. Main Viewer
        self.dual_viewer = DualPdfViewerWidget(self)
        self.dual_viewer.close_requested.connect(self.accept)
        self.layout.addWidget(self.dual_viewer, 1)

        # 2. MATCH ASSESSMENT OVERLAY / FOOTER
        self.feedback_frame = QFrame()
        self.feedback_frame.setStyleSheet("background-color: #f8f9fa; border-top: 1px solid #dee2e6;")
        f_layout = QHBoxLayout(self.feedback_frame)
        f_layout.setContentsMargins(15, 5, 15, 5) # Narrower vertical margin
        f_layout.setSpacing(10)
        
        self.btn_incorrect = QPushButton(self.tr("Mismatch"))
        self.btn_incorrect.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f; 
                color: white; 
                font-weight: bold; 
                padding: 4px 15px; 
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #b71c1c; }
        """)
        self.btn_incorrect.clicked.connect(self.on_match_incorrect)

        self.btn_correct = QPushButton(self.tr("Match OK"))
        self.btn_correct.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32; 
                color: white; 
                font-weight: bold; 
                padding: 4px 15px; 
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1b5e20; }
        """)
        self.btn_correct.clicked.connect(self.on_match_correct)
        
        f_layout.addStretch()
        f_layout.addWidget(self.btn_incorrect)
        f_layout.addWidget(self.btn_correct)
        f_layout.addStretch()
        
        self.layout.addWidget(self.feedback_frame)
        
        # Geometry Persistence (Call AFTER dual_viewer is created)
        self.restore_geometry()

    def on_match_correct(self):
        self.match_assessed.emit(True)
        self.accept()

    def on_match_incorrect(self):
        self.match_assessed.emit(False)
        self.accept()

    def restore_geometry(self):
        geom = self.settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(1200, 850)
        
        # Restore splitter state
        split_state = self.settings.value("splitter_state")
        if split_state:
            self.dual_viewer.splitter.restoreState(split_state)

    def save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter_state", self.dual_viewer.splitter.saveState())
        self.settings.sync()

    def done(self, r):
        self.save_settings()
        self.dual_viewer.stop()
        super().done(r)

    def closeEvent(self, event: QCloseEvent):
        self.save_settings()
        self.dual_viewer.stop()
        super().closeEvent(event)

    def load_comparison(self, left_path, right_path):
        self.dual_viewer.load_documents(left_path, right_path)
