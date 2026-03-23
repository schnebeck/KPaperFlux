"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_workflow_graph_layout.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for the _compute_layout() BFS algorithm in
                gui/widgets/workflow_graph.py.
------------------------------------------------------------------------------
"""
import pytest
from PyQt6.QtCore import QPointF

from core.workflow import WorkflowRule, WorkflowState, WorkflowTransition
from gui.widgets.workflow_graph import _compute_layout, NODE_W, H_GAP


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_rule(states: dict) -> WorkflowRule:
    """Convenience factory for WorkflowRule from a plain state dict."""
    return WorkflowRule(id="test", name="Test", states=states, triggers={})


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_empty_rule_returns_empty_layout():
    rule = _make_rule({})
    assert _compute_layout(rule) == {}


def test_single_state_placed_at_origin():
    rule = _make_rule({"NEW": WorkflowState(label="Start")})
    pos = _compute_layout(rule)
    assert "NEW" in pos
    p = pos["NEW"]
    assert p.x() == pytest.approx(NODE_W / 2, abs=1)
    assert p.y() == pytest.approx(0, abs=1)


def test_linear_chain_assigns_increasing_x():
    """NEW -> VERIFIED -> DONE should place nodes in that left-to-right order."""
    rule = _make_rule({
        "NEW": WorkflowState(label="New", transitions=[WorkflowTransition(action="verify", target="VERIFIED")]),
        "VERIFIED": WorkflowState(label="Verified", transitions=[WorkflowTransition(action="approve", target="DONE")]),
        "DONE": WorkflowState(label="Done", final=True),
    })
    pos = _compute_layout(rule)
    assert pos["NEW"].x() < pos["VERIFIED"].x() < pos["DONE"].x()


def test_parallel_states_in_same_layer_differ_in_y():
    """Two states both reachable from NEW should be in the same x-layer."""
    rule = _make_rule({
        "NEW": WorkflowState(label="New", transitions=[
            WorkflowTransition(action="path_a", target="STATE_A"),
            WorkflowTransition(action="path_b", target="STATE_B"),
        ]),
        "STATE_A": WorkflowState(label="A", final=True),
        "STATE_B": WorkflowState(label="B", final=True),
    })
    pos = _compute_layout(rule)
    assert pos["STATE_A"].x() == pytest.approx(pos["STATE_B"].x(), abs=1)
    assert pos["STATE_A"].y() != pytest.approx(pos["STATE_B"].y(), abs=1)


def test_unreachable_state_gets_extra_layer():
    """An island state should be assigned a layer beyond all reachable ones."""
    rule = _make_rule({
        "NEW": WorkflowState(label="New", transitions=[WorkflowTransition(action="go", target="DONE")]),
        "DONE": WorkflowState(label="Done", final=True),
        "ORPHAN": WorkflowState(label="Orphan"),
    })
    pos = _compute_layout(rule)
    assert pos["ORPHAN"].x() > pos["DONE"].x()


def test_back_edge_does_not_change_source_layer():
    """A back-edge (DONE -> NEW) must not alter NEW's layer assignment."""
    rule = _make_rule({
        "NEW": WorkflowState(label="New", transitions=[WorkflowTransition(action="submit", target="REVIEW")]),
        "REVIEW": WorkflowState(label="Review", transitions=[
            WorkflowTransition(action="approve", target="DONE"),
            WorkflowTransition(action="reject", target="NEW"),   # back-edge
        ]),
        "DONE": WorkflowState(label="Done", final=True),
    })
    pos = _compute_layout(rule)
    # NEW must still be in layer 0 (leftmost)
    assert pos["NEW"].x() < pos["REVIEW"].x() < pos["DONE"].x()


def test_start_defaults_to_first_state_when_no_new():
    """If no 'NEW' state exists, BFS starts from the first state."""
    rule = _make_rule({
        "ALPHA": WorkflowState(label="Alpha", transitions=[WorkflowTransition(action="go", target="BETA")]),
        "BETA": WorkflowState(label="Beta", final=True),
    })
    pos = _compute_layout(rule)
    assert pos["ALPHA"].x() < pos["BETA"].x()


def test_final_states_sorted_last_in_layer():
    """Within a layer, final states appear below non-final ones."""
    rule = _make_rule({
        "NEW": WorkflowState(label="New", transitions=[
            WorkflowTransition(action="fail", target="FINAL_BAD"),
            WorkflowTransition(action="pass", target="NON_FINAL"),
        ]),
        "FINAL_BAD": WorkflowState(label="Bad", final=True),
        "NON_FINAL": WorkflowState(label="Pending"),
    })
    pos = _compute_layout(rule)
    # Final state should have a larger y (sorted last)
    assert pos["FINAL_BAD"].y() > pos["NON_FINAL"].y()


def test_layer_spacing_matches_constants():
    """Each layer should be exactly (NODE_W + H_GAP) apart horizontally."""
    rule = _make_rule({
        "NEW": WorkflowState(label="New", transitions=[WorkflowTransition(action="go", target="DONE")]),
        "DONE": WorkflowState(label="Done", final=True),
    })
    pos = _compute_layout(rule)
    expected_gap = NODE_W + H_GAP
    actual_gap = pos["DONE"].x() - pos["NEW"].x()
    assert actual_gap == pytest.approx(expected_gap, abs=1)
