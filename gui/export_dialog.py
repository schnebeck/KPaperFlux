from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,                              QLabel, QCheckBox, QFileDialog, QProgressBar, QMessageBox)
from gui.utils import show_selectable_message_box
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from core.exporter import DocumentExporter
from core.config import AppConfig
import os

class ExportWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str) # Success, ErrorMsg

    def __init__(self, documents, output_path, include_pdfs):
        super().__init__()
        self.documents = documents
        self.output_path = output_path
        self.include_pdfs = include_pdfs

    def run(self):
        try:
            DocumentExporter.export_to_zip(
                self.documents, 
                self.output_path, 
                self.include_pdfs, 
                self.progress.emit
            )
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))

class ExportDialog(QDialog):
    def __init__(self, parent=None, documents=None):
        super().__init__(parent)
        self.documents = documents or []
        self.setWindowTitle(self.tr("Export Documents"))
        self.setMinimumWidth(400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Info
        layout.addWidget(QLabel(self.tr(f"Exporting {len(self.documents)} documents.")))
        
        # Options
        self.chk_pdfs = QCheckBox(self.tr("Include PDF files (in 'documents/' folder)"))
        self.chk_pdfs.setChecked(True)
        layout.addWidget(self.chk_pdfs)
        
        # File Selection
        file_layout = QHBoxLayout()
        self.lbl_path = QLabel(self.tr("No file selected"))
        file_layout.addWidget(self.lbl_path, 1)
        
        btn_browse = QPushButton(self.tr("Browse..."))
        btn_browse.clicked.connect(self.browse_file)
        file_layout.addWidget(btn_browse)
        
        layout.addLayout(file_layout)
        self.output_path = ""
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_export = QPushButton(self.tr("Export"))
        self.btn_export.clicked.connect(self.start_export)
        self.btn_export.setEnabled(False)
        btn_layout.addWidget(self.btn_export)

        # Transfer Export Option
        self.btn_transfer = QPushButton(self.tr("Export to Transfer"))
        self.btn_transfer.clicked.connect(self.export_to_transfer)
        self.config = AppConfig()
        transfer_path = self.config.get_transfer_path()
        self.btn_transfer.setVisible(bool(transfer_path) and os.path.exists(transfer_path))
        btn_layout.addWidget(self.btn_transfer)
        
        self.btn_cancel = QPushButton(self.tr("Close"))
        self.btn_cancel.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)

    def browse_file(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, 
            self.tr("Save Export Archive"),
            f"export_{len(self.documents)}_docs.zip",
            self.tr("ZIP Archive (*.zip)")
        )
        if filename:
            if not filename.lower().endswith(".zip"):
                filename += ".zip"
            self.output_path = filename
            self.lbl_path.setText(filename)
            self.btn_export.setEnabled(True)

    def start_export(self):
        self.btn_export.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.worker = ExportWorker(
            self.documents, 
            self.output_path, 
            self.chk_pdfs.isChecked()
        )
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, success, error_msg):
        self.btn_cancel.setEnabled(True)
        if success:
            show_selectable_message_box(self, self.tr("Success"), self.tr("Export completed successfully."), icon=QMessageBox.Icon.Information)
            self.accept()
        else:
            show_selectable_message_box(self, self.tr("Error"), self.tr(f"Export failed:\n{error_msg}"), icon=QMessageBox.Icon.Critical)
            self.btn_export.setEnabled(True)
            self.btn_transfer.setEnabled(True)

    def export_to_transfer(self):
        transfer_path = self.config.get_transfer_path()
        if not transfer_path or not os.path.exists(transfer_path):
            return

        filename = f"export_{len(self.documents)}_docs.zip"
        self.output_path = os.path.join(transfer_path, filename)
        
        # Check if file exists
        if os.path.exists(self.output_path):
            reply = show_selectable_message_box(self, self.tr("Confirm Overwrite"),
                                         self.tr(f"File '{filename}' already exists in transfer folder. Overwrite?"),
                                         icon=QMessageBox.Icon.Question,
                                         buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.btn_transfer.setEnabled(False)
        self.start_export()
