
import pytest
from core.workflow import WorkflowEngine, WorkflowRule

def test_load_rule():
    rule_data = {
        "id": "test_flow",
        "states": {
            "NEW": {
                "label": "Start",
                "transitions": [
                    {"action": "advance", "target": "STEP_2"}
                ]
            },
            "STEP_2": {
                "label": "End",
                "final": True
            }
        }
    }
    rule = WorkflowRule(**rule_data)
    assert rule.id == "test_flow"
    assert "NEW" in rule.states

def test_engine_transition():
    rule_data = {
        "id": "test_flow",
        "states": {
            "NEW": {
                "label": "Start",
                "transitions": [
                    {"action": "proceed", "target": "DONE"}
                ]
            },
            "DONE": {"label": "Done", "final": True}
        }
    }
    rule = WorkflowRule(**rule_data)
    engine = WorkflowEngine(rule)
    
    # Valid transition
    next_state = engine.get_next_state("NEW", "proceed")
    assert next_state == "DONE"
    
    # Invalid transition
    with pytest.raises(ValueError):
        engine.get_next_state("NEW", "invalid_action")

def test_requirements_check():
    rule_data = {
        "id": "req_flow",
        "states": {
            "NEW": {
                "transitions": [
                    {
                        "action": "check",
                        "target": "OK",
                        "required_fields": ["iban", "amount"]
                    }
                ]
            },
            "OK": {"final": True}
        }
    }
    rule = WorkflowRule(**rule_data)
    engine = WorkflowEngine(rule)
    
    # Missing data
    data = {"iban": "DE123"}
    assert engine.can_transition("NEW", "check", data) is False
    
    # Complete data
    data = {"iban": "DE123", "amount": 100.0}
    assert engine.can_transition("NEW", "check", data) is True

def test_semantic_integration():
    from core.models.semantic import SemanticExtraction, FinanceBody, MonetarySummation, WorkflowInfo

    rule_data = {
        "id": "pay_flow",
        "states": {
            "NEW": {
                "transitions": [{"action": "verify", "target": "PAID", "required_fields": ["monetary_summation.grand_total_amount"]}]
            },
            "PAID": {"final": True}
        }
    }
    rule = WorkflowRule(**rule_data)
    engine = WorkflowEngine(rule)

    # 1. Setup Document with workflow in the dict
    sem = SemanticExtraction()
    sem.bodies["finance_body"] = FinanceBody(
        monetary_summation=MonetarySummation(grand_total_amount=50.0)
    )
    sem.workflows["pay_flow"] = WorkflowInfo(rule_id="pay_flow", current_step="NEW")

    # 2. Check if transition is possible
    val = sem.get_financial_value("monetary_summation.grand_total_amount")
    data_for_check = {"monetary_summation.grand_total_amount": val}

    wf = sem.workflows["pay_flow"]
    if engine.can_transition(wf.current_step, "verify", data_for_check):
        next_s = engine.get_next_state(wf.current_step, "verify")
        wf.apply_transition("verify", next_s, user="TEST_BOT")

    assert sem.workflows["pay_flow"].current_step == "PAID"
    assert "TRANSITION: verify" in sem.workflows["pay_flow"].history[-1].action

def test_registry_loading():
    from core.workflow import WorkflowRuleRegistry
    import os
    
    registry = WorkflowRuleRegistry()
    registry.load_from_directory("resources/workflows")
    
    rule = registry.get_rule("invoice_standard")
    assert rule is not None
    assert rule.id == "invoice_standard"
    
    # Check trigger find (multi-rule)
    found_list = registry.find_rules_for_tags(["INVOICE", "URGENT"])
    assert len(found_list) >= 1
    assert any(r.id == "invoice_standard" for r in found_list)
