"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/controllers/processing_controller.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Handles document reprocessing and stamping operations.
                Communicates back to the caller exclusively via Qt signals
                to avoid circular widget references.
------------------------------------------------------------------------------
"""

import os
import shutil
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QMessageBox, QProgressDialog

from core.logger import get_logger
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager

logger = get_logger("gui.processing_controller")


class ProcessingController(QObject):
    """
    Owns all document reprocessing and stamping operations.

    Signal contract
    ---------------
    list_refresh_requested      → list_widget.refresh_list()
    stats_refresh_requested     → cockpit_widget.refresh_stats()
    editor_reload_requested([]) → reload editor for these UUIDs if visible
    viewer_clear_requested      → pdf_viewer.clear()
    list_select_requested(str)  → list_widget.select_document(uuid)
    document_reselect_requested(str) → re-emit list_widget.document_selected([uuid])
    """

    list_refresh_requested = pyqtSignal()
    stats_refresh_requested = pyqtSignal()
    editor_reload_requested = pyqtSignal(list)
    viewer_clear_requested = pyqtSignal()
    list_select_requested = pyqtSignal(str)
    document_reselect_requested = pyqtSignal(str)

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
        self.reprocess_worker = None
        self._reprocess_errors: List[str] = []

    # ── Reprocess ─────────────────────────────────────────────────────────────

    def reprocess_documents(self, uuids: List[str], force_ocr: bool = False) -> None:
        """Re-run the pipeline for a list of documents."""
        from gui.workers import ReprocessWorker

        if not self.pipeline:
            return

        source_uuids = set()
        for u in uuids:
            self.db_manager.reset_document_for_reanalysis(u)
            source_uuids.add(u)

        start_uuids = list(source_uuids)
        if not start_uuids:
            return

        count = len(start_uuids)
        label = (
            self._parent.tr("Reprocessing...")
            if not force_ocr
            else self._parent.tr("Running OCR...")
        )
        progress = QProgressDialog(label, self._parent.tr("Cancel"), 0, count, self._parent)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.forceShow()
        progress.setValue(0)

        # If the currently-viewed document is in the set, clear the viewer first
        viewer = getattr(self._parent, "pdf_viewer", None)
        uuid_to_restore = None
        if viewer and viewer.current_uuid in start_uuids:
            uuid_to_restore = viewer.current_uuid
            self.viewer_clear_requested.emit()

        self.reprocess_worker = ReprocessWorker(self.pipeline, start_uuids, force_ocr=force_ocr)
        self._reprocess_errors = []

        def _on_progress(i: int, uid: str) -> None:
            progress.setLabelText(
                self._parent.tr("Reprocessing %s of %s...") % (i + 1, count)
            )
            progress.setValue(i)

        self.reprocess_worker.progress.connect(_on_progress)
        self.reprocess_worker.error.connect(
            lambda uid, msg: self._reprocess_errors.append(f"{uid}: {msg}")
        )
        self.reprocess_worker.finished.connect(
            lambda ok, total, processed: self._on_reprocess_finished(
                ok, total, processed, uuids, progress, uuid_to_restore
            )
        )
        progress.canceled.connect(self.reprocess_worker.cancel)
        self.reprocess_worker.start()

    def _on_reprocess_finished(
        self,
        success_count: int,
        total: int,
        processed_uuids: List[str],
        original_uuids: List[str],
        progress_dialog: QProgressDialog,
        uuid_to_restore: Optional[str],
    ) -> None:
        from gui.utils import show_notification

        progress_dialog.close()

        if self.reprocess_worker:
            self.reprocess_worker.wait()
            self.reprocess_worker.deleteLater()
            self.reprocess_worker = None

        if self.pipeline:
            self.pipeline.reset_cancellation()

        # Ask MainWindow to reload the editor if any edited doc was reprocessed
        self.editor_reload_requested.emit(processed_uuids)
        self.list_refresh_requested.emit()

        if uuid_to_restore and uuid_to_restore in processed_uuids:
            self.list_select_requested.emit(uuid_to_restore)

        self.stats_refresh_requested.emit()

        if self._reprocess_errors:
            error_count = len(self._reprocess_errors)
            show_notification(
                self._parent,
                self._parent.tr("Processing Error"),
                self._parent.tr(
                    "%n error(s) occurred during reprocessing. Check logs.", "", error_count
                ),
                duration=5000,
            )
            self._reprocess_errors = []

        show_notification(
            self._parent,
            self._parent.tr("Reprocessed"),
            f"Reprocessed {success_count}/{total} documents.\nProcessing will continue in background.",
        )

    # ── Stamp ─────────────────────────────────────────────────────────────────

    def stamp_documents(self, uuid_or_list) -> None:
        """Apply or remove a visual stamp on one or more documents."""
        from gui.stamper_dialog import StamperDialog
        from core.stamper import DocumentStamper
        from gui.utils import show_selectable_message_box, show_notification

        if not self.pipeline:
            return

        uuids = uuid_or_list if isinstance(uuid_or_list, list) else [uuid_or_list]
        if not uuids:
            return

        target_uuid = uuids[0]
        src_path = self.pipeline.vault.get_file_path(target_uuid)

        if not src_path or not os.path.exists(src_path) or src_path == "/dev/null":
            if self.db_manager:
                mapping = self.db_manager.get_source_mapping_from_entity(target_uuid)
                if mapping:
                    phys_uuid = mapping[0].get("file_uuid")
                    if phys_uuid:
                        src_path = self.pipeline.vault.get_file_path(phys_uuid)

        if not src_path or not os.path.exists(src_path):
            show_selectable_message_box(
                self._parent,
                self._parent.tr("Error"),
                self._parent.tr("Could not locate physical file for UUID: %s") % target_uuid,
                icon=QMessageBox.Icon.Warning,
            )
            return

        stamper = DocumentStamper()
        dialog = StamperDialog(self._parent)
        dialog.populate_stamps(stamper.get_stamps(src_path))

        if not dialog.exec():
            return

        action, text, pos, color, rotation, remove_id = dialog.get_data()
        try:
            successful_count = 0
            if action == "remove":
                if len(uuids) > 1:
                    show_selectable_message_box(
                        self._parent,
                        self._parent.tr("Batch Operation"),
                        self._parent.tr("Removing stamps is only supported for single documents."),
                        icon=QMessageBox.Icon.Warning,
                    )
                    uuids = [target_uuid]
                if stamper.remove_stamp(src_path, stamp_id=remove_id):
                    successful_count = 1
            else:
                for uid in uuids:
                    fpath = self.pipeline.vault.get_file_path(uid)
                    if not fpath or not os.path.exists(fpath) or fpath == "/dev/null":
                        if self.db_manager:
                            mapping = self.db_manager.get_source_mapping_from_entity(uid)
                            if mapping:
                                phys_uuid = mapping[0].get("file_uuid")
                                if phys_uuid:
                                    fpath = self.pipeline.vault.get_file_path(phys_uuid)
                    if not fpath or not os.path.exists(fpath):
                        logger.info(f"[Stamper] Failed to resolve path for {uid}")
                        continue
                    base, ext = os.path.splitext(fpath)
                    tmp_path = f"{base}_stamped{ext}"
                    stamper.apply_stamp(fpath, tmp_path, text, position=pos, color=color, rotation=rotation)
                    shutil.move(tmp_path, fpath)
                    successful_count += 1

            msg = (
                self._parent.tr("Stamp removed.")
                if action == "remove"
                else self._parent.tr("Stamp applied to %n document(s).", "", successful_count)
            )
            show_notification(self._parent, self._parent.tr("Success"), msg)
            self.document_reselect_requested.emit(target_uuid)

        except Exception as e:
            show_selectable_message_box(
                self._parent,
                self._parent.tr("Error"),
                self._parent.tr("Stamping operation failed: %s") % e,
                icon=QMessageBox.Icon.Critical,
            )
