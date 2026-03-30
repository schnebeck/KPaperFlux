"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_workflow_scheduler.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for WorkflowScheduler — background auto-transition
                evaluation loop.

                Tests cover:
                  - auto=True transition whose condition passes → applied
                  - auto=False transition → not applied
                  - auto=True transition whose condition fails → not applied
                  - one doc raises an exception → others still processed
                  - transitions_applied signal carries correct count
------------------------------------------------------------------------------
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, WorkflowInfo
from core.workflow import (
    WorkflowRule,
    WorkflowRuleRegistry,
    WorkflowState,
    WorkflowTransition,
    WorkflowCondition,
)
from core.workflow_scheduler import WorkflowScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(auto: bool = True, condition_passes: bool = True) -> WorkflowRule:
    """Build a minimal two-state rule with one transition.

    When *auto* is True the transition is an auto-transition.
    When *condition_passes* is False, a numeric condition is added that
    the doc_data will not satisfy.
    """
    conditions = []
    if not condition_passes:
        # DAYS_IN_STATE > 9999 — will never pass in tests
        conditions = [WorkflowCondition(field="DAYS_IN_STATE", op=">", value=9999)]

    return WorkflowRule(
        id="test_rule",
        states={
            "OPEN": WorkflowState(
                label="Open",
                transitions=[
                    WorkflowTransition(
                        action="escalate",
                        target="ESCALATED",
                        auto=auto,
                        conditions=conditions,
                    )
                ],
            ),
            "ESCALATED": WorkflowState(label="Escalated", final=True),
        },
    )


def _make_doc(rule_id: str = "test_rule", current_step: str = "OPEN") -> VirtualDocument:
    """Build a VirtualDocument with one workflow entry in *current_step*."""
    doc = VirtualDocument(uuid="doc-test-1")
    sd = SemanticExtraction()
    wf_info = WorkflowInfo(rule_id=rule_id, current_step=current_step)
    # Set entered_at to 2 days ago so DAYS_IN_STATE == 2
    wf_info.current_step_entered_at = (datetime.now() - timedelta(days=2)).isoformat()
    sd.workflows[rule_id] = wf_info
    doc.semantic_data = sd
    return doc


def _make_registry(rule: WorkflowRule) -> WorkflowRuleRegistry:
    """Populate a fresh registry singleton with *rule*."""
    reg = WorkflowRuleRegistry()
    reg.rules.clear()
    reg.rules[rule.id] = rule
    return reg


def _make_scheduler(docs: list, save_raises: bool = False) -> WorkflowScheduler:
    """Return a WorkflowScheduler backed by a mock db_manager."""
    mock_db = MagicMock()
    mock_db.search_documents_advanced.return_value = docs
    if save_raises:
        mock_db.update_document_metadata.side_effect = RuntimeError("DB down")
    return WorkflowScheduler(mock_db, interval_minutes=15)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSchedulerAppliesAutoTransition:
    """auto=True, condition passes → transition applied and document saved."""

    def test_transition_applied(self):
        rule = _make_rule(auto=True, condition_passes=True)
        _make_registry(rule)
        doc = _make_doc()
        scheduler = _make_scheduler([doc])

        scheduler._run()

        assert doc.semantic_data.workflows["test_rule"].current_step == "ESCALATED"

    def test_document_saved(self):
        rule = _make_rule(auto=True, condition_passes=True)
        _make_registry(rule)
        doc = _make_doc()
        scheduler = _make_scheduler([doc])

        scheduler._run()

        scheduler.db_manager.update_document_metadata.assert_called_once()
        call_kwargs = scheduler.db_manager.update_document_metadata.call_args
        assert call_kwargs[0][0] == doc.uuid  # first positional arg is uuid


class TestSchedulerSkipsManualTransitions:
    """auto=False → never applied by the scheduler."""

    def test_manual_transition_not_applied(self):
        rule = _make_rule(auto=False, condition_passes=True)
        _make_registry(rule)
        doc = _make_doc()
        scheduler = _make_scheduler([doc])

        scheduler._run()

        # Step must remain unchanged
        assert doc.semantic_data.workflows["test_rule"].current_step == "OPEN"
        scheduler.db_manager.update_document_metadata.assert_not_called()


