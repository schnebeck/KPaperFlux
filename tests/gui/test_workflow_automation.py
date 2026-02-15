import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from gui.metadata_editor import MetadataEditorWidget
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, WorkflowInfo
from core.workflow import WorkflowRuleRegistry, WorkflowRule

@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])

@pytest.fixture
def editor(qtbot):
    widget = MetadataEditorWidget(db_manager=MagicMock())
    qtbot.addWidget(widget)
    return widget

def test_auto_rule_assignment_on_display(qtbot, editor):
    """
    Test that if a document has 'INVOICE' tag but no rule_id, 
    the editor automatically assigns the matching rule.
    """
    # 1. Setup Registry with a mock rule for INVOICE
    registry = WorkflowRuleRegistry()
    registry.rules.clear()
    
    rule = WorkflowRule(
        id="test_invoice_rule",
        name="Test Invoice Rule",
        triggers={"type_tags": ["INVOICE"]},
        states={"NEW": {"label": "New"}}
    )
    registry.rules["test_invoice_rule"] = rule
    
    # 2. Create Doc with INVOICE tag but no workflow info
    doc = VirtualDocument(uuid="doc1")
    doc.type_tags = ["INVOICE"]
    doc.semantic_data = SemanticExtraction() 
    # workflow is None by default in SemanticExtraction if not initialized
    
    # 3. Display Doc
    editor.display_document(doc)
    
    # 4. Verify that rule_id was assigned
    # We check the internal doc state or the UI
    assert doc.semantic_data.workflow is not None
    assert doc.semantic_data.workflow.rule_id == "test_invoice_rule"
    
    # Verify UI updated
    assert editor.workflow_controls.rule_id == "test_invoice_rule"

def test_no_auto_reassignment_if_already_set(qtbot, editor):
    """
    If a rule is already set (e.g. manually), don't override it on display.
    """
    registry = WorkflowRuleRegistry()
    registry.rules.clear()
    
    rule_invoice = WorkflowRule(id="rule_invoice", triggers={"type_tags": ["INVOICE"]})
    rule_other = WorkflowRule(id="rule_other", triggers={"type_tags": ["OTHER"]})
    registry.rules["rule_invoice"] = rule_invoice
    registry.rules["rule_other"] = rule_other
    
    doc = VirtualDocument(uuid="doc1")
    doc.type_tags = ["INVOICE"]
    doc.semantic_data = SemanticExtraction(
        workflow=WorkflowInfo(rule_id="manual_rule", current_step="SOME_STEP")
    )
    
    editor.display_document(doc)
    
    # Should NOT be changed to rule_invoice
    assert doc.semantic_data.workflow.rule_id == "manual_rule"
