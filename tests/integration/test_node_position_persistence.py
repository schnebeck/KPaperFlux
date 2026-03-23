"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/integration/test_node_position_persistence.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Integration / smoke tests for node-position persistence in the
                visual workflow graph editor.

                Covers the full round-trip:
                  drag node  →  rule.node_positions updated
                              →  model_dump() serialises positions
                              →  WorkflowRule(**json) restores them
                              →  _compute_layout() uses stored positions
                              →  new graph widget places nodes at saved coords
------------------------------------------------------------------------------
"""
import json
import pytest
from PyQt6.QtCore import QPointF

from core.workflow import WorkflowRule, WorkflowState, WorkflowTransition
from gui.widgets.workflow_graph import WorkflowGraphWidget, _compute_layout


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def two_state_rule() -> WorkflowRule:
    return WorkflowRule(
        id="persist_test",
        name="Persist Test",
        states={
            "NEW": WorkflowState(label="New", transitions=[
                WorkflowTransition(action="finish", target="DONE"),
            ]),
            "DONE": WorkflowState(label="Done", final=True),
        },
        triggers={"type_tags": ["TEST"]},
    )


# ── Unit: _on_node_moved writes into rule.node_positions ─────────────────────

def test_node_move_updates_rule_positions(qtbot, two_state_rule):
    widget = WorkflowGraphWidget(mode="edit")
    qtbot.addWidget(widget)
    widget.load(two_state_rule)

    widget._on_node_moved("NEW", QPointF(123.0, 456.0))

    assert "NEW" in widget._rule.node_positions
    assert widget._rule.node_positions["NEW"] == pytest.approx([123.0, 456.0], abs=0.1)


def test_node_move_emits_rule_changed(qtbot, two_state_rule):
    widget = WorkflowGraphWidget(mode="edit")
    qtbot.addWidget(widget)
    widget.load(two_state_rule)

    signals = []
    widget.rule_changed.connect(lambda: signals.append(True))
    widget._on_node_moved("NEW", QPointF(10.0, 20.0))

    assert len(signals) == 1


# ── Unit: _compute_layout prefers stored positions ────────────────────────────

def test_compute_layout_uses_stored_position():
    rule = WorkflowRule(
        id="layout_test",
        name="Layout Test",
        states={
            "NEW": WorkflowState(label="New", transitions=[
                WorkflowTransition(action="go", target="DONE"),
            ]),
            "DONE": WorkflowState(label="Done", final=True),
        },
        triggers={},
        node_positions={"NEW": [999.0, 888.0]},
    )
    pos = _compute_layout(rule)
    assert pos["NEW"].x() == pytest.approx(999.0, abs=0.1)
    assert pos["NEW"].y() == pytest.approx(888.0, abs=0.1)


def test_compute_layout_falls_back_to_bfs_for_missing_state():
    """States not in node_positions still get auto-positioned."""
    rule = WorkflowRule(
        id="fallback_test",
        name="Fallback Test",
        states={
            "NEW": WorkflowState(label="New", transitions=[
                WorkflowTransition(action="go", target="DONE"),
            ]),
            "DONE": WorkflowState(label="Done", final=True),
        },
        triggers={},
        node_positions={"NEW": [500.0, 0.0]},
    )
    pos = _compute_layout(rule)
    # NEW is stored; DONE must still be placed via BFS (not missing)
    assert "DONE" in pos
    # DONE should NOT be at the same position as NEW
    assert pos["DONE"] != pos["NEW"]
    # DONE's x comes from BFS layer 1, independent of NEW's manual position
    from gui.widgets.workflow_graph import NODE_W, H_GAP
    expected_done_x = 1 * (NODE_W + H_GAP) + NODE_W / 2
    assert pos["DONE"].x() == pytest.approx(expected_done_x, abs=1)


# ── Integration: full JSON round-trip ─────────────────────────────────────────

def test_positions_survive_model_dump_and_reload(qtbot, two_state_rule):
    """Drag a node, serialise to JSON, deserialise, check position is restored."""
    widget = WorkflowGraphWidget(mode="edit")
    qtbot.addWidget(widget)
    widget.load(two_state_rule)

    # Simulate dragging "DONE" to an unusual position
    widget._on_node_moved("DONE", QPointF(777.0, -333.0))

    # Serialise (as _save_rule does)
    rule_out = widget.get_rule()
    payload = json.dumps(rule_out.model_dump())

    # Deserialise (as load_from_directory does)
    data = json.loads(payload)
    rule_in = WorkflowRule(**data)

    assert "DONE" in rule_in.node_positions
    assert rule_in.node_positions["DONE"] == pytest.approx([777.0, -333.0], abs=0.1)


def test_restored_rule_positions_used_in_new_widget(qtbot, two_state_rule):
    """After round-trip through JSON, a fresh graph widget places nodes correctly."""
    # Step 1: set a custom position and serialise
    w1 = WorkflowGraphWidget(mode="edit")
    qtbot.addWidget(w1)
    w1.load(two_state_rule)
    w1._on_node_moved("NEW", QPointF(42.0, 84.0))

    payload = json.dumps(w1.get_rule().model_dump())

    # Step 2: restore and load into a brand-new widget
    rule_restored = WorkflowRule(**json.loads(payload))

    w2 = WorkflowGraphWidget(mode="edit")
    qtbot.addWidget(w2)
    w2.load(rule_restored)

    # The node in the scene should sit at the stored position
    node = w2._nodes.get("NEW")
    assert node is not None
    assert node.pos().x() == pytest.approx(42.0, abs=0.1)
    assert node.pos().y() == pytest.approx(84.0, abs=0.1)


def test_node_positions_empty_by_default():
    """A newly created rule has no stored positions."""
    rule = WorkflowRule(id="fresh", name="Fresh", states={}, triggers={})
    assert rule.node_positions == {}


def test_old_json_without_positions_loads_cleanly():
    """JSON saved before node_positions was added must still load without error."""
    legacy_json = json.dumps({
        "id": "legacy",
        "name": "Legacy Rule",
        "states": {
            "NEW": {"label": "New", "final": False, "transitions": []},
        },
        "triggers": {},
        # node_positions deliberately absent
    })
    rule = WorkflowRule(**json.loads(legacy_json))
    assert rule.node_positions == {}
    # layout must still work
    pos = _compute_layout(rule)
    assert "NEW" in pos
