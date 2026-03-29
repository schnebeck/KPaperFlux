"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_workflow_engine.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for WorkflowEngine — evaluate_transition(),
                can_transition(), get_next_state(), get_auto_transition(),
                and process_auto_transitions().

                Tests cover:
                  - All six condition operators (>, <, >=, <=, =, !=)
                  - Numeric vs. string comparison paths
                  - required_fields enforcement
                  - Missing / None field values
                  - Non-numeric values with non-equality operators → False
                  - Combined required_fields + conditions
                  - get_next_state() happy path and ValueError on bad action
                  - Auto-transition chaining and max_depth guard
------------------------------------------------------------------------------
"""
import pytest

from core.workflow import (
    WorkflowEngine,
    WorkflowRule,
    WorkflowState,
    WorkflowTransition,
    WorkflowCondition,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rule(*transitions: WorkflowTransition) -> WorkflowRule:
    """Minimal rule with a single START state and an END state."""
    return WorkflowRule(
        id="test",
        states={
            "START": WorkflowState(label="Start", transitions=list(transitions)),
            "END":   WorkflowState(label="End", final=True),
        },
    )


def _trans(
    action: str = "go",
    target: str = "END",
    auto: bool = False,
    required_fields: list[str] | None = None,
    conditions: list[WorkflowCondition] | None = None,
) -> WorkflowTransition:
    return WorkflowTransition(
        action=action,
        target=target,
        auto=auto,
        required_fields=required_fields or [],
        conditions=conditions or [],
    )


def _cond(field: str, op: str, value: float | str) -> WorkflowCondition:
    return WorkflowCondition(field=field, op=op, value=value)


# ---------------------------------------------------------------------------
# evaluate_transition — no conditions, no required_fields
# ---------------------------------------------------------------------------

class TestEvaluateTransitionUnrestricted:

    def test_always_true_when_no_conditions(self):
        engine = WorkflowEngine(_rule(_trans()))
        assert engine.evaluate_transition(_trans(), {}) is True

    def test_always_true_with_arbitrary_extra_data(self):
        engine = WorkflowEngine(_rule(_trans()))
        assert engine.evaluate_transition(_trans(), {"foo": 42, "bar": "x"}) is True


# ---------------------------------------------------------------------------
# evaluate_transition — required_fields
# ---------------------------------------------------------------------------

class TestRequiredFields:

    def test_present_field_passes(self):
        t = _trans(required_fields=["iban"])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"iban": "DE123"}) is True

    def test_missing_field_fails(self):
        t = _trans(required_fields=["iban"])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {}) is False

    def test_none_value_fails(self):
        t = _trans(required_fields=["iban"])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"iban": None}) is False

    def test_multiple_fields_all_present_passes(self):
        t = _trans(required_fields=["iban", "total_gross"])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"iban": "DE1", "total_gross": 100.0}) is True

    def test_multiple_fields_one_missing_fails(self):
        t = _trans(required_fields=["iban", "total_gross"])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"iban": "DE1"}) is False


# ---------------------------------------------------------------------------
# evaluate_transition — numeric conditions
# ---------------------------------------------------------------------------

class TestNumericConditions:

    def test_greater_than_passes(self):
        t = _trans(conditions=[_cond("DAYS_IN_STATE", ">", 10)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"DAYS_IN_STATE": 11}) is True

    def test_greater_than_equal_fails(self):
        t = _trans(conditions=[_cond("DAYS_IN_STATE", ">", 10)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"DAYS_IN_STATE": 10}) is False

    def test_less_than_passes(self):
        t = _trans(conditions=[_cond("total_gross", "<", 500)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"total_gross": 499.99}) is True

    def test_less_than_equal_fails(self):
        t = _trans(conditions=[_cond("total_gross", "<", 500)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"total_gross": 500.0}) is False

    def test_greater_equal_boundary(self):
        t = _trans(conditions=[_cond("AGE_DAYS", ">=", 30)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"AGE_DAYS": 30}) is True
        assert engine.evaluate_transition(t, {"AGE_DAYS": 29}) is False

    def test_less_equal_boundary(self):
        t = _trans(conditions=[_cond("total_gross", "<=", 100)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"total_gross": 100}) is True
        assert engine.evaluate_transition(t, {"total_gross": 101}) is False

    def test_equals_numeric_passes(self):
        t = _trans(conditions=[_cond("page_count", "=", 1)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"page_count": 1}) is True

    def test_equals_numeric_fails(self):
        t = _trans(conditions=[_cond("page_count", "=", 1)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"page_count": 2}) is False

    def test_not_equals_numeric_passes(self):
        t = _trans(conditions=[_cond("page_count", "!=", 0)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"page_count": 5}) is True

    def test_not_equals_numeric_fails(self):
        t = _trans(conditions=[_cond("page_count", "!=", 0)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"page_count": 0}) is False

    def test_string_numeric_value_is_coerced(self):
        """Values stored as strings (e.g. from JSON) should still compare numerically."""
        t = _trans(conditions=[_cond("DAYS_IN_STATE", ">", 10)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"DAYS_IN_STATE": "15"}) is True

    def test_multiple_conditions_all_must_pass(self):
        t = _trans(conditions=[
            _cond("DAYS_IN_STATE", ">", 5),
            _cond("total_gross", ">=", 100),
        ])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"DAYS_IN_STATE": 10, "total_gross": 200}) is True
        assert engine.evaluate_transition(t, {"DAYS_IN_STATE": 10, "total_gross": 50}) is False
        assert engine.evaluate_transition(t, {"DAYS_IN_STATE": 3, "total_gross": 200}) is False


# ---------------------------------------------------------------------------
# evaluate_transition — string conditions
# ---------------------------------------------------------------------------

class TestStringConditions:

    def test_equals_string_passes(self):
        t = _trans(conditions=[_cond("direction", "=", "INCOMING")])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"direction": "INCOMING"}) is True

    def test_equals_string_fails(self):
        t = _trans(conditions=[_cond("direction", "=", "INCOMING")])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"direction": "OUTGOING"}) is False

    def test_not_equals_string_passes(self):
        t = _trans(conditions=[_cond("effective_type", "!=", "UNKNOWN")])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"effective_type": "INVOICE"}) is True

    def test_not_equals_string_fails(self):
        t = _trans(conditions=[_cond("effective_type", "!=", "UNKNOWN")])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"effective_type": "UNKNOWN"}) is False

    def test_gt_on_non_numeric_returns_false(self):
        """Non-numeric values with ordering operators must return False, not raise."""
        t = _trans(conditions=[_cond("sender_name", ">", "A")])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"sender_name": "Zalando"}) is False

    def test_lt_on_non_numeric_returns_false(self):
        t = _trans(conditions=[_cond("sender_name", "<", "Z")])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"sender_name": "Amazon"}) is False


# ---------------------------------------------------------------------------
# evaluate_transition — missing / None field in condition
# ---------------------------------------------------------------------------

class TestMissingConditionField:

    def test_missing_field_returns_false(self):
        t = _trans(conditions=[_cond("DAYS_IN_STATE", ">", 10)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {}) is False

    def test_none_field_returns_false(self):
        t = _trans(conditions=[_cond("DAYS_IN_STATE", ">", 10)])
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"DAYS_IN_STATE": None}) is False


# ---------------------------------------------------------------------------
# evaluate_transition — combined required_fields + conditions
# ---------------------------------------------------------------------------

class TestCombinedRequiredAndConditions:

    def test_required_and_condition_both_satisfied(self):
        t = _trans(
            required_fields=["iban"],
            conditions=[_cond("total_gross", ">", 0)],
        )
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"iban": "DE1", "total_gross": 50}) is True

    def test_required_missing_blocks_even_if_condition_passes(self):
        t = _trans(
            required_fields=["iban"],
            conditions=[_cond("total_gross", ">", 0)],
        )
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"total_gross": 50}) is False

    def test_condition_fails_blocks_even_if_required_present(self):
        t = _trans(
            required_fields=["iban"],
            conditions=[_cond("total_gross", ">", 100)],
        )
        engine = WorkflowEngine(_rule(t))
        assert engine.evaluate_transition(t, {"iban": "DE1", "total_gross": 50}) is False


# ---------------------------------------------------------------------------
# can_transition
# ---------------------------------------------------------------------------

class TestCanTransition:

    def test_can_transition_true(self):
        rule = _rule(_trans("approve"))
        engine = WorkflowEngine(rule)
        assert engine.can_transition("START", "approve", {}) is True

    def test_can_transition_false_wrong_action(self):
        rule = _rule(_trans("approve"))
        engine = WorkflowEngine(rule)
        assert engine.can_transition("START", "reject", {}) is False

    def test_can_transition_false_unknown_state(self):
        rule = _rule(_trans("approve"))
        engine = WorkflowEngine(rule)
        assert engine.can_transition("NONEXISTENT", "approve", {}) is False

    def test_can_transition_blocked_by_condition(self):
        rule = _rule(_trans("pay", conditions=[_cond("total_gross", ">", 0)]))
        engine = WorkflowEngine(rule)
        assert engine.can_transition("START", "pay", {"total_gross": 0}) is False
        assert engine.can_transition("START", "pay", {"total_gross": 1}) is True


# ---------------------------------------------------------------------------
# get_next_state
# ---------------------------------------------------------------------------

class TestGetNextState:

    def test_returns_target_on_success(self):
        rule = _rule(_trans("go", target="END"))
        engine = WorkflowEngine(rule)
        assert engine.get_next_state("START", "go", {}) == "END"

    def test_raises_on_unknown_action(self):
        rule = _rule(_trans("go"))
        engine = WorkflowEngine(rule)
        with pytest.raises(ValueError, match="nonexistent"):
            engine.get_next_state("START", "nonexistent", {})

    def test_raises_on_unknown_state(self):
        rule = _rule(_trans("go"))
        engine = WorkflowEngine(rule)
        with pytest.raises(ValueError, match="GHOST"):
            engine.get_next_state("GHOST", "go", {})

    def test_raises_when_condition_not_met(self):
        rule = _rule(_trans("pay", conditions=[_cond("total_gross", ">", 100)]))
        engine = WorkflowEngine(rule)
        with pytest.raises(ValueError):
            engine.get_next_state("START", "pay", {"total_gross": 0})

    def test_no_data_skips_condition_check(self):
        """get_next_state with data=None bypasses evaluate_transition."""
        rule = _rule(_trans("go", conditions=[_cond("total_gross", ">", 999)]))
        engine = WorkflowEngine(rule)
        # data=None → condition is not evaluated → transition is taken
        assert engine.get_next_state("START", "go", None) == "END"


# ---------------------------------------------------------------------------
# get_auto_transition / process_auto_transitions
# ---------------------------------------------------------------------------

class TestAutoTransitions:

    def _chained_rule(self) -> WorkflowRule:
        """A → B → C, both auto-transitions; B→C guarded by a condition."""
        return WorkflowRule(
            id="chain",
            states={
                "A": WorkflowState(transitions=[
                    WorkflowTransition(action="a_to_b", target="B", auto=True),
                ]),
                "B": WorkflowState(transitions=[
                    WorkflowTransition(
                        action="b_to_c", target="C", auto=True,
                        conditions=[WorkflowCondition(field="flag", op="=", value="yes")],
                    ),
                ]),
                "C": WorkflowState(final=True),
            },
        )

    def test_get_auto_transition_returns_target(self):
        rule = _rule(_trans("go", auto=True))
        engine = WorkflowEngine(rule)
        assert engine.get_auto_transition("START", {}) == "END"

    def test_get_auto_transition_returns_none_when_blocked(self):
        rule = _rule(_trans("go", auto=True, conditions=[_cond("flag", "=", "yes")]))
        engine = WorkflowEngine(rule)
        assert engine.get_auto_transition("START", {"flag": "no"}) is None

    def test_get_auto_transition_returns_none_for_manual_transition(self):
        rule = _rule(_trans("go", auto=False))
        engine = WorkflowEngine(rule)
        assert engine.get_auto_transition("START", {}) is None

    def test_process_auto_transitions_chains(self):
        rule = self._chained_rule()
        engine = WorkflowEngine(rule)
        result = engine.process_auto_transitions("A", {"flag": "yes"})
        assert result == "C"

    def test_process_auto_transitions_stops_when_condition_fails(self):
        rule = self._chained_rule()
        engine = WorkflowEngine(rule)
        result = engine.process_auto_transitions("A", {"flag": "no"})
        assert result == "B"

    def test_process_auto_transitions_max_depth_guard(self):
        """A self-loop auto-transition must not run forever."""
        rule = WorkflowRule(
            id="loop",
            states={
                "LOOP": WorkflowState(transitions=[
                    WorkflowTransition(action="again", target="LOOP", auto=True),
                ]),
            },
        )
        engine = WorkflowEngine(rule)
        result = engine.process_auto_transitions("LOOP", {}, max_depth=5)
        assert result == "LOOP"
