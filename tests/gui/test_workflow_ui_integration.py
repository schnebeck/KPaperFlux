import pytest
from PyQt6.QtCore import Qt
from gui.widgets.workflow_controls import WorkflowControlsWidget
from core.workflow import WorkflowRuleRegistry, WorkflowRule, WorkflowState, WorkflowTransition, WorkflowCondition

@pytest.fixture
def controls(qtbot):
    widget = WorkflowControlsWidget()
    qtbot.addWidget(widget)
    return widget

def test_ui_updates_on_new_rule(qtbot, controls):
    registry = WorkflowRuleRegistry()
    registry.rules.clear()
    
    rule = WorkflowRule(
        id="test_ui_rule",
        states={
            "NEW": WorkflowState(label="Initial Step", transitions=[
                WorkflowTransition(action="verify", target="DONE")
            ])
        }
    )
    registry.rules["test_ui_rule"] = rule
    
    controls.update_workflow("test_ui_rule", "NEW", {})
    
    assert "Initial Step" in controls.status_lbl.text()
    # Check if 'Verify' button exists and is enabled
    verify_btn = None
    for i in range(controls.buttons_layout.count()):
        w = controls.buttons_layout.itemAt(i).widget()
        if w.text() == "Verify":
            verify_btn = w
            break
    
    assert verify_btn is not None
    assert verify_btn.isEnabled()

def test_ui_disables_button_on_missing_fields(qtbot, controls):
    registry = WorkflowRuleRegistry()
    registry.rules.clear()
    
    rule = WorkflowRule(
        id="test_fields_rule",
        states={
            "NEW": WorkflowState(label="New", transitions=[
                WorkflowTransition(action="approve", target="DONE", required_fields=["iban"])
            ])
        }
    )
    registry.rules["test_fields_rule"] = rule
    
    # 1. No iban -> Disabled
    controls.update_workflow("test_fields_rule", "NEW", {})
    approve_btn = controls.buttons_layout.itemAt(0).widget()
    assert not approve_btn.isEnabled()
    assert "Missing fields: iban" in approve_btn.toolTip()
    
    # 2. With iban -> Enabled
    controls.update_workflow("test_fields_rule", "NEW", {"iban": "DE123"})
    approve_btn = controls.buttons_layout.itemAt(0).widget()
    assert approve_btn.isEnabled()

def test_ui_signal_emission(qtbot, controls):
    registry = WorkflowRuleRegistry()
    registry.rules.clear()
    
    rule = WorkflowRule(
        id="test_signal_rule",
        states={
            "NEW": WorkflowState(transitions=[
                WorkflowTransition(action="go", target="NEXT")
            ])
        }
    )
    registry.rules["test_signal_rule"] = rule
    controls.update_workflow("test_signal_rule", "NEW", {})
    
    with qtbot.waitSignal(controls.transition_triggered) as blocker:
        go_btn = controls.buttons_layout.itemAt(0).widget()
        qtbot.mouseClick(go_btn, Qt.MouseButton.LeftButton)
        
    assert blocker.args == ["go", "NEXT", False]

def test_auto_transition_emits_immediately(qtbot, controls):
    """
    Test that an auto-transition is triggered automatically when update_workflow is called.
    """
    registry = WorkflowRuleRegistry()
    registry.rules.clear()
    
    rule = WorkflowRule(
        id="test_auto_ui",
        states={
            "NEW": WorkflowState(transitions=[
                WorkflowTransition(action="skip_me", target="AUTO_STEP", auto=True)
            ])
        }
    )
    registry.rules["test_auto_ui"] = rule
    
    with qtbot.waitSignal(controls.transition_triggered) as blocker:
        controls.update_workflow("test_auto_ui", "NEW", {})
        
    assert blocker.args == ["skip_me", "AUTO_STEP", True]
