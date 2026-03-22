from typing import Callable, Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                              QMessageBox, QProgressBar, QPushButton, QVBoxLayout)

from core.config import AppConfig
from core.exporter import DocumentExporter
from gui.utils import show_selectable_message_box
import os


class ExportWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)  # Success, ErrorMsg

    def __init__(
        self,
        documents: list,
        output_path: str,
        include_pdfs: bool,
        mode: str = "ZIP",
        path_resolver: Optional[Callable[[str], Optional[str]]] = None,
    ):
        super().__init__()
        self.documents = documents
        self.output_path = output_path
        self.include_pdfs = include_pdfs
        self.mode = mode
        self.path_resolver = path_resolver

    def run(self) -> None:
        try:
            if self.mode == "PDF_MERGE":
                DocumentExporter.export_to_pdf_batch(
                    self.documents,
                    self.output_path,
                    self.path_resolver,
                    self.progress.emit,
                )
            else:
                DocumentExporter.export_to_zip(
                    self.documents,
                    self.output_path,
                    self.include_pdfs,
                    self.progress.emit,
                    self.path_resolver,
                )
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))


class ExportDialog(QDialog):
    def __init__(
        self,
        parent=None,
        documents=None,
        path_resolver: Optional[Callable[[str], Optional[str]]] = None,
    ):
        super().__init__(parent)
        self.documents = documents or []
        self.path_resolver = path_resolver
        self.setWindowTitle(self.tr("Export Documents"))
        self.setMinimumWidth(400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Info
        layout.addWidget(QLabel(self.tr("Exporting %s documents.") % len(self.documents)))
        
        # Options
        self.chk_pdfs = QCheckBox(self.tr("Include PDF files (in 'documents/' folder)"))
        self.chk_pdfs.setChecked(True)
        layout.addWidget(self.chk_pdfs)

        self.chk_merge_pdf = QCheckBox(self.tr("Export as single MERGED PDF file"))
        self.chk_merge_pdf.toggled.connect(self._on_merge_toggled)
        layout.addWidget(self.chk_merge_pdf)
        
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
        if self.chk_merge_pdf.isChecked():
            caption = self.tr("Save Merged PDF")
            default_name = f"merged_{len(self.documents)}_docs.pdf"
            filter_str = self.tr("PDF Document (*.pdf)")
        else:
            caption = self.tr("Save Export Archive")
            default_name = f"export_{len(self.documents)}_docs.zip"
            filter_str = self.tr("ZIP Archive (*.zip)")

        filename, _ = QFileDialog.getSaveFileName(
            self, 
            caption,
            default_name,
            filter_str
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
            self.chk_pdfs.isChecked(),
            mode="PDF_MERGE" if self.chk_merge_pdf.isChecked() else "ZIP",
            path_resolver=self.path_resolver,
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
            show_selectable_message_box(self, self.tr("Error"), self.tr("Export failed:\n%s") % error_msg, icon=QMessageBox.Icon.Critical)
            self.btn_export.setEnabled(True)
            self.btn_transfer.setEnabled(True)

    def _on_merge_toggled(self, checked):
        """Update UI based on merge mode."""
        self.chk_pdfs.setEnabled(not checked)
        self.output_path = ""
        self.lbl_path.setText(self.tr("No file selected"))
        self.btn_export.setEnabled(False)

    def export_to_transfer(self):
        transfer_path = self.config.get_transfer_path()
        if not transfer_path or not os.path.exists(transfer_path):
            return

        filename = f"export_{len(self.documents)}_docs.zip"
        self.output_path = os.path.join(transfer_path, filename)
        
        # Check if file exists
        if os.path.exists(self.output_path):
            reply = show_selectable_message_box(self, self.tr("Confirm Overwrite"),
                                         self.tr("File '%s' already exists in transfer folder. Overwrite?") % filename,
                                         icon=QMessageBox.Icon.Question,
                                         buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.btn_transfer.setEnabled(False)
        self.start_export()
