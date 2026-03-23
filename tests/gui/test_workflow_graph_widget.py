"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/gui/test_workflow_graph_widget.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    GUI tests for WorkflowGraphWidget (run/edit mode) and
                WorkflowGraphsPanel in gui/widgets/workflow_graph.py.
------------------------------------------------------------------------------
"""
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt

from core.models.semantic import WorkflowInfo, WorkflowLog
from core.workflow import WorkflowRule, WorkflowState, WorkflowTransition
from gui.widgets.workflow_graph import (
    WorkflowGraphWidget,
    WorkflowGraphsPanel,
    StateNode,
    TransitionEdge,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def simple_rule() -> WorkflowRule:
    return WorkflowRule(
        id="test_rule",
        name="Test Rule",
        states={
            "NEW": WorkflowState(label="New", transitions=[
                WorkflowTransition(action="verify", target="DONE"),
            ]),
            "DONE": WorkflowState(label="Done", final=True),
        },
        triggers={"type_tags": ["INVOICE"]},
    )


@pytest.fixture()
def workflow_info() -> WorkflowInfo:
    return WorkflowInfo(rule_id="test_rule", current_step="NEW")


# ── Run-mode tests ────────────────────────────────────────────────────────────

def test_run_mode_loads_without_error(qtbot, simple_rule, workflow_info):
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    widget.load(simple_rule, workflow_info, {})
    widget.show()
    qtbot.waitExposed(widget)


def test_run_mode_creates_nodes_for_all_states(qtbot, simple_rule, workflow_info):
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    widget.load(simple_rule, workflow_info, {})

    nodes = [i for i in widget._scene.items() if isinstance(i, StateNode)]
    node_ids = {n.state_id for n in nodes}
    assert node_ids == {"NEW", "DONE"}


def test_run_mode_current_state_marked(qtbot, simple_rule, workflow_info):
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    workflow_info.current_step = "NEW"
    widget.load(simple_rule, workflow_info, {})

    current_nodes = [
        n for n in widget._scene.items()
        if isinstance(n, StateNode) and n.is_current
    ]
    assert len(current_nodes) == 1
    assert current_nodes[0].state_id == "NEW"


def test_run_mode_creates_transition_edges(qtbot, simple_rule, workflow_info):
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    widget.load(simple_rule, workflow_info, {})

    edges = [i for i in widget._scene.items() if isinstance(i, TransitionEdge)]
    assert len(edges) == 1
    assert edges[0].transition.action == "verify"


def test_run_mode_transition_triggers_signal(qtbot, simple_rule, workflow_info):
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    widget.load(simple_rule, workflow_info, {})

    emitted = []
    widget.transition_triggered.connect(lambda *args: emitted.append(args))

    # Simulate clicking an available edge
    edges = [i for i in widget._scene.items() if isinstance(i, TransitionEdge)]
    assert edges, "No edges found"
    edge = edges[0]
    assert edge._click_cb is not None
    edge._click_cb(edge)

    assert len(emitted) == 1
    rule_id, action, target, is_auto = emitted[0]
    assert rule_id == "test_rule"
    assert action == "verify"
    assert target == "DONE"
    assert is_auto is False


def test_run_mode_reload_clears_previous_scene(qtbot, simple_rule, workflow_info):
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    widget.load(simple_rule, workflow_info, {})
    first_node_count = len([i for i in widget._scene.items() if isinstance(i, StateNode)])

    widget.load(simple_rule, workflow_info, {})
    second_node_count = len([i for i in widget._scene.items() if isinstance(i, StateNode)])
    assert first_node_count == second_node_count == 2


def test_run_mode_visited_state_detection(qtbot, simple_rule):
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)

    wf = WorkflowInfo(rule_id="test_rule", current_step="DONE")
    # _extract_visited() parses the action string for "(SRC -> TGT)" patterns
    wf.history = [WorkflowLog(action="verify (NEW -> DONE)", user="USER")]
    widget.load(simple_rule, wf, {})

    visited = widget._extract_visited(wf)
    assert "NEW" in visited
    assert "DONE" in visited


# ── Edit-mode tests ───────────────────────────────────────────────────────────

def test_edit_mode_loads_without_error(qtbot, simple_rule):
    widget = WorkflowGraphWidget(mode="edit")
    qtbot.addWidget(widget)
    widget.load(simple_rule)
    widget.show()
    qtbot.waitExposed(widget)


def test_edit_mode_nodes_are_movable(qtbot, simple_rule):
    widget = WorkflowGraphWidget(mode="edit")
    qtbot.addWidget(widget)
    widget.load(simple_rule)

    nodes = [i for i in widget._scene.items() if isinstance(i, StateNode)]
    for node in nodes:
        assert node.flags() & node.GraphicsItemFlag.ItemIsMovable


def test_edit_mode_get_rule_returns_rule(qtbot, simple_rule):
    widget = WorkflowGraphWidget(mode="edit")
    qtbot.addWidget(widget)
    widget.load(simple_rule)

    rule = widget.get_rule()
    assert rule is not None
    assert "NEW" in rule.states
    assert "DONE" in rule.states


def test_edit_mode_add_state_emits_rule_changed(qtbot, simple_rule):
    widget = WorkflowGraphWidget(mode="edit")
    qtbot.addWidget(widget)
    widget.load(simple_rule)

    changed_signals = []
    widget.rule_changed.connect(lambda: changed_signals.append(True))

    # _cmd_add_state() uses QInputDialog.getText; mock both calls
    with patch("gui.widgets.workflow_graph.QInputDialog.getText",
               side_effect=[("PENDING", True), ("Pending", True)]):
        widget._cmd_add_state()

    assert len(changed_signals) >= 1
    assert "PENDING" in widget._rule.states


def test_edit_mode_detail_panel_present(qtbot, simple_rule):
    widget = WorkflowGraphWidget(mode="edit")
    qtbot.addWidget(widget)
    widget.load(simple_rule)
    # Detail frame should exist
    assert widget._detail is not None


def test_edit_mode_get_rule_preserves_states(qtbot, simple_rule):
    """get_rule() must return the same state structure that was loaded."""
    widget = WorkflowGraphWidget(mode="edit")
    qtbot.addWidget(widget)
    widget.load(simple_rule)

    rule = widget.get_rule()
    assert set(rule.states.keys()) == {"NEW", "DONE"}
    assert rule.states["DONE"].final is True


# ── WorkflowGraphsPanel tests ─────────────────────────────────────────────────

def test_panel_shows_one_graph_per_workflow(qtbot, simple_rule):
    panel = WorkflowGraphsPanel()
    qtbot.addWidget(panel)

    registry = MagicMock()
    registry.get_rule.return_value = simple_rule

    workflows = {
        "test_rule": WorkflowInfo(rule_id="test_rule", current_step="NEW"),
        "other_rule": WorkflowInfo(rule_id="other_rule", current_step="NEW"),
    }
    registry.get_rule.side_effect = lambda rid: simple_rule if rid in workflows else None

    panel.update_workflows(workflows, registry, {})
    assert len(panel._graphs) == 2


def test_panel_removes_stale_graphs(qtbot, simple_rule):
    panel = WorkflowGraphsPanel()
    qtbot.addWidget(panel)

    registry = MagicMock()
    registry.get_rule.return_value = simple_rule

    wf1 = {"rule_a": WorkflowInfo(rule_id="rule_a", current_step="NEW")}
    panel.update_workflows(wf1, registry, {})
    assert len(panel._graphs) == 1

    panel.update_workflows({}, registry, {})
    assert len(panel._graphs) == 0


def test_panel_transition_signal_forwarded(qtbot, simple_rule):
    panel = WorkflowGraphsPanel()
    qtbot.addWidget(panel)

    registry = MagicMock()
    registry.get_rule.return_value = simple_rule

    workflows = {"test_rule": WorkflowInfo(rule_id="test_rule", current_step="NEW")}
    panel.update_workflows(workflows, registry, {})

    emitted = []
    panel.transition_triggered.connect(lambda *args: emitted.append(args))

    # Simulate a signal from the inner graph
    panel._graphs["test_rule"].transition_triggered.emit("test_rule", "verify", "DONE", False)
    assert len(emitted) == 1
    assert emitted[0] == ("test_rule", "verify", "DONE", False)


def test_panel_clear_removes_all_graphs(qtbot, simple_rule):
    panel = WorkflowGraphsPanel()
    qtbot.addWidget(panel)

    registry = MagicMock()
    registry.get_rule.return_value = simple_rule

    workflows = {"test_rule": WorkflowInfo(rule_id="test_rule", current_step="NEW")}
    panel.update_workflows(workflows, registry, {})
    assert len(panel._graphs) == 1

    panel.clear()
    assert len(panel._graphs) == 0
