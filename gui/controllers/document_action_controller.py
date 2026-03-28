"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/controllers/document_action_controller.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Coordinates all document-modifying user actions (delete,
                reprocess, import, stamp, stage-2, archive/restore/purge).
                Communicates back to MainWindow exclusively via Qt signals
                to avoid circular widget references.
------------------------------------------------------------------------------
"""

import os
import shutil
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QDialog, QMessageBox, QProgressDialog

from core.logger import get_logger
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager

logger = get_logger("gui.document_action_controller")


class DocumentActionController(QObject):
    """
    Owns all document-modifying operations previously scattered across
    MainWindow.  Emits fine-grained signals so the window layer can refresh
    the appropriate widgets without the controller holding widget references.

    Signal contract
    ---------------
    list_refresh_requested      → list_widget.refresh_list()
    stats_refresh_requested     → cockpit_widget.refresh_stats()
    status_updated(str)         → main_status_label.setText()
    editor_reload_requested([]) → reload editor for these UUIDs if visible
    editor_clear_requested      → editor_widget.clear()
    viewer_clear_requested      → pdf_viewer.clear()
    list_select_requested(str)  → list_widget.select_document(uuid)
    document_reselect_requested(str) → re-emit list_widget.document_selected([uuid])
    splitter_dialog_requested(str)   → open_splitter_dialog_slot(uuid)
    """

    list_refresh_requested = pyqtSignal()
    stats_refresh_requested = pyqtSignal()
    status_updated = pyqtSignal(str)
    editor_reload_requested = pyqtSignal(list)
    editor_clear_requested = pyqtSignal()
    viewer_clear_requested = pyqtSignal()
    list_select_requested = pyqtSignal(str)
    document_reselect_requested = pyqtSignal(str)
    splitter_dialog_requested = pyqtSignal(str)

    def __init__(
        self,
        parent: QObject,
        pipeline: Optional[PipelineProcessor],
        db_manager: Optional[DatabaseManager],
    ) -> None:
        super().__init__(parent)
        self._parent = parent          # widget used as dialog parent
        self.pipeline = pipeline
        self.db_manager = db_manager
        self._is_trash_mode: bool = False
        self.reprocess_worker = None
        self.import_worker = None
        self._reprocess_errors: List[str] = []

    # ── Trash-mode state (kept in sync by MainWindow) ─────────────────────────

    def set_trash_mode(self, enabled: bool) -> None:
        """Called by MainWindow whenever trash-mode toggles."""
        self._is_trash_mode = enabled

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_documents(self, uuids: List[str]) -> None:
        """
        Delete one or more documents with a confirmation dialog.
        Soft-deletes in normal mode; hard-purges in trash mode.
        """
        from gui.utils import show_selectable_message_box, show_notification

        if not isinstance(uuids, list):
            uuids = [uuids]
        if not uuids:
            return

        count = len(uuids)
        msg = (
            self._parent.tr("Are you sure you want to delete this item?")
            if count == 1
            else self._parent.tr("Are you sure you want to delete %s items?") % count
        )

        reply = show_selectable_message_box(
            self._parent,
            self._parent.tr("Confirm Delete"),
            msg,
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        if not (self.db_manager and self.pipeline):
            return

        deleted_count = 0
        for uuid in uuids:
            if self._is_trash_mode:
                if self.pipeline.delete_entity(uuid, purge=True):
                    deleted_count += 1
                continue

            if self.pipeline.delete_entity(uuid, purge=False):
                deleted_count += 1
                continue

            doc = self.db_manager.get_document_by_uuid(uuid)
            if doc:
                if self._is_trash_mode:
                    self.db_manager.purge_document(uuid)
                else:
                    self.db_manager.mark_documents_deleted([uuid])
                deleted_count += 1

        self.editor_clear_requested.emit()
        self.viewer_clear_requested.emit()
        self.list_refresh_requested.emit()
        self.stats_refresh_requested.emit()

        if count > 1:
            show_notification(
                self._parent,
                self._parent.tr("Deleted"),
                self._parent.tr("Deleted %s items.") % deleted_count,
            )

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
            self.reprocess_documents(to_full)

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
            self.reprocess_documents(to_full)

        self.status_updated.emit(
            self._parent.tr("Queued %n doc(s) for background extraction.", "", len(uuids))
        )

    # ── Archive / Restore / Purge ─────────────────────────────────────────────

    def restore_documents(self, uuids: List[str]) -> None:
        """Restore soft-deleted documents."""
        from gui.utils import show_notification

        count = sum(1 for uid in uuids if self.db_manager.restore_document(uid))
        if count > 0:
            self.list_refresh_requested.emit()
            show_notification(
                self._parent,
                self._parent.tr("Restored"),
                self._parent.tr("Restored %n document(s).", "", count),
            )

    def archive_documents(self, uuids: List[str], archive: bool = True) -> None:
        """Archive or unarchive documents."""
        from gui.utils import show_notification

        count = sum(1 for uid in uuids if self.pipeline.archive_entity(uid, archive))
        if count > 0:
            self.list_refresh_requested.emit()
            action_str = (
                self._parent.tr("Archived") if archive else self._parent.tr("Restored from Archive")
            )
            msg_str = (
                self._parent.tr("Archived %n document(s)", "", count)
                if archive
                else self._parent.tr("Restored %n document(s) from Archive", "", count)
            )
            show_notification(self._parent, action_str, msg_str)

    def purge_documents(self, uuids: List[str]) -> None:
        """Permanently delete documents (hard purge, no confirmation)."""
        from gui.utils import show_notification

        count = sum(1 for uid in uuids if self.pipeline.delete_entity(uid))
        if count > 0:
            self.list_refresh_requested.emit()
            show_notification(
                self._parent,
                self._parent.tr("Deleted"),
                self._parent.tr("Permanently deleted %n document(s).", "", count),
            )
