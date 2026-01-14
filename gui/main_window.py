from typing import Optional
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QFileDialog, QMessageBox
from core.pipeline import PipelineProcessor

class MainWindow(QMainWindow):
    """
    Main application window for KPaperFlux.
    """
    def __init__(self, pipeline: Optional[PipelineProcessor] = None):
        super().__init__()
        self.pipeline = pipeline
        self.setWindowTitle("KPaperFlux")
        self.resize(800, 600)
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout
        layout = QVBoxLayout(central_widget)
        
        # Widgets
        self.label = QLabel("KPaperFlux v1.0")
        layout.addWidget(self.label)
        
        self.btn_import = QPushButton("Import Documents")
        self.btn_import.setObjectName("btn_import")
        self.btn_import.clicked.connect(self.import_document_slot)
        layout.addWidget(self.btn_import)

    def import_document_slot(self):
        """Handle import button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Document", "", "PDF Files (*.pdf);;All Files (*)"
        )
        
        if file_path and self.pipeline:
            try:
                doc = self.pipeline.process_document(file_path)
                QMessageBox.information(
                    self, "Success", f"Document imported successfully!\nUUID: {doc.uuid}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to process document: {e}"
                )
        elif not self.pipeline:
            # Fallback/Debug if pipeline is missing
            print(f"Selected: {file_path}, but no pipeline connected.")
