"""
Tests for multi-workflow support per document.
Verifies that documents with multiple type_tags can have N concurrent workflows.
"""
import pytest
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, WorkflowInfo
from core.workflow import WorkflowRuleRegistry, WorkflowRule, WorkflowEngine
from core.filter_tree import FilterTree, FilterNode, NodeType
from core.rules_engine import RulesEngine
from unittest.mock import MagicMock


@pytest.fixture
def registry():
    reg = WorkflowRuleRegistry()
    reg.rules.clear()
    reg.rules["invoice_flow"] = WorkflowRule(
        id="invoice_flow",
        triggers={"type_tags": ["INVOICE"]},
        states={"NEW": {"label": "New"}, "PAID": {"label": "Paid", "final": True}}
    )
    reg.rules["order_flow"] = WorkflowRule(
        id="order_flow",
        triggers={"type_tags": ["ORDER_CONFIRMATION"]},
        states={"NEW": {"label": "New"}, "CONFIRMED": {"label": "Confirmed", "final": True}}
    )
    return reg


def test_find_rules_for_tags_returns_all_matches(registry):
    """find_rules_for_tags() returns all rules matching any of the given tags."""
    matches = registry.find_rules_for_tags(["INVOICE", "ORDER_CONFIRMATION"])
    rule_ids = {r.id for r in matches}
    assert "invoice_flow" in rule_ids
    assert "order_flow" in rule_ids


def test_find_rules_for_tags_single_match(registry):
    matches = registry.find_rules_for_tags(["INVOICE"])
    assert len(matches) == 1
    assert matches[0].id == "invoice_flow"


def test_find_rules_for_tags_no_match(registry):
    matches = registry.find_rules_for_tags(["UNKNOWN_TAG"])
    assert matches == []


def test_rules_engine_assigns_multiple_workflows(registry):
    """RulesEngine assigns all matching rules to the workflows dict."""
    mock_db = MagicMock()
    mock_db.matches_condition.return_value = True
    filter_tree = FilterTree()

    doc = VirtualDocument(uuid="multi-doc")
    doc.semantic_data = SemanticExtraction()

    rule1 = FilterNode("Invoice Rule", NodeType.FILTER)
    rule1.assign_workflow = "invoice_flow"
    rule1.data = {}

    rule2 = FilterNode("Order Rule", NodeType.FILTER)
    rule2.assign_workflow = "order_flow"
    rule2.data = {}

    engine = RulesEngine(mock_db, filter_tree)
    modified = engine.apply_rules_to_entity(doc, rules=[rule1, rule2])

    assert modified is True
    assert "invoice_flow" in doc.semantic_data.workflows
    assert "order_flow" in doc.semantic_data.workflows


def test_workflows_dict_default_is_empty():
    """SemanticExtraction starts with an empty workflows dict."""
    sd = SemanticExtraction()
    assert sd.workflows == {}


def test_workflows_dict_persists_independently():
    """Each workflow in the dict has its own independent state."""
    sd = SemanticExtraction()
    sd.workflows["invoice_flow"] = WorkflowInfo(rule_id="invoice_flow", current_step="NEW")
    sd.workflows["order_flow"] = WorkflowInfo(rule_id="order_flow", current_step="NEW")

    sd.workflows["invoice_flow"].apply_transition("pay", "PAID", user="TEST")

    assert sd.workflows["invoice_flow"].current_step == "PAID"
    assert sd.workflows["order_flow"].current_step == "NEW"  # unchanged


def test_old_workflow_key_ignored_on_load():
    """Pydantic silently ignores the old 'workflow' key (backward compat)."""
    import json
    from core.models.semantic import SemanticExtraction

    old_json = json.dumps({
        "direction": "INCOMING",
        "workflow": {
            "rule_id": "old_rule",
            "current_step": "STEP_1",
            "history": []
        }
    })

    sd = SemanticExtraction.model_validate_json(old_json)
    # Old 'workflow' key is silently dropped
    assert sd.workflows == {}
    assert sd.direction == "INCOMING"


def test_rules_engine_does_not_reset_in_progress_workflows(registry):
    """If a workflow is already present and in progress, it is not reset to NEW."""
    mock_db = MagicMock()
    mock_db.matches_condition.return_value = True
    filter_tree = FilterTree()

    doc = VirtualDocument(uuid="in-progress")
    doc.semantic_data = SemanticExtraction()
    doc.semantic_data.workflows["invoice_flow"] = WorkflowInfo(
        rule_id="invoice_flow", current_step="PAID"
    )

    rule = FilterNode("Invoice Rule", NodeType.FILTER)
    rule.assign_workflow = "invoice_flow"
    rule.data = {}

    engine = RulesEngine(mock_db, filter_tree)
    modified = engine.apply_rules_to_entity(doc, rules=[rule])

    # Already present — no change
    assert modified is False
    assert doc.semantic_data.workflows["invoice_flow"].current_step == "PAID"
