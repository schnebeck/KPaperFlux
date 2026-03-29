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

from core.workflow import WorkflowRule, WorkflowState, WorkflowTransition, WorkflowCondition, StateType
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


def test_state_type_combo_change_no_segfault(qtbot, two_state_rule):
    """Changing the state type combo (currentIndexChanged) must not segfault."""
    from PyQt6.QtWidgets import QComboBox
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_node(editor, "NEW")

    fl = editor._detail_form_layout
    type_combo = fl.itemAt(1, QFormLayout.ItemRole.FieldRole).widget()  # row 1: Type
    assert isinstance(type_combo, QComboBox)

    # Select END_OK (index 2 in the combo)
    type_combo.setCurrentIndex(2)

    qtbot.wait(50)

    assert not editor._detail_form.isHidden()
    assert editor._detail_hint.isHidden()


# ── Positive: semantics after edit ────────────────────────────────────────────

def test_state_type_combo_persists_in_rule(qtbot, two_state_rule):
    """After selecting END_OK the rule model must reflect state_type and final."""
    from PyQt6.QtWidgets import QComboBox
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_node(editor, "NEW")

    fl = editor._detail_form_layout
    type_combo = fl.itemAt(1, QFormLayout.ItemRole.FieldRole).widget()
    assert isinstance(type_combo, QComboBox)
    # END_OK is at index 2 in the _type_labels dict
    type_combo.setCurrentIndex(2)

    qtbot.wait(50)

    rule = editor.get_rule()
    assert rule.states["NEW"].state_type == StateType.END_OK
    assert rule.states["NEW"].is_terminal is True


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
    """Toggling required-field checkboxes (itemChanged) must not segfault."""
    from PyQt6.QtWidgets import QTreeWidget
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(two_state_rule)
    _select_edge(editor, "NEW", "go")

    fl = editor._detail_form_layout
    req_tree = fl.itemAt(2, QFormLayout.ItemRole.FieldRole).widget()
    assert isinstance(req_tree, QTreeWidget)

    # Check the first field in the first group (total_gross / Gross Amount)
    first_group = req_tree.topLevelItem(0)
    first_field = first_group.child(0)
    first_field.setCheckState(0, Qt.CheckState.Checked)

    qtbot.wait(80)

    assert not editor._detail_form.isHidden()
    rule = editor.get_rule()
    assert "total_gross" in rule.states["NEW"].transitions[0].required_fields


# ── Condition editor ──────────────────────────────────────────────────────────

@pytest.fixture()
def rule_with_conditions() -> WorkflowRule:
    """Rule whose transition already carries a WorkflowCondition."""
    return WorkflowRule(
        id="cond_rule",
        name="Condition Rule",
        states={
            "WAIT": WorkflowState(label="Waiting", transitions=[
                WorkflowTransition(
                    action="escalate",
                    target="DONE",
                    conditions=[
                        WorkflowCondition(field="DAYS_IN_STATE", op=">", value=10),
                    ],
                ),
            ]),
            "DONE": WorkflowState(label="Done", state_type="END_OK", final=True),
        },
    )


def test_existing_conditions_shown_in_table(qtbot, rule_with_conditions):
    """Conditions already on a transition must be pre-populated in the table."""
    from PyQt6.QtWidgets import QTableWidget
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(rule_with_conditions)
    _select_edge(editor, "WAIT", "escalate")

    fl = editor._detail_form_layout
    cond_container = fl.itemAt(3, QFormLayout.ItemRole.FieldRole).widget()
    table = cond_container.findChild(QTableWidget)

    assert table is not None
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "DAYS_IN_STATE"
    assert table.item(0, 2).text() == "10"


def test_add_condition_button_appends_row(qtbot, rule_with_conditions):
    """Clicking '+ Condition' must add a row to the conditions table.

    After _apply() runs, _rebuild() recreates the graph and the edge is
    re-selected — the table widget is replaced, so we check via the rule model
    rather than the stale widget reference.
    """
    from PyQt6.QtWidgets import QPushButton
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(rule_with_conditions)
    _select_edge(editor, "WAIT", "escalate")

    fl = editor._detail_form_layout
    cond_container = fl.itemAt(3, QFormLayout.ItemRole.FieldRole).widget()

    btn_add = next(
        (b for b in cond_container.findChildren(QPushButton) if "+" in b.text()), None
    )
    assert btn_add is not None
    btn_add.click()

    qtbot.wait(80)

    # New default row has field="DAYS_IN_STATE", value="0" — verify via model
    rule = editor.get_rule()
    conds = rule.states["WAIT"].transitions[0].conditions
    assert len(conds) == 2


def test_conditions_persist_in_rule_after_edit(qtbot, rule_with_conditions):
    """After editing the condition field cell the rule model must update."""
    from PyQt6.QtWidgets import QTableWidget
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(rule_with_conditions)
    _select_edge(editor, "WAIT", "escalate")

    fl = editor._detail_form_layout
    cond_container = fl.itemAt(3, QFormLayout.ItemRole.FieldRole).widget()
    table = cond_container.findChild(QTableWidget)

    # Change the value cell from "10" to "30"
    table.item(0, 2).setText("30")
    # Trigger itemChanged → deferred _apply
    qtbot.wait(80)

    rule = editor.get_rule()
    conds = rule.states["WAIT"].transitions[0].conditions
    assert len(conds) == 1
    assert conds[0].value == 30.0


def test_remove_condition_updates_rule(qtbot, rule_with_conditions):
    """Selecting a condition row and clicking '− Remove' must delete it."""
    from PyQt6.QtWidgets import QTableWidget, QPushButton
    editor = WorkflowRuleFormEditor()
    qtbot.addWidget(editor)
    editor.load_rule(rule_with_conditions)
    _select_edge(editor, "WAIT", "escalate")

    fl = editor._detail_form_layout
    cond_container = fl.itemAt(3, QFormLayout.ItemRole.FieldRole).widget()
    table = cond_container.findChild(QTableWidget)
    assert table.rowCount() == 1

    table.selectRow(0)
    btn_del = next(
        (b for b in cond_container.findChildren(QPushButton) if "−" in b.text()), None
    )
    assert btn_del is not None
    btn_del.click()

    qtbot.wait(80)

    rule = editor.get_rule()
    assert rule.states["WAIT"].transitions[0].conditions == []
