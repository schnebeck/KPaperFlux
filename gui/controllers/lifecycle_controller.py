"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/controllers/lifecycle_controller.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Handles document lifecycle operations: delete, restore, archive,
                and purge.  Communicates back to the caller exclusively via Qt
                signals to avoid circular widget references.
------------------------------------------------------------------------------
"""

from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from core.logger import get_logger
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager

logger = get_logger("gui.lifecycle_controller")


class LifecycleController(QObject):
    """
    Owns all document lifecycle operations (delete, restore, archive, purge).

    Signal contract
    ---------------
    list_refresh_requested  → list_widget.refresh_list()
    stats_refresh_requested → cockpit_widget.refresh_stats()
    editor_clear_requested  → editor_widget.clear()
    viewer_clear_requested  → pdf_viewer.clear()
    """

    list_refresh_requested = pyqtSignal()
    stats_refresh_requested = pyqtSignal()
    editor_clear_requested = pyqtSignal()
    viewer_clear_requested = pyqtSignal()

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
        self._is_trash_mode: bool = False

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

    # ── Restore ───────────────────────────────────────────────────────────────

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

    # ── Archive ───────────────────────────────────────────────────────────────

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

    # ── Purge ─────────────────────────────────────────────────────────────────

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
