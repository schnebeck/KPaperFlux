import pytest
from core.workflow import WorkflowEngine, WorkflowRule, WorkflowState, WorkflowTransition, WorkflowCondition

def test_basic_transition():
    rule = WorkflowRule(
        id="test_rule",
        states={
            "NEW": WorkflowState(label="New", transitions=[
                WorkflowTransition(action="verify", target="DONE")
            ]),
            "DONE": WorkflowState(label="Done", final=True)
        }
    )
    engine = WorkflowEngine(rule)
    
    assert engine.get_next_state("NEW", "verify") == "DONE"
    with pytest.raises(ValueError):
        engine.get_next_state("NEW", "non_existent")

def test_conditions_logic():
    rule = WorkflowRule(
        id="cond_rule",
        states={
            "NEW": WorkflowState(label="New", transitions=[
                WorkflowTransition(
                    action="approve", 
                    target="HIGH_VALUE",
                    conditions=[WorkflowCondition(field="total_gross", op=">", value=1000)]
                ),
                WorkflowTransition(
                    action="approve", 
                    target="LOW_VALUE",
                    conditions=[WorkflowCondition(field="total_gross", op="<=", value=1000)]
                )
            ])
        }
    )
    engine = WorkflowEngine(rule)
    
    # High Value
    assert engine.can_transition("NEW", "approve", {"total_gross": 1500}) is True
    assert engine.get_next_state("NEW", "approve", {"total_gross": 1500}) == "HIGH_VALUE"

    # Low Value
    assert engine.can_transition("NEW", "approve", {"total_gross": 500}) is True
    assert engine.get_next_state("NEW", "approve", {"total_gross": 500}) == "LOW_VALUE"
    
    # No match
    with pytest.raises(ValueError):
        engine.get_next_state("NEW", "approve", {"total_gross": None})
    
def test_auto_transitions():
    """
    Test that the engine can automatically skip states if conditions are met.
    """
    rule = WorkflowRule(
        id="auto_rule",
        states={
            "NEW": WorkflowState(label="New", transitions=[
                # Auto-transition to URGENT if value > 5000
                WorkflowTransition(
                    action="auto_check", 
                    target="URGENT", 
                    auto=True,
                    conditions=[WorkflowCondition(field="total_gross", op=">", value=5000)]
                ),
                # Otherwise manual transition
                WorkflowTransition(action="process", target="PROCESSING")
            ]),
            "URGENT": WorkflowState(label="Urgent", transitions=[
                WorkflowTransition(action="process", target="PROCESSING")
            ]),
            "PROCESSING": WorkflowState(label="Processing")
        }
    )
    engine = WorkflowEngine(rule)
    
    # If total_gross is 6000, it should auto-transition to URGENT
    next_state = engine.get_auto_transition("NEW", {"total_gross": 6000})
    assert next_state == "URGENT"
    
    # If total_gross is 1000, no auto-transition
    next_state = engine.get_auto_transition("NEW", {"total_gross": 1000})
    assert next_state is None

def test_auto_transition_chain():
    """
    Test that auto-transitions can be chained.
    NEW -> (auto) -> VALIDATED -> (auto) -> ARCHIVED
    """
    rule = WorkflowRule(
        id="chain_rule",
        states={
            "NEW": WorkflowState(transitions=[
                WorkflowTransition(action="a1", target="VALIDATED", auto=True)
            ]),
            "VALIDATED": WorkflowState(transitions=[
                WorkflowTransition(action="a2", target="ARCHIVED", auto=True, 
                                   conditions=[WorkflowCondition(field="flag", op="=", value="true")])
            ]),
            "ARCHIVED": WorkflowState(final=True)
        }
    )
    engine = WorkflowEngine(rule)
    
    # Should skip all the way to ARCHIVED
    final_state = engine.process_auto_transitions("NEW", {"flag": "true"})
    assert final_state == "ARCHIVED"
    
    # Should stop at VALIDATED
    final_state = engine.process_auto_transitions("NEW", {"flag": "false"})
    assert final_state == "VALIDATED"
