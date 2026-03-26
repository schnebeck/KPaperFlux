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
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtWidgets import QGraphicsView

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
def rule_with_required_fields() -> WorkflowRule:
    """Rule where the only transition has required_fields not met by empty doc_data."""
    return WorkflowRule(
        id="test_rule",
        name="Test Rule",
        states={
            "NEW": WorkflowState(label="New", transitions=[
                WorkflowTransition(
                    action="verify", target="DONE",
                    required_fields=["total_gross", "iban"],
                ),
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
    """Clicking an available edge sets pending, then _on_apply emits the signal."""
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    widget.load(simple_rule, workflow_info, {})

    emitted = []
    widget.transition_triggered.connect(lambda *args: emitted.append(args))

    # Simulate clicking an available edge — sets pending, does NOT emit signal yet
    edges = [i for i in widget._scene.items() if isinstance(i, TransitionEdge)]
    assert edges, "No edges found"
    edge = edges[0]
    assert edge._click_cb is not None
    edge._click_cb(edge)

    # Signal must NOT be emitted by the click alone
    assert len(emitted) == 0, "Click alone must not emit signal; Apply button is required"

    # Now apply the pending transition
    widget._on_apply()

    assert len(emitted) == 1
    rule_id, action, target, is_auto = emitted[0]
    assert rule_id == "test_rule"
    assert action == "verify"
    assert target == "DONE"
    assert is_auto is False


def test_run_mode_drag_mode_is_nodrag(qtbot, simple_rule, workflow_info):
    """Run mode must not use ScrollHandDrag — that mode consumes left-button clicks
    for view panning and prevents TransitionEdge.mousePressEvent from firing."""
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    assert widget._view.dragMode() == QGraphicsView.DragMode.NoDrag


def _click_item_via_view(qtbot, widget: WorkflowGraphWidget, item) -> None:
    """Helper: left-click the centre of *item* through the view's viewport."""
    scene_center = item.mapToScene(item.boundingRect().center())
    view_pt: QPoint = widget._view.mapFromScene(scene_center)
    qtbot.mouseClick(widget._view.viewport(), Qt.MouseButton.LeftButton, pos=view_pt)


def test_run_mode_click_on_edge_triggers_signal(qtbot, simple_rule, workflow_info):
    """Clicking an available edge sets pending; Apply then emits transition_triggered.

    Integration test: drives the full event path viewport → scene → item.
    The earlier unit test (test_run_mode_transition_triggers_signal) calls _click_cb
    directly and would NOT catch a view-level event-swallowing regression.
    """
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    widget.resize(600, 300)
    widget.show()
    qtbot.waitExposed(widget)
    widget.load(simple_rule, workflow_info, {})
    widget._fit_view()

    emitted: list = []
    widget.transition_triggered.connect(lambda *args: emitted.append(args))

    edges = [i for i in widget._scene.items() if isinstance(i, TransitionEdge)]
    assert edges, "No TransitionEdge items in scene after load()"
    edge = edges[0]
    assert edge.is_available, "Edge should be available (no required_fields)"
    assert edge._click_cb is not None, "Edge must have click_callback in run mode"

    # Click the edge — this sets pending but does NOT emit the signal
    _click_item_via_view(qtbot, widget, edge)

    assert len(emitted) == 0, (
        f"Click alone must not emit signal; got {len(emitted)}. "
        "Pending must be set first, then Apply commits."
    )
    # Verify pending was set
    assert widget._pending_action == "verify", "Pending action must be set after edge click"
    assert widget._pending_target == "DONE", "Pending target must be set after edge click"

    # Now press Apply
    widget._on_apply()

    assert len(emitted) == 1, (
        f"Expected 1 emission after _on_apply(), got {len(emitted)}."
    )
    rule_id, action, target, is_auto = emitted[0]
    assert rule_id == "test_rule"
    assert action == "verify"
    assert target == "DONE"
    assert is_auto is False


def test_run_mode_click_on_target_node_triggers_signal(qtbot, simple_rule, workflow_info):
    """Clicking a target state node sets pending; Apply then emits transition_triggered.

    Users expect both the arrow and the destination box to be clickable (to set pending).
    """
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    widget.resize(600, 300)
    widget.show()
    qtbot.waitExposed(widget)
    widget.load(simple_rule, workflow_info, {})
    widget._fit_view()

    emitted: list = []
    widget.transition_triggered.connect(lambda *args: emitted.append(args))

    # Find the target node (DONE — not the current node NEW)
    target_nodes = [
        n for n in widget._scene.items()
        if isinstance(n, StateNode) and n.state_id == "DONE"
    ]
    assert target_nodes, "Target node DONE not found in scene"
    tgt_node = target_nodes[0]
    assert tgt_node._click_cb is not None, (
        "Target node must have a click_callback assigned in run mode"
    )

    # Click the target node — sets pending, does NOT emit signal
    _click_item_via_view(qtbot, widget, tgt_node)

    assert len(emitted) == 0, (
        f"Click alone must not emit signal; got {len(emitted)}. "
        "Pending must be confirmed with Apply."
    )
    assert widget._pending_action == "verify", "Pending action must be set after node click"
    assert widget._pending_target == "DONE", "Pending target must be set after node click"

    # Now press Apply
    widget._on_apply()

    assert len(emitted) == 1, f"Expected 1 emission after _on_apply(), got {len(emitted)}"
    rule_id, action, target, is_auto = emitted[0]
    assert rule_id == "test_rule"
    assert action == "verify"
    assert target == "DONE"
    assert is_auto is False


def test_run_mode_blocked_transition_not_clickable(
    qtbot, rule_with_required_fields, workflow_info
):
    """A transition with unmet required_fields must NOT be clickable in run mode.

    Blocked transitions show a tooltip with the missing fields but do not allow
    the user to set them as pending or trigger them. Only available transitions
    can be selected via click.
    """
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    widget.resize(600, 300)
    widget.show()
    qtbot.waitExposed(widget)
    # Empty doc_data → required_fields NOT met → is_available=False
    widget.load(rule_with_required_fields, workflow_info, {})
    widget._fit_view()

    edges = [i for i in widget._scene.items() if isinstance(i, TransitionEdge)]
    assert edges, "No edges in scene"
    edge = edges[0]
    assert not edge.is_available, "Precondition: edge must be blocked for this test"
    # Blocked edge must NOT have a click callback (is_available guard prevents it)
    assert edge._click_cb is None, "Blocked edge must not have a click callback"

    emitted: list = []
    widget.transition_triggered.connect(lambda *args: emitted.append(args))

    # Click via edge — must NOT set pending or emit signal
    _click_item_via_view(qtbot, widget, edge)
    assert len(emitted) == 0, "Blocked transition must not fire signal when clicked"
    assert widget._pending_action is None, "Blocked transition must not set pending"

    # Target node for a blocked transition must also NOT have a click callback
    tgt_nodes = [
        n for n in widget._scene.items()
        if isinstance(n, StateNode) and n.state_id == "DONE"
    ]
    assert tgt_nodes, "Target node DONE not in scene"
    assert tgt_nodes[0]._click_cb is None, (
        "Target node must NOT have a click_callback when the only incoming transition is blocked"
    )


def test_run_mode_blocked_transition_has_tooltip(
    qtbot, rule_with_required_fields, workflow_info
):
    """Blocked transitions must expose a tooltip naming the missing fields."""
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    widget.load(rule_with_required_fields, workflow_info, {})

    edges = [i for i in widget._scene.items() if isinstance(i, TransitionEdge)]
    assert edges
    edge = edges[0]
    assert not edge.is_available
    tip = edge.toolTip()
    assert "total_gross" in tip
    assert "iban" in tip

    # Target node should carry the same hint
    tgt_nodes = [
        n for n in widget._scene.items()
        if isinstance(n, StateNode) and n.state_id == "DONE"
    ]
    assert tgt_nodes
    assert "total_gross" in tgt_nodes[0].toolTip()


def test_run_mode_available_transition_has_no_tooltip(qtbot, simple_rule, workflow_info):
    """Available transitions (all required fields present or none required) must
    not show a missing-fields tooltip."""
    widget = WorkflowGraphWidget(mode="run")
    qtbot.addWidget(widget)
    widget.load(simple_rule, workflow_info, {})

    edges = [i for i in widget._scene.items() if isinstance(i, TransitionEdge)]
    assert edges
    assert edges[0].toolTip() == ""


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

    # _cmd_add_state() asks only for the label; ID is auto-generated
    with patch("gui.widgets.workflow_graph.QInputDialog.getText",
               return_value=("Pending", True)):
        widget._cmd_add_state()

    assert len(changed_signals) >= 1
    labels = [s.label for s in widget._rule.states.values()]
    assert "Pending" in labels


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
