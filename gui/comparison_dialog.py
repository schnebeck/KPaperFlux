from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtCore import Qt, QSettings
from gui.pdf_viewer import DualPdfViewerWidget
import os

class ComparisonDialog(QDialog):
    """
    Modal dialog for side-by-side document comparison.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Document Comparison"))
        
        # Geometry Persistence
        self.settings = QSettings("KPaperFlux", "ComparisonDialog")
        self.restore_geometry()
        
        # Store pipeline if parent has it
        self.pipeline = getattr(parent, 'pipeline', None)
        
        self.layout = QVBoxLayout(self)
        self.dual_viewer = DualPdfViewerWidget(self)
        self.layout.addWidget(self.dual_viewer)
        
        # Bottom Buttons
        self.btn_layout = QHBoxLayout()
        self.btn_close = QPushButton(self.tr("Close"))
        self.btn_close.setFixedWidth(120)
        self.btn_close.setFixedHeight(35)
        self.btn_close.setStyleSheet("font-weight: bold;")
        self.btn_close.clicked.connect(self.accept)
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.btn_close)
        
        self.layout.addLayout(self.btn_layout)

    def restore_geometry(self):
        geom = self.settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(1200, 800)

    def closeEvent(self, event: QCloseEvent):
        self.settings.setValue("geometry", self.saveGeometry())
        self.dual_viewer.stop()
        super().closeEvent(event)

    def load_comparison(self, left_path, right_path):
        self.dual_viewer.load_documents(left_path, right_path)