class TestSchedulerSkipsBlockedCondition:
    """auto=True but condition never passes → not applied."""

    def test_blocked_condition_not_applied(self):
        rule = _make_rule(auto=True, condition_passes=False)
        _make_registry(rule)
        doc = _make_doc()
        scheduler = _make_scheduler([doc])

        scheduler._run()

        assert doc.semantic_data.workflows["test_rule"].current_step == "OPEN"
        scheduler.db_manager.update_document_metadata.assert_not_called()


class TestSchedulerHandlesDocumentErrorGracefully:
    """One document raises during processing → other documents still processed."""

    def test_error_in_one_doc_does_not_abort(self):
        rule = _make_rule(auto=True, condition_passes=True)
        _make_registry(rule)

        # First doc: broken semantic_data property raises AttributeError
        bad_doc = MagicMock(spec=VirtualDocument)
        bad_doc.uuid = "bad-doc"
        # Make accessing semantic_data raise so _process_document raises
        type(bad_doc).semantic_data = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
        )

        good_doc = _make_doc()
        good_doc.uuid = "good-doc"

        scheduler = _make_scheduler([bad_doc, good_doc])

        # Should not raise
        scheduler._run()

        # Good doc must still have been transitioned
        assert good_doc.semantic_data.workflows["test_rule"].current_step == "ESCALATED"

    def test_error_doc_does_not_prevent_save_of_good_doc(self):
        rule = _make_rule(auto=True, condition_passes=True)
        _make_registry(rule)

        bad_doc = MagicMock(spec=VirtualDocument)
        bad_doc.uuid = "bad-doc"
        type(bad_doc).semantic_data = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
        )

        good_doc = _make_doc()
        good_doc.uuid = "good-doc"

        scheduler = _make_scheduler([bad_doc, good_doc])
        scheduler._run()

        scheduler.db_manager.update_document_metadata.assert_called_once_with(
            "good-doc", {"semantic_data": good_doc.semantic_data}
        )


class TestSchedulerEmitsCount:
    """transitions_applied signal carries the correct transition count."""

    def test_signal_count_when_transitions_applied(self, qtbot):
        rule = _make_rule(auto=True, condition_passes=True)
        _make_registry(rule)
        doc = _make_doc()
        scheduler = _make_scheduler([doc])

        received = []
        scheduler.transitions_applied.connect(lambda n: received.append(n))

        scheduler._run()

        assert received == [1]

    def test_signal_count_zero_when_no_transitions(self, qtbot):
        rule = _make_rule(auto=False)
        _make_registry(rule)
        doc = _make_doc()
        scheduler = _make_scheduler([doc])

        received = []
        scheduler.transitions_applied.connect(lambda n: received.append(n))

        scheduler._run()

        assert received == [0]

    def test_run_completed_emitted(self, qtbot):
        rule = _make_rule(auto=False)
        _make_registry(rule)
        scheduler = _make_scheduler([])

        with qtbot.waitSignal(scheduler.run_completed, timeout=1000):
            scheduler._run()

    def test_multiple_docs_count_aggregated(self, qtbot):
        rule = _make_rule(auto=True, condition_passes=True)
        _make_registry(rule)

        doc1 = _make_doc()
        doc1.uuid = "doc-1"
        doc2 = _make_doc()
        doc2.uuid = "doc-2"

        scheduler = _make_scheduler([doc1, doc2])

        received = []
        scheduler.transitions_applied.connect(lambda n: received.append(n))
        scheduler._run()

        assert received == [2]


class TestComputeDaysInState:
    """Unit tests for the static helper."""

    def test_zero_when_none(self):
        assert WorkflowScheduler._compute_days_in_state(None) == 0

    def test_zero_when_empty_string(self):
        assert WorkflowScheduler._compute_days_in_state("") == 0

    def test_zero_when_invalid(self):
        assert WorkflowScheduler._compute_days_in_state("not-a-date") == 0

    def test_correct_days(self):
        three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
        assert WorkflowScheduler._compute_days_in_state(three_days_ago) == 3
