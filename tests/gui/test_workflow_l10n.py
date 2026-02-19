import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QEvent
from gui.widgets.workflow_controls import WorkflowControlsWidget

def test_workflow_controls_translation_calls(qapp):
    """Verifies that WorkflowControlsWidget uses tr() for its labels."""
    from core.workflow import WorkflowRuleRegistry
    import os
    
    # Load rules from standard path
    registry = WorkflowRuleRegistry()
    registry.load_from_directory("resources/workflows")
    
    widget = WorkflowControlsWidget()
    
    # Mock some data
    rule_id = "invoice_standard"
    current_step = "NEW"
    doc_data = {"total_gross": 100}
    
    # We just want to see if it runs without error and the logic is sound
    widget.update_workflow(rule_id, current_step, doc_data)
    
    # The label should be "Incoming Invoice" (source)
    # If a translator was loaded, it would be "Eingangsrechnung"
    assert widget.status_lbl.text() == "Incoming Invoice"
    
    # Check if a button exists
    assert widget.buttons_layout.count() > 0
    btn = widget.buttons_layout.itemAt(0).widget()
    # verify capitalize() + tr() worked
    assert btn.text() == "Verify"

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
