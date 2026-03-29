"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_workflow_history_widget.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for WorkflowHistoryWidget.
------------------------------------------------------------------------------
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QLabel, QTableWidget

from core.models.semantic import WorkflowInfo, WorkflowLog
from core.workflow import WorkflowRuleRegistry
from gui.widgets.workflow_history_widget import WorkflowHistoryWidget


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_registry(rule_id: str, display_name: str) -> WorkflowRuleRegistry:
    """Return a WorkflowRuleRegistry mock that resolves a single rule by id."""
    rule = MagicMock()
    rule.get_display_name.return_value = display_name

    registry = MagicMock(spec=WorkflowRuleRegistry)
    registry.get_rule.side_effect = lambda rid: rule if rid == rule_id else None
    return registry


def _make_log(action: str, user: str = "USER", comment: str | None = None) -> WorkflowLog:
    return WorkflowLog(
        timestamp=datetime(2024, 3, 15, 10, 30).isoformat(),
        action=action,
        user=user,
        comment=comment,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_empty_workflows_shows_placeholder(qtbot: pytest.fixture) -> None:
    """Empty workflows dict must show a centered placeholder label."""
    widget = WorkflowHistoryWidget()
    qtbot.addWidget(widget)

    widget.update_workflows({}, _make_registry("rule_a", "Rule A"))

    labels = widget.findChildren(QLabel)
    placeholder_texts = [lbl.text() for lbl in labels]
    assert any("No workflow history yet." in t for t in placeholder_texts)


def test_workflows_without_history_shows_placeholder(qtbot: pytest.fixture) -> None:
    """Workflows with empty history lists must also show the placeholder."""
    widget = WorkflowHistoryWidget()
    qtbot.addWidget(widget)

    workflows = {
        "rule_a": WorkflowInfo(rule_id="rule_a", current_step="NEW", history=[]),
    }
    widget.update_workflows(workflows, _make_registry("rule_a", "Rule A"))

    labels = widget.findChildren(QLabel)
    placeholder_texts = [lbl.text() for lbl in labels]
    assert any("No workflow history yet." in t for t in placeholder_texts)


def test_history_shows_all_log_entries(qtbot: pytest.fixture) -> None:
    """All WorkflowLog entries in history must appear as table rows."""
    widget = WorkflowHistoryWidget()
    qtbot.addWidget(widget)

    logs = [
        _make_log("TRANSITION: go (NEW -> IN_PROGRESS)"),
        _make_log("TRANSITION: done (IN_PROGRESS -> DONE)"),
        _make_log("TRANSITION: reject (DONE -> REJECTED)"),
    ]
    workflows = {
        "rule_a": WorkflowInfo(rule_id="rule_a", current_step="DONE", history=logs),
    }
    widget.update_workflows(workflows, _make_registry("rule_a", "Rule A"))

    tables = widget.findChildren(QTableWidget)
    assert len(tables) == 1
    assert tables[0].rowCount() == 3


def test_history_newest_first(qtbot: pytest.fixture) -> None:
    """Newest entries (last in history list) must appear in the first row of the table."""
    widget = WorkflowHistoryWidget()
    qtbot.addWidget(widget)

    logs = [
        _make_log("TRANSITION: go (NEW -> STEP1)"),
        _make_log("TRANSITION: done (STEP1 -> DONE)"),
    ]
    workflows = {
        "rule_a": WorkflowInfo(rule_id="rule_a", current_step="DONE", history=logs),
    }
    widget.update_workflows(workflows, _make_registry("rule_a", "Rule A"))

    tables = widget.findChildren(QTableWidget)
    assert len(tables) == 1
    table = tables[0]

    # Row 0 should be the last log entry (newest), row 1 the first (oldest)
    first_row_action = table.item(0, 1).text()
    second_row_action = table.item(1, 1).text()

    assert "STEP1 -> DONE" in first_row_action
    assert "NEW -> STEP1" in second_row_action


def test_action_strips_transition_prefix(qtbot: pytest.fixture) -> None:
    """The 'TRANSITION: ' prefix in log actions must be stripped in the table cell."""
    widget = WorkflowHistoryWidget()
    qtbot.addWidget(widget)

    logs = [_make_log("TRANSITION: verify (NEW -> VERIFIED)")]
    workflows = {
        "rule_a": WorkflowInfo(rule_id="rule_a", current_step="VERIFIED", history=logs),
    }
    widget.update_workflows(workflows, _make_registry("rule_a", "Rule A"))

    tables = widget.findChildren(QTableWidget)
    assert len(tables) == 1
    action_text = tables[0].item(0, 1).text()

    assert "TRANSITION:" not in action_text
    assert "verify (NEW -> VERIFIED)" in action_text


def test_multiple_rules_shown(qtbot: pytest.fixture) -> None:
    """Each rule with history gets its own header label and table."""
    widget = WorkflowHistoryWidget()
    qtbot.addWidget(widget)

    logs_a = [_make_log("TRANSITION: go (NEW -> DONE)")]
    logs_b = [_make_log("TRANSITION: start (INIT -> PROCESSING)")]

    workflows = {
        "rule_a": WorkflowInfo(rule_id="rule_a", current_step="DONE", history=logs_a),
        "rule_b": WorkflowInfo(rule_id="rule_b", current_step="PROCESSING", history=logs_b),
    }

    rule_a_mock = MagicMock()
    rule_a_mock.get_display_name.return_value = "Rule Alpha"
    rule_b_mock = MagicMock()
    rule_b_mock.get_display_name.return_value = "Rule Beta"

    registry = MagicMock(spec=WorkflowRuleRegistry)
    registry.get_rule.side_effect = lambda rid: {"rule_a": rule_a_mock, "rule_b": rule_b_mock}.get(rid)

    widget.update_workflows(workflows, registry)

    tables = widget.findChildren(QTableWidget)
    assert len(tables) == 2

    labels = widget.findChildren(QLabel)
    label_texts = [lbl.text() for lbl in labels]
    assert any("Rule Alpha" in t for t in label_texts)
    assert any("Rule Beta" in t for t in label_texts)
