
import pytest
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, WorkflowInfo
from core.filter_tree import FilterTree, FilterNode, NodeType
from core.rules_engine import RulesEngine
from core.database import DatabaseManager
from unittest.mock import MagicMock

@pytest.fixture
def mock_db():
    db = MagicMock(spec=DatabaseManager)
    db.matches_condition.return_value = True
    return db

@pytest.fixture
def filter_tree():
    tree = FilterTree()
    return tree

def test_rule_assignment_of_workflow(mock_db, filter_tree):
    # 1. Setup a document without any workflow
    doc = VirtualDocument(uuid="test-uuid")
    doc.semantic_data = SemanticExtraction()
    assert len(doc.semantic_data.workflows) == 0

    # 2. Setup a rule with workflow assignment
    rule = FilterNode("Test Workflow Rule", NodeType.FILTER)
    rule.assign_workflow = "special_invoice_flow"
    rule.data = {"field": "sender", "op": "equals", "value": "Amazon"}

    # 3. Apply rule via engine
    engine = RulesEngine(mock_db, filter_tree)
    modified = engine.apply_rules_to_entity(doc, rules=[rule])

    # 4. Verify assignment
    assert modified is True
    assert "special_invoice_flow" in doc.semantic_data.workflows
    assert doc.semantic_data.workflows["special_invoice_flow"].rule_id == "special_invoice_flow"
    assert doc.semantic_data.workflows["special_invoice_flow"].current_step == "NEW"

def test_rule_assignment_adds_to_existing(mock_db, filter_tree):
    """Adding a new rule does not remove existing ones."""
    doc = VirtualDocument(uuid="test-uuid")
    doc.semantic_data = SemanticExtraction()
    doc.semantic_data.workflows["old_flow"] = WorkflowInfo(rule_id="old_flow", current_step="STEP1")

    rule = FilterNode("Add New Workflow", NodeType.FILTER)
    rule.assign_workflow = "new_flow"

    engine = RulesEngine(mock_db, filter_tree)
    modified = engine.apply_rules_to_entity(doc, rules=[rule])

    assert modified is True
    assert "old_flow" in doc.semantic_data.workflows
    assert "new_flow" in doc.semantic_data.workflows

def test_rule_assignment_no_change_if_already_present(mock_db, filter_tree):
    """If the workflow is already in the dict, applying the same rule yields no change."""
    doc = VirtualDocument(uuid="test-uuid")
    doc.semantic_data = SemanticExtraction()
    doc.semantic_data.workflows["correct_flow"] = WorkflowInfo(rule_id="correct_flow")

    rule = FilterNode("Same Workflow", NodeType.FILTER)
    rule.assign_workflow = "correct_flow"

    engine = RulesEngine(mock_db, filter_tree)
    modified = engine.apply_rules_to_entity(doc, rules=[rule])

    # No change because the workflow is already present and no tags changed
    assert modified is False
