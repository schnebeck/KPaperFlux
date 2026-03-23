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
    A document with an INVOICE tag and no workflows should have the matching rule
    auto-assigned in its workflows dict when displayed.
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
    assert len(doc.semantic_data.workflows) == 0

    # 3. Display Doc
    editor.display_document(doc)

    # 4. Verify that rule was added to workflows dict
    assert "test_invoice_rule" in doc.semantic_data.workflows
    assert doc.semantic_data.workflows["test_invoice_rule"].current_step == "NEW"

    # Verify UI has a control for this rule
    assert "test_invoice_rule" in editor._workflow_controls

def test_multi_rule_assignment_on_display(qtbot, editor):
    """
    A document with multiple type_tags matching multiple rules should get
    all matching rules assigned simultaneously.
    """
    registry = WorkflowRuleRegistry()
    registry.rules.clear()

    rule_invoice = WorkflowRule(
        id="rule_invoice",
        triggers={"type_tags": ["INVOICE"]},
        states={"NEW": {"label": "New"}}
    )
    rule_order = WorkflowRule(
        id="rule_order",
        triggers={"type_tags": ["ORDER_CONFIRMATION"]},
        states={"NEW": {"label": "New"}}
    )
    registry.rules["rule_invoice"] = rule_invoice
    registry.rules["rule_order"] = rule_order

    doc = VirtualDocument(uuid="multi-doc")
    doc.type_tags = ["INVOICE", "ORDER_CONFIRMATION"]
    doc.semantic_data = SemanticExtraction()

    editor.display_document(doc)

    assert "rule_invoice" in doc.semantic_data.workflows
    assert "rule_order" in doc.semantic_data.workflows
    assert len(editor._workflow_controls) == 2

def test_existing_workflow_not_overwritten_on_display(qtbot, editor):
    """
    If a workflow is already in progress (e.g. STEP_2), displaying the doc
    again should not reset it to NEW.
    """
    registry = WorkflowRuleRegistry()
    registry.rules.clear()

    rule = WorkflowRule(
        id="rule_invoice",
        triggers={"type_tags": ["INVOICE"]},
        states={"NEW": {"label": "New"}, "STEP_2": {"label": "Step 2"}}
    )
    registry.rules["rule_invoice"] = rule

    doc = VirtualDocument(uuid="doc2")
    doc.type_tags = ["INVOICE"]
    doc.semantic_data = SemanticExtraction(
        workflows={"rule_invoice": WorkflowInfo(rule_id="rule_invoice", current_step="STEP_2")}
    )

    editor.display_document(doc)

    # Step should NOT be reset to NEW
    assert doc.semantic_data.workflows["rule_invoice"].current_step == "STEP_2"
