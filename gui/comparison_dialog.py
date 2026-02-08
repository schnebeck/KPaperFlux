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
        self.dual_viewer.close_requested.connect(self.accept)
        self.layout.addWidget(self.dual_viewer)

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
