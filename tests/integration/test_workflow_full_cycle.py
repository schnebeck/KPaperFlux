import pytest
from PyQt6.QtCore import Qt
from gui.metadata_editor import MetadataEditorWidget
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, WorkflowInfo
from core.workflow import WorkflowRuleRegistry, WorkflowRule, WorkflowState, WorkflowTransition, WorkflowCondition
from unittest.mock import MagicMock

@pytest.fixture
def editor(qtbot):
    db_mock = MagicMock()
    widget = MetadataEditorWidget()
    widget.set_db_manager(db_mock)
    qtbot.addWidget(widget)
    return widget

def test_manual_transition_updates_history(qtbot, editor):
    # Setup Rule
    registry = WorkflowRuleRegistry()
    registry.rules.clear()
    rule = WorkflowRule(
        id="manual_rule",
        states={
            "NEW": WorkflowState(transitions=[
                WorkflowTransition(action="verify", target="DONE")
            ])
        }
    )
    registry.rules["manual_rule"] = rule

    # Setup Doc with workflow in dict
    doc = VirtualDocument(uuid="test-uuid")
    doc.semantic_data = SemanticExtraction(
        workflows={"manual_rule": WorkflowInfo(rule_id="manual_rule", current_step="NEW")}
    )

    editor.display_document(doc)

    # Find the workflow control for manual_rule
    assert "manual_rule" in editor._workflow_controls
    ctrl = editor._workflow_controls["manual_rule"]

    # Find the verify button
    verify_btn = None
    for i in range(ctrl.buttons_layout.count()):
        w = ctrl.buttons_layout.itemAt(i).widget()
        if w and "Verify" in w.text():
            verify_btn = w
            break

    assert verify_btn is not None

    # Click it
    qtbot.mouseClick(verify_btn, Qt.MouseButton.LeftButton)

    # Verify History
    history = doc.semantic_data.workflows["manual_rule"].history
    assert len(history) == 1
    assert "TRANSITION: verify (NEW -> DONE)" in history[0].action
    assert history[0].user == "USER"
    assert doc.semantic_data.workflows["manual_rule"].current_step == "DONE"

def test_auto_transition_updates_history_immediately(qtbot, editor):
    # Setup Rule with Auto-Transition
    registry = WorkflowRuleRegistry()
    registry.rules.clear()
    rule = WorkflowRule(
        id="auto_rule",
        states={
            "NEW": WorkflowState(transitions=[
                WorkflowTransition(action="skip", target="AUTO_DONE", auto=True)
            ]),
            "AUTO_DONE": WorkflowState(final=True)
        }
    )
    registry.rules["auto_rule"] = rule

    # Setup Doc
    doc = VirtualDocument(uuid="auto-uuid")
    doc.semantic_data = SemanticExtraction(
        workflows={"auto_rule": WorkflowInfo(rule_id="auto_rule", current_step="NEW")}
    )

    # Displaying doc should trigger the auto-transition
    editor.display_document(doc)

    # The signal is emitted from WorkflowControlsWidget, caught by MetadataEditorWidget
    qtbot.wait(100)  # Small wait to ensure signals are processed

    history = doc.semantic_data.workflows["auto_rule"].history
    assert len(history) == 1
    assert "TRANSITION: skip (NEW -> AUTO_DONE)" in history[0].action
    assert history[0].user == "SYSTEM"
    assert doc.semantic_data.workflows["auto_rule"].current_step == "AUTO_DONE"
