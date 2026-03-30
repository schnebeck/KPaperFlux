"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/controllers/document_action_controller.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Thin facade that aggregates ImportController, ProcessingController
                and LifecycleController.  All signals are re-exported so
                MainWindow callers do not need any changes.  Private helpers
                like _on_import_finished are delegated to maintain backwards
                compatibility with existing unit tests.
------------------------------------------------------------------------------
"""

from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from core.logger import get_logger
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager
from gui.controllers.import_controller import ImportController
from gui.controllers.processing_controller import ProcessingController
from gui.controllers.lifecycle_controller import LifecycleController

logger = get_logger("gui.document_action_controller")


class DocumentActionController(QObject):
    """
    Facade that delegates all document-modifying operations to three focused
    sub-controllers.  Exposes the same signal interface that MainWindow wires
    to so callers require zero changes.

    Signal contract (identical to the original monolithic controller)
    ---------------
    list_refresh_requested      -> list_widget.refresh_list()
    stats_refresh_requested     -> cockpit_widget.refresh_stats()
    status_updated(str)         -> main_status_label.setText()
    editor_reload_requested([]) -> reload editor for these UUIDs if visible
    editor_clear_requested      -> editor_widget.clear()
    viewer_clear_requested      -> pdf_viewer.clear()
    list_select_requested(str)  -> list_widget.select_document(uuid)
    document_reselect_requested(str) -> re-emit list_widget.document_selected([uuid])
    splitter_dialog_requested(str)   -> open_splitter_dialog_slot(uuid)
    """

    # Re-declared so MainWindow can connect to self.doc_controller.<signal>
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
        self._parent = parent
        self.pipeline = pipeline
        self.db_manager = db_manager

        # Sub-controllers — each owned by this facade (QObject parent = self).
        # The widget-parent reference (_parent) is set to `parent` (the window
        # widget) so dialog boxes appear on the correct window.
        self.importer = ImportController(self, pipeline, db_manager)
        self.importer._parent = parent
        self.processor = ProcessingController(self, pipeline, db_manager)
        self.processor._parent = parent
        self.lifecycle = LifecycleController(self, pipeline, db_manager)
        self.lifecycle._parent = parent

        # Wire sub-controller signals to facade signals

        # ImportController
        self.importer.list_refresh_requested.connect(self.list_refresh_requested)
        self.importer.stats_refresh_requested.connect(self.stats_refresh_requested)
        self.importer.status_updated.connect(self.status_updated)
        self.importer.splitter_dialog_requested.connect(self.splitter_dialog_requested)
        # Stage-2 helpers in ImportController delegate reprocess to ProcessingController
        self.importer.reprocess_requested.connect(self.processor.reprocess_documents)

        # ProcessingController
        self.processor.list_refresh_requested.connect(self.list_refresh_requested)
        self.processor.stats_refresh_requested.connect(self.stats_refresh_requested)
        self.processor.editor_reload_requested.connect(self.editor_reload_requested)
        self.processor.viewer_clear_requested.connect(self.viewer_clear_requested)
        self.processor.list_select_requested.connect(self.list_select_requested)
        self.processor.document_reselect_requested.connect(self.document_reselect_requested)

        # LifecycleController
        self.lifecycle.list_refresh_requested.connect(self.list_refresh_requested)
        self.lifecycle.stats_refresh_requested.connect(self.stats_refresh_requested)
        self.lifecycle.editor_clear_requested.connect(self.editor_clear_requested)
        self.lifecycle.viewer_clear_requested.connect(self.viewer_clear_requested)

    # _parent synchronisation
    # Tests may reassign ctrl._parent after construction; propagate to all
    # sub-controllers so their dialog calls use the correct widget parent.

    @property  # type: ignore[override]
    def _parent(self):
        return self.__parent

    @_parent.setter
    def _parent(self, value) -> None:
        self.__parent = value
        if hasattr(self, "importer"):
            self.importer._parent = value
        if hasattr(self, "processor"):
            self.processor._parent = value
        if hasattr(self, "lifecycle"):
            self.lifecycle._parent = value

    # Backwards-compatible private helpers (used by existing unit tests)

    def _on_import_finished(
        self,
        success_count: int,
        total: int,
        imported_uuids: List[str],
        error_msg: Optional[str],
        progress_dialog: object,
        skip_splitter: bool,
    ) -> None:
        """Delegation shim so existing tests calling this method still pass."""
        self.importer._on_import_finished(
            success_count, total, imported_uuids, error_msg, progress_dialog, skip_splitter
        )

    def _on_reprocess_finished(
        self,
        success_count: int,
        total: int,
        processed_uuids: List[str],
        original_uuids: List[str],
        progress_dialog: object,
        uuid_to_restore: Optional[str],
    ) -> None:
        """Delegation shim so existing tests calling this method still pass."""
        self.processor._on_reprocess_finished(
            success_count, total, processed_uuids, original_uuids, progress_dialog, uuid_to_restore
        )

    # Public API (delegates to sub-controllers)

    def set_trash_mode(self, enabled: bool) -> None:
        """Called by MainWindow whenever trash-mode toggles."""
        self.lifecycle.set_trash_mode(enabled)

    # Import group
    def start_import(self, files: List[str], move_source: bool = False) -> None:
        self.importer.start_import(files, move_source=move_source)

    def run_stage_2(self, uuids: List[str]) -> None:
        self.importer.run_stage_2(uuids)

    def run_stage_2_all_missing(self) -> None:
        self.importer.run_stage_2_all_missing()

    # Processing group
    def reprocess_documents(self, uuids: List[str], force_ocr: bool = False) -> None:
        self.processor.reprocess_documents(uuids, force_ocr=force_ocr)

    def stamp_documents(self, uuid_or_list) -> None:
        self.processor.stamp_documents(uuid_or_list)

    # Lifecycle group
    def delete_documents(self, uuids: List[str]) -> None:
        self.lifecycle.delete_documents(uuids)

    def restore_documents(self, uuids: List[str]) -> None:
        self.lifecycle.restore_documents(uuids)

    def archive_documents(self, uuids: List[str], archive: bool = True) -> None:
        self.lifecycle.archive_documents(uuids, archive)

    def purge_documents(self, uuids: List[str]) -> None:
        self.lifecycle.purge_documents(uuids)

    # Worker references (used by MainWindow.closeEvent)

    @property
    def reprocess_worker(self):
        return self.processor.reprocess_worker

    @property
    def import_worker(self):
        return self.importer.import_worker
