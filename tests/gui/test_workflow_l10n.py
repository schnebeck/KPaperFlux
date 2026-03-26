import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QEvent
from gui.widgets.workflow_controls import WorkflowControlsWidget

def test_workflow_controls_translation_calls(qapp):
    """Verifies that WorkflowControlsWidget renders a rule without errors.

    Uses an inline fixture rule so the test is independent of the JSON files
    in resources/workflows/ (which are user-editable and their content changes).
    """
    from core.workflow import WorkflowRuleRegistry, WorkflowRule, WorkflowState, WorkflowTransition

    rule = WorkflowRule(
        id="_test_l10n_rule",
        name="L10n Test Rule",
        states={
            "OPEN": WorkflowState(label="Open Invoice", transitions=[
                WorkflowTransition(action="approve", target="DONE"),
            ]),
            "DONE": WorkflowState(label="Approved", final=True),
        },
        triggers={"type_tags": ["_TEST"]},
    )
    WorkflowRuleRegistry().rules["_test_l10n_rule"] = rule

    widget = WorkflowControlsWidget()
    widget.update_workflow("_test_l10n_rule", "OPEN", {"total_gross": 100})

    # Status label shows the state label (possibly translated)
    assert widget.status_lbl.text() != ""
    assert widget.status_lbl.text() != "No Workflow"

    # At least one transition button must be rendered
    assert widget.buttons_layout.count() > 0
    btn = widget.buttons_layout.itemAt(0).widget()
    assert btn.text() != ""

    # Cleanup
    WorkflowRuleRegistry().rules.pop("_test_l10n_rule", None)

def test_metadata_editor_status_l10n(qapp):
    """Verifies that status combo in MetadataEditor uses translations."""
    from gui.metadata_editor import MetadataEditorWidget
    widget = MetadataEditorWidget()
    
    # Check if "Processed" is in the combo (source)
    found = False
    for i in range(widget.status_combo.count()):
        if widget.status_combo.itemText(i) == "Processed":
            found = True
            break
    assert found
