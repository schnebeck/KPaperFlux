"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/integration/test_state_property_edit_crash.py
Version:        1.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Regression tests for the segfault that occurred when editing
                state or transition properties in the WorkflowRuleFormEditor
                right panel.

                Root cause: _apply() was called synchronously from an
                editingFinished / stateChanged handler.  Inside _apply(),
                _rebuild() cleared the scene which triggered selectionChanged
                → _on_item_selected(None) → fl.removeRow() — deleting the
                very widget whose signal handler was still on the call stack.

                Fix: all signal-to-_apply connections now use
                QTimer.singleShot(0, _apply) so the handler returns before
                any widget manipulation occurs.  This covers both state
                editing (_fill_state_detail) and transition editing
                (_fill_transition_detail).
------------------------------------------------------------------------------
"""
import pytest
from PyQt6.QtWidgets import QFormLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest

from core.workflow import WorkflowRule, WorkflowState, WorkflowTransition
from gui.workflow_manager import WorkflowRuleFormEditor


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def two_state_rule() -> WorkflowRule:
    return WorkflowRule(
        id="crash_regression",
        name="Crash Regression",
        states={
            "NEW": WorkflowState(label="New", transitions=[
                WorkflowTransition(action="go", target="DONE"),
            ]),
            "DONE": WorkflowState(label="Done", final=True),
        },
        triggers={},
    )


def _select_node(editor: WorkflowRuleFormEditor, state_id: str):
    """Helper: simulate selecting a state node in the graph."""
    node = editor._graph_widget._nodes.get(state_id)
    assert node is not None, f"Node '{state_id}' not found after load"
    editor._on_item_selected(node)
    return node


# ── Positive: editing label must not crash ────────────────────────────────────

def test_label_edit_no_segfault(qtbot, two_state_rule):
    """Changing a state label (editingFinished) must not segfault."""
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_node(editor, "NEW")

    fl = editor._detail_form_layout
    lbl_edit = fl.itemAt(0, QFormLayout.ItemRole.FieldRole).widget()  # row 0: Label

    lbl_edit.setText("Renamed Label")
    QTest.keyClick(lbl_edit, Qt.Key.Key_Return)

    qtbot.wait(50)

    assert not editor._detail_form.isHidden()
    assert editor._detail_hint.isHidden()


def test_final_checkbox_toggle_no_segfault(qtbot, two_state_rule):
    """Toggling 'Final state' checkbox (stateChanged) must not segfault."""
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_node(editor, "NEW")

    fl = editor._detail_form_layout
    final_chk = fl.itemAt(1, QFormLayout.ItemRole.FieldRole).widget()  # row 1: Final

    final_chk.setChecked(True)

    qtbot.wait(50)

    assert not editor._detail_form.isHidden()
    assert editor._detail_hint.isHidden()


# ── Positive: semantics after edit ────────────────────────────────────────────

def test_label_edit_persists_in_rule(qtbot, two_state_rule):
    """After editing a label the rule model must reflect the new value."""
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_node(editor, "NEW")

    fl = editor._detail_form_layout
    lbl_edit = fl.itemAt(0, QFormLayout.ItemRole.FieldRole).widget()
    lbl_edit.setText("Inbox")
    QTest.keyClick(lbl_edit, Qt.Key.Key_Return)

    qtbot.wait(50)

    rule = editor.get_rule()
    assert rule.states["NEW"].label == "Inbox"


def test_state_id_is_stable(qtbot, two_state_rule):
    """Editing a state label must not change its ID — IDs are immutable."""
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_node(editor, "NEW")

    fl = editor._detail_form_layout
    lbl_edit = fl.itemAt(0, QFormLayout.ItemRole.FieldRole).widget()
    lbl_edit.setText("Umbenennt")
    QTest.keyClick(lbl_edit, Qt.Key.Key_Return)

    qtbot.wait(50)

    rule = editor.get_rule()
    # ID must be unchanged
    assert "NEW" in rule.states
    # But label changed
    assert rule.states["NEW"].label == "Umbenennt"


# ── Transition editing — previously untested, caused second segfault ──────────

def _select_edge(editor: WorkflowRuleFormEditor, src_id: str, action: str):
    """Helper: simulate selecting a transition edge in the graph."""
    edge = next(
        (e for e in editor._graph_widget._edges
         if e.src.state_id == src_id and e.transition.action == action),
        None,
    )
    assert edge is not None, f"Edge '{src_id}:{action}' not found"
    editor._on_item_selected(edge)
    return edge


def test_transition_auto_checkbox_no_segfault(qtbot, two_state_rule):
    """Toggling 'Auto' on a transition (stateChanged) must not segfault.

    This is the scenario that caused the second segfault: _fill_transition_detail
    connected auto_chk.stateChanged directly to _apply() without deferral.
    """
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_edge(editor, "NEW", "go")

    fl = editor._detail_form_layout
    auto_chk = fl.itemAt(1, QFormLayout.ItemRole.FieldRole).widget()

    auto_chk.setChecked(True)   # triggers stateChanged → must not segfault

    qtbot.wait(50)

    assert not editor._detail_form.isHidden()
    assert editor._detail_hint.isHidden()


def test_transition_action_rename_no_segfault(qtbot, two_state_rule):
    """Renaming a transition action (editingFinished) must not segfault."""
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_edge(editor, "NEW", "go")

    fl = editor._detail_form_layout
    action_edit = fl.itemAt(0, QFormLayout.ItemRole.FieldRole).widget()

    action_edit.setText("proceed")
    QTest.keyClick(action_edit, Qt.Key.Key_Return)

    qtbot.wait(50)

    assert not editor._detail_form.isHidden()
    assert editor._detail_hint.isHidden()


def test_transition_action_rename_persists(qtbot, two_state_rule):
    """After renaming a transition label the rule model must reflect the change.

    The stable *action* ID ("go") is preserved; only *label* changes.
    """
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_edge(editor, "NEW", "go")

    fl = editor._detail_form_layout
    label_edit = fl.itemAt(0, QFormLayout.ItemRole.FieldRole).widget()  # row 0: Label
    label_edit.setText("proceed")
    QTest.keyClick(label_edit, Qt.Key.Key_Return)

    qtbot.wait(50)

    rule = editor.get_rule()
    t = rule.states["NEW"].transitions[0]
    assert t.label == "proceed"   # display label updated
    assert t.action == "go"       # stable ID unchanged


def test_double_deferred_apply_no_segfault(qtbot, two_state_rule):
    """Two deferred _apply calls in the same event-loop tick must not crash.

    When pressing Enter in lbl_edit, Qt may also fire editingFinished on
    id_edit (focus-out).  Both schedule QTimer.singleShot(0, _apply).  The
    second call must detect that the widgets are already gone and return early.
    """
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_node(editor, "NEW")

    fl = editor._detail_form_layout
    lbl_edit = fl.itemAt(0, QFormLayout.ItemRole.FieldRole).widget()  # row 0: Label

    # Simulate both editingFinished signals firing before the event loop runs
    lbl_edit.setText("Inbox")
    lbl_edit.editingFinished.emit()
    lbl_edit.editingFinished.emit()  # second call — stale after first _apply runs

    qtbot.wait(50)

    # Must still be alive
    assert not editor._detail_form.isHidden()


def test_transition_required_fields_no_segfault(qtbot, two_state_rule):
    """Editing required fields (editingFinished) must not segfault."""
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_edge(editor, "NEW", "go")

    fl = editor._detail_form_layout
    req_edit = fl.itemAt(2, QFormLayout.ItemRole.FieldRole).widget()

    req_edit.setText("iban, total_gross")
    QTest.keyClick(req_edit, Qt.Key.Key_Return)

    qtbot.wait(50)

    assert not editor._detail_form.isHidden()
    rule = editor.get_rule()
    assert rule.states["NEW"].transitions[0].required_fields == ["iban", "total_gross"]
