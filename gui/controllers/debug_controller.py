"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/controllers/debug_controller.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Handles all debug/maintenance operations from the Debug menu.
                Communicates back to MainWindow via signals only.
------------------------------------------------------------------------------
"""

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from core.logger import get_logger
from core.integrity import IntegrityManager
from core.database import DatabaseManager
from core.pipeline import PipelineProcessor

logger = get_logger("gui.debug_controller")


class DebugController(QObject):
    """
    Owns all Debug-menu operations.  Emits signals so MainWindow can refresh
    the list widget without the controller holding widget references.

    Signal contract
    ---------------
    list_refresh_requested  → list_widget.refresh_list()
    """

    list_refresh_requested = pyqtSignal()

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

    # ── Orphan / broken vault files ───────────────────────────────────────────

    def show_orphans(self) -> None:
        mgr = IntegrityManager(self.db_manager, self.pipeline.vault)
        mgr.show_orphaned_vault_files()

    def prune_orphans(self) -> None:
        from gui.utils import show_selectable_message_box

        msg = (
            "Permanently delete ALL files in the vault that are NOT referenced "
            "by any entity? Check console for progress."
        )
        reply = show_selectable_message_box(
            self._parent,
            "Prune Vault",
            msg,
            icon=QMessageBox.Icon.Warning,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            mgr = IntegrityManager(self.db_manager, self.pipeline.vault)
            mgr.prune_orphaned_vault_files()

    def show_broken(self) -> None:
        mgr = IntegrityManager(self.db_manager, self.pipeline.vault)
        mgr.show_broken_entity_references()

    def prune_broken(self) -> None:
        from gui.utils import show_selectable_message_box

        msg = (
            "Permanently delete ALL database entries (entities) that point to "
            "missing files? Check console for progress."
        )
        reply = show_selectable_message_box(
            self._parent,
            "Prune Database",
            msg,
            icon=QMessageBox.Icon.Warning,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            mgr = IntegrityManager(self.db_manager, self.pipeline.vault)
            mgr.prune_broken_entity_references()
            self.list_refresh_requested.emit()

    def deduplicate_vault(self) -> None:
        from gui.utils import show_selectable_message_box

        msg = (
            "This will IDENTIFY duplicates by HASH and SIZE.\n\n"
            "STEP 1: Delete newer duplicate files from Vault.\n"
            "STEP 2: Remove ALL entities from the list that pointed to these files.\n\n"
            "This is DESTRUCTIVE. Continue?"
        )
        reply = show_selectable_message_box(
            self._parent,
            "Physical Deduplication",
            msg,
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            mgr = IntegrityManager(self.db_manager, self.pipeline.vault)
            mgr.deduplicate_vault()
            self.list_refresh_requested.emit()

    def prune_orphan_workflows(self) -> None:
        """Remove workflow entries whose rule_id no longer exists in the registry."""
        from gui.utils import show_selectable_message_box
        from core.workflow import WorkflowRuleRegistry

        if not self.db_manager:
            return

        registry = WorkflowRuleRegistry()
        known_ids = set(registry.rules.keys())

        all_docs = self.db_manager.get_all_entities_view()
        affected: list[tuple] = []

        for doc in all_docs:
            sd = getattr(doc, "semantic_data", None)
            if not sd or not hasattr(sd, "workflows") or not sd.workflows:
                continue
            orphaned = [rid for rid in sd.workflows if rid not in known_ids]
            if orphaned:
                affected.append((doc.uuid, orphaned))

        if not affected:
            show_selectable_message_box(
                self._parent,
                self._parent.tr("Orphaned Workflow References"),
                self._parent.tr(
                    "No orphaned workflow references found. "
                    "All rule IDs in all documents match a known rule."
                ),
                icon=QMessageBox.Icon.Information,
            )
            return

        total_entries = sum(len(ids) for _, ids in affected)
        all_orphaned_ids = sorted({rid for _, ids in affected for rid in ids})
        detail = "\n".join(f"  • {rid}" for rid in all_orphaned_ids)
        msg = (
            f"Found {total_entries} orphaned workflow reference(s) in "
            f"{len(affected)} document(s).\n\n"
            f"Unknown rule IDs:\n{detail}\n\n"
            "Remove these entries from all affected documents?"
        )
        reply = show_selectable_message_box(
            self._parent,
            self._parent.tr("Prune Orphaned Workflow References"),
            msg,
            icon=QMessageBox.Icon.Warning,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        pruned_docs = 0
        errors: list[str] = []
        for uuid, orphaned_ids in affected:
            try:
                doc = self.db_manager.get_document_by_uuid(uuid)
                sd = getattr(doc, "semantic_data", None)
                if sd and hasattr(sd, "workflows"):
                    for rid in orphaned_ids:
                        sd.workflows.pop(rid, None)
                    self.db_manager.update_document_metadata(uuid, {"semantic_data": sd})
                    pruned_docs += 1
            except Exception as e:
                logger.error(f"Failed to prune orphaned workflows from {uuid}: {e}")
                errors.append(uuid)

        summary = self._parent.tr(
            "Removed orphaned workflow references from %n document(s).", "", pruned_docs
        )
        if errors:
            summary += f"\n\nFailed for {len(errors)} document(s) — see log for details."
        show_selectable_message_box(
            self._parent,
            self._parent.tr("Done"),
            summary,
            icon=QMessageBox.Icon.Information,
        )
        self.list_refresh_requested.emit()
