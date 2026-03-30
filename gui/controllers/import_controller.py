"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/controllers/import_controller.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Handles all document import and Stage 2 semantic extraction
                operations.  Communicates back to the caller exclusively via
                Qt signals to avoid circular widget references.
------------------------------------------------------------------------------
"""

from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QDialog, QMessageBox, QProgressDialog

from core.logger import get_logger
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager

logger = get_logger("gui.import_controller")


class ImportController(QObject):
    """
    Owns all import and Stage-2 semantic extraction operations.

    Signal contract
    ---------------
    list_refresh_requested      → list_widget.refresh_list()
    stats_refresh_requested     → cockpit_widget.refresh_stats()
    status_updated(str)         → main_status_label.setText()
    splitter_dialog_requested(str)   → open_splitter_dialog_slot(uuid)
    """

    list_refresh_requested = pyqtSignal()
    stats_refresh_requested = pyqtSignal()
    status_updated = pyqtSignal(str)
    splitter_dialog_requested = pyqtSignal(str)

    # Forwarded to ProcessingController.reprocess_documents via facade wiring
    reprocess_requested = pyqtSignal(list)

    def __init__(
        self,
        parent: QObject,
        pipeline: Optional[PipelineProcessor],
        db_manager: Optional[DatabaseManager],
    ) -> None:
        super().__init__(parent)
        self._parent = parent
        self.pipeline = pipeline
        self.db_manager = db_manager
        self.import_worker = None

    # ── Import ────────────────────────────────────────────────────────────────

    def start_import(self, files: List[str], move_source: bool = False) -> None:
        """
        Unified entry point for importing documents (menu, drag-drop, transfer).
        Opens the Splitter preflight dialog for PDFs, then runs ImportWorker.
        """
        from gui.workers import ImportWorker
        from gui.splitter_dialog import SplitterDialog
        from core.utils.forensics import get_pdf_class, PDFClass

        if not files or not self.pipeline:
            return

        import_items = []
        pdf_files = [f for f in files if f.lower().endswith(".pdf")]
        other_files = [f for f in files if not f.lower().endswith(".pdf")]

        if pdf_files:
            file_infos = []
            for f in pdf_files:
                try:
                    p_class = get_pdf_class(f)
                    file_infos.append({
                        "path": f,
                        "pdf_class": p_class.value,
                        "is_protected": p_class != PDFClass.STANDARD,
                    })
                except Exception as e:
                    logger.error(f"Error classifying PDF {f}: {e}")
                    file_infos.append({"path": f, "pdf_class": "C", "is_protected": False})

            if file_infos:
                dialog = SplitterDialog(self.pipeline, self._parent)
                dialog.load_for_batch_import(file_infos)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    import_items.append(("BATCH", dialog.import_instructions))
                else:
                    logger.info("PDF Import cancelled by user.")

        for fpath in other_files:
            import_items.append((fpath, None))

        if not import_items:
            logger.info("No files to import (User cancelled all).")
            return

        is_batch = any(item[0] == "BATCH" for item in import_items if isinstance(item, tuple))

        count = 0
        for item in import_items:
            if isinstance(item, tuple) and item[0] == "BATCH" and isinstance(item[1], list):
                unique_files: set = set()
                for doc_instr in item[1]:
                    for pg in doc_instr.get("pages", []):
                        if "file_path" in pg:
                            unique_files.add(pg["file_path"])
                count += len(unique_files) + len(item[1])
            else:
                count += 1

        progress = QProgressDialog(
            self._parent.tr("Initializing Import..."),
            self._parent.tr("Cancel"),
            0, count, self._parent,
        )
        progress.setWindowTitle(self._parent.tr("Importing..."))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()

        self.import_worker = ImportWorker(self.pipeline, import_items, move_source=move_source)

        def _on_import_progress(i: int, label: str) -> None:
            self.status_updated.emit(
                self._parent.tr("Importing %s/%s: %s") % (i + 1, count, label)
            )
            progress.setValue(i + 1)

        def _on_document_imported(uid: str) -> None:
            self.list_refresh_requested.emit()
            self.stats_refresh_requested.emit()

        self.import_worker.progress.connect(_on_import_progress)
        self.import_worker.document_imported.connect(_on_document_imported)
        self.import_worker.finished.connect(
            lambda s, t, uuids, err: self._on_import_finished(s, t, uuids, err, progress, is_batch)
        )
        progress.canceled.connect(self.import_worker.cancel)
        self.import_worker.start()

    def _on_import_finished(
        self,
        success_count: int,
        total: int,
        imported_uuids: List[str],
        error_msg: Optional[str],
        progress_dialog: QProgressDialog,
        skip_splitter: bool,
    ) -> None:
        from gui.utils import show_notification, show_selectable_message_box

        progress_dialog.close()

        if self.import_worker:
            self.import_worker.wait()
            self.import_worker.deleteLater()
            self.import_worker = None

        if self.pipeline:
            self.pipeline.reset_cancellation()

        if error_msg:
            show_selectable_message_box(
                self._parent,
                self._parent.tr("Import Error"),
                error_msg,
                icon=QMessageBox.Icon.Warning,
            )

        self.list_refresh_requested.emit()

        splitter_opened = False
        if imported_uuids:
            for uid in imported_uuids:
                d = self.db_manager.get_document_by_uuid(uid) if self.db_manager else None
                if d is None:
                    logger.debug(f"Import Finished: UUID={uid} NOT FOUND in DB!")
                if d and d.page_count and d.page_count > 1 and not skip_splitter:
                    if not splitter_opened:
                        self.splitter_dialog_requested.emit(uid)
                        splitter_opened = True

        if not error_msg and not splitter_opened:
            show_notification(
                self._parent,
                self._parent.tr("Import Finished"),
                self._parent.tr("Imported %s documents.\nBackground processing started.")
                % len(imported_uuids),
            )

        self.stats_refresh_requested.emit()

    # ── Stage 2 / Semantic Extraction ─────────────────────────────────────────

    def run_stage_2(self, uuids: List[str]) -> None:
        """Trigger Stage 2 semantic extraction for a list of document UUIDs."""
        from gui.utils import show_selectable_message_box

        if not uuids:
            show_selectable_message_box(
                self._parent,
                self._parent.tr("Action required"),
                self._parent.tr("Please select at least one document."),
                icon=QMessageBox.Icon.Warning,
            )
            return

        to_shortcut = []
        to_full = []
        for uid in uuids:
            doc = self.db_manager.get_document_by_uuid(uid)
            if doc and doc.status in ("PROCESSED", "ERROR_AI") and doc.type_tags:
                to_shortcut.append(uid)
            else:
                to_full.append(uid)

        if to_shortcut:
            self.db_manager.queue_for_semantic_extraction(to_shortcut)
        if to_full:
            self.reprocess_requested.emit(to_full)

        self.status_updated.emit(
            self._parent.tr("Queued %s docs for extraction.") % len(uuids)
        )

    def run_stage_2_all_missing(self) -> None:
        """Find all documents without semantic data and queue them for extraction."""
        from gui.utils import show_selectable_message_box, show_notification

        docs = self.db_manager.get_documents_missing_semantic_data()
        if not docs:
            show_notification(
                self._parent,
                self._parent.tr("Semantic Data"),
                self._parent.tr("No empty documents found."),
            )
            return

        uuids = [d.uuid for d in docs]
        confirm = show_selectable_message_box(
            self._parent,
            self._parent.tr("Process empty Documents"),
            self._parent.tr(
                "Start semantic extraction for %s documents without details?"
            ) % len(uuids),
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        to_shortcut = [
            uid for uid in uuids
            if next((d for d in docs if d.uuid == uid), None)
            and next((d for d in docs if d.uuid == uid)).status in ("PROCESSED", "ERROR_AI")
            and next((d for d in docs if d.uuid == uid)).type_tags
        ]
        to_full = [uid for uid in uuids if uid not in to_shortcut]

        if to_shortcut:
            self.db_manager.queue_for_semantic_extraction(to_shortcut)
        if to_full:
            self.reprocess_requested.emit(to_full)

        self.status_updated.emit(
            self._parent.tr("Queued %n doc(s) for background extraction.", "", len(uuids))
        )
