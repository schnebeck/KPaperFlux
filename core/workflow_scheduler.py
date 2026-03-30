"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/workflow_scheduler.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Background scheduler that evaluates auto-transitions for all
                documents with active workflows. Fires on a configurable interval
                (default 15 minutes) and applies any auto-transitions whose
                conditions are now satisfied.
------------------------------------------------------------------------------
"""

from datetime import datetime
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.logger import get_logger
from core.workflow import (
    WorkflowEngine,
    WorkflowRuleRegistry,
    build_workflow_data,
)

logger = get_logger("core.workflow_scheduler")


class WorkflowScheduler(QObject):
    """Background scheduler that evaluates auto-transitions for all active workflow documents.

    The scheduler fires on a configurable interval (default 15 minutes) and
    applies any auto-transitions whose conditions are satisfied.  One bad
    document never aborts the run — all per-document errors are caught and
    logged at WARNING level.

    Signals:
        transitions_applied(int): emitted after each run with the count of
            transitions that were applied (may be 0).
        run_completed(): emitted after each scheduled run, even when no
            transitions were applied.
    """

    transitions_applied = pyqtSignal(int)
    run_completed = pyqtSignal()

    def __init__(
        self,
        db_manager: Any,
        interval_minutes: int = 15,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.db_manager = db_manager
        self._interval_ms = interval_minutes * 60 * 1000

        self._timer = QTimer(self)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._run)

    # ── Public API ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the recurring timer and schedule a first run after 5 seconds."""
        self._timer.start(self._interval_ms)
        QTimer.singleShot(5000, self._run)

    def stop(self) -> None:
        """Stop the recurring timer."""
        self._timer.stop()

    # ── Core evaluation loop ───────────────────────────────────────────────

    def _run(self) -> None:
        """Evaluate all documents with active workflows and apply auto-transitions."""
        count = 0
        registry = WorkflowRuleRegistry()

        try:
            docs = self.db_manager.search_documents_advanced(
                {"field": "semantic:workflows", "op": "is_not_empty", "value": None}
            )
        except Exception as exc:
            logger.warning(f"[WorkflowScheduler] Failed to query documents: {exc}")
            self.transitions_applied.emit(0)
            self.run_completed.emit()
            return

        for doc in docs:
            try:
                count += self._process_document(doc, registry)
            except Exception as exc:
                logger.warning(
                    f"[WorkflowScheduler] Error processing document {getattr(doc, 'uuid', '?')}: {exc}"
                )

        logger.debug(f"[WorkflowScheduler] Run complete — {count} transition(s) applied.")
        self.transitions_applied.emit(count)
        self.run_completed.emit()

    def _process_document(self, doc: Any, registry: WorkflowRuleRegistry) -> int:
        """Evaluate and apply auto-transitions for a single document.

        Returns the number of transitions applied for this document.
        """
        sd = getattr(doc, "semantic_data", None)
        if sd is None or not hasattr(sd, "workflows"):
            return 0

        applied = 0
        for rule_id, wf_info in list(sd.workflows.items()):
            rule = registry.get_rule(rule_id)
            if rule is None:
                logger.debug(
                    f"[WorkflowScheduler] Rule '{rule_id}' not found in registry — skipping."
                )
                continue

            current_step = wf_info.current_step
            days_in_state = self._compute_days_in_state(wf_info.current_step_entered_at)
            doc_data = build_workflow_data(doc, days_in_state)

            engine = WorkflowEngine(rule)

            # Find the first applicable auto-transition (action + target)
            action, target = self._find_auto_transition(engine, current_step, doc_data)
            if target is None:
                continue

            wf_info.apply_transition(action, target, user="SCHEDULER")
            try:
                self.db_manager.update_document_metadata(
                    doc.uuid, {"semantic_data": sd}
                )
            except Exception as exc:
                logger.warning(
                    f"[WorkflowScheduler] Failed to save transition for "
                    f"doc {doc.uuid} rule {rule_id}: {exc}"
                )
                continue

            logger.info(
                f"[WorkflowScheduler] doc={doc.uuid} rule={rule_id} "
                f"'{current_step}' --[{action}]--> '{target}'"
            )
            applied += 1

        return applied

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_days_in_state(entered_at: Any) -> int:
        """Return whole days since *entered_at* ISO timestamp, or 0."""
        if not entered_at:
            return 0
        try:
            entered = datetime.fromisoformat(str(entered_at))
            delta = datetime.now() - entered
            return max(0, delta.days)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _find_auto_transition(
        engine: WorkflowEngine, current_state: str, data: dict
    ) -> tuple[str, Any]:
        """Return (action, target) for the first applicable auto-transition, or ('', None)."""
        state = engine.rule.states.get(current_state)
        if not state:
            return ("", None)
        for trans in state.transitions:
            if trans.auto and engine.evaluate_transition(trans, data):
                return (trans.action, trans.target)
        return ("", None)
