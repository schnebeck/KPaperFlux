
import pytest
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction
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
    # 1. Setup a document without workflow
    doc = VirtualDocument(uuid="test-uuid")
    doc.semantic_data = SemanticExtraction()
    assert doc.semantic_data.workflow.playbook_id is None

    # 2. Setup a rule with workflow assignment
    rule = FilterNode("Test Workflow Rule", NodeType.FILTER)
    rule.assign_workflow = "special_invoice_flow"
    rule.data = {"field": "sender", "op": "equals", "value": "Amazon"}
    
    # 3. Apply rule via engine
    engine = RulesEngine(mock_db, filter_tree)
    modified = engine.apply_rules_to_entity(doc, rules=[rule])
    
    # 4. Verify assignment
    assert modified is True
    assert doc.semantic_data.workflow.playbook_id == "special_invoice_flow"

def test_rule_assignment_precedence(mock_db, filter_tree):
    # Setup document
    doc = VirtualDocument(uuid="test-uuid")
    doc.semantic_data = SemanticExtraction()
    doc.semantic_data.workflow.playbook_id = "old_flow"

    # Setup rule that changes it
    rule = FilterNode("Override Workflow", NodeType.FILTER)
    rule.assign_workflow = "new_flow"
    
    engine = RulesEngine(mock_db, filter_tree)
    modified = engine.apply_rules_to_entity(doc, rules=[rule])
    
    assert modified is True
    assert doc.semantic_data.workflow.playbook_id == "new_flow"

def test_rule_assignment_no_change(mock_db, filter_tree):
    # Setup document
    doc = VirtualDocument(uuid="test-uuid")
    doc.semantic_data = SemanticExtraction()
    doc.semantic_data.workflow.playbook_id = "correct_flow"

    # Setup rule with same workflow
    rule = FilterNode("Same Workflow", NodeType.FILTER)
    rule.assign_workflow = "correct_flow"
    
    engine = RulesEngine(mock_db, filter_tree)
    # If only tags change or nothing, it should return False regarding the workflow part
    modified = engine.apply_rules_to_entity(doc, rules=[rule])
    
    assert modified is False # No change because tags didn't change and workflow is same
