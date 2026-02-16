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
    
    # Setup Doc
    doc = VirtualDocument(uuid="test-uuid")
    doc.semantic_data = SemanticExtraction(
        workflow=WorkflowInfo(rule_id="manual_rule", current_step="NEW")
    )
    
    editor.display_document(doc)
    
    # Find the button
    verify_btn = None
    for i in range(editor.workflow_controls.buttons_layout.count()):
        w = editor.workflow_controls.buttons_layout.itemAt(i).widget()
        if w.text() == "Verify":
            verify_btn = w
            break
    
    assert verify_btn is not None
    
    # Click it
    qtbot.mouseClick(verify_btn, Qt.MouseButton.LeftButton)
    
    # Verify History
    history = doc.semantic_data.workflow.history
    assert len(history) == 1
    assert "TRANSITION: verify (NEW -> DONE)" in history[0].action
    assert history[0].user == "USER"
    assert doc.semantic_data.workflow.current_step == "DONE"

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
        workflow=WorkflowInfo(rule_id="auto_rule", current_step="NEW")
    )
    
    # Displaying doc should trigger the auto-transition
    editor.display_document(doc)
    
    # The signal is emitted from WorkflowControlsWidget, caught by MetadataEditorWidget
    # which updates the doc.
    
    # Note: Because the signal might be queued, we might need to wait or process events.
    qtbot.wait(100) # Small wait to ensure signals are processed
    
    history = doc.semantic_data.workflow.history
    assert len(history) == 1
    assert "TRANSITION: skip (NEW -> AUTO_DONE)" in history[0].action
    assert history[0].user == "SYSTEM"
    assert doc.semantic_data.workflow.current_step == "AUTO_DONE"
