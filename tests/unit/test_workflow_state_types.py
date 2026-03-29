"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_workflow_state_types.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for StateType enum, WorkflowState.is_terminal /
                is_start properties, entered_at timestamp tracking, and the
                updated get_initial_state() / completion_percent() helpers.
------------------------------------------------------------------------------
"""
import pytest
from datetime import datetime, timedelta

from core.workflow import (
    StateType,
    WorkflowRule,
    WorkflowState,
    WorkflowEngine,
    get_initial_state,
    completion_percent,
)
from core.models.semantic import WorkflowInfo


# ---------------------------------------------------------------------------
# StateType — enum membership
# ---------------------------------------------------------------------------

class TestStateTypeEnum:

    def test_all_five_variants_exist(self):
        assert StateType.START
        assert StateType.NORMAL
        assert StateType.END_OK
        assert StateType.END_NOK
        assert StateType.END_NEUTRAL

    def test_values_are_strings(self):
        assert StateType.END_OK == "END_OK"
        assert StateType.START == "START"

    def test_roundtrip_from_string(self):
        assert StateType("END_NOK") == StateType.END_NOK


# ---------------------------------------------------------------------------
# WorkflowState.is_terminal
# ---------------------------------------------------------------------------

class TestIsTerminal:

    def test_end_ok_is_terminal(self):
        s = WorkflowState(state_type=StateType.END_OK)
        assert s.is_terminal is True

    def test_end_nok_is_terminal(self):
        s = WorkflowState(state_type=StateType.END_NOK)
        assert s.is_terminal is True

    def test_end_neutral_is_terminal(self):
        s = WorkflowState(state_type=StateType.END_NEUTRAL)
        assert s.is_terminal is True

    def test_normal_is_not_terminal(self):
        s = WorkflowState(state_type=StateType.NORMAL)
        assert s.is_terminal is False

    def test_start_is_not_terminal(self):
        s = WorkflowState(state_type=StateType.START)
        assert s.is_terminal is False

    def test_legacy_final_flag_still_makes_is_terminal_true(self):
        """Backwards compat: rules without state_type but with final=True."""
        s = WorkflowState(final=True)  # no state_type set
        assert s.is_terminal is True

    def test_default_state_type_is_normal(self):
        s = WorkflowState()
        assert s.state_type == StateType.NORMAL


# ---------------------------------------------------------------------------
# WorkflowState.is_start
# ---------------------------------------------------------------------------

class TestIsStart:

    def test_start_type_is_start(self):
        s = WorkflowState(state_type=StateType.START)
        assert s.is_start is True

    def test_normal_is_not_start(self):
        s = WorkflowState(state_type=StateType.NORMAL)
        assert s.is_start is False

    def test_legacy_initial_flag(self):
        """Backwards compat: rules without state_type but with initial=True."""
        s = WorkflowState(initial=True)
        assert s.is_start is True


# ---------------------------------------------------------------------------
# get_initial_state — START type preferred over topology heuristic
# ---------------------------------------------------------------------------

class TestGetInitialState:

    def _make_rule(self, states: dict) -> WorkflowRule:
        return WorkflowRule(id="test", states=states)

    def test_start_type_wins_over_topology(self):
        rule = self._make_rule({
            "A": {"state_type": "START", "transitions": [{"action": "go", "target": "B"}]},
            "B": {"state_type": "END_OK"},
        })
        assert get_initial_state(rule) == "A"

    def test_legacy_initial_flag_still_works(self):
        rule = self._make_rule({
            "FIRST": {"initial": True, "transitions": [{"action": "go", "target": "LAST"}]},
            "LAST": {"final": True},
        })
        assert get_initial_state(rule) == "FIRST"

    def test_topology_fallback_when_no_marker(self):
        rule = self._make_rule({
            "ROOT": {"transitions": [{"action": "go", "target": "LEAF"}]},
            "LEAF": {},
        })
        assert get_initial_state(rule) == "ROOT"

    def test_empty_rule_returns_none(self):
        rule = self._make_rule({})
        assert get_initial_state(rule) is None


# ---------------------------------------------------------------------------
# completion_percent — uses is_terminal
# ---------------------------------------------------------------------------

class TestCompletionPercent:

    def _make_rule_and_info(self, state_type_str: str) -> tuple:
        rule = WorkflowRule(id="x", states={
            "START": {"state_type": "START", "transitions": [{"action": "go", "target": "END"}]},
            "END": {"state_type": state_type_str},
        })
        info = WorkflowInfo(rule_id="x", current_step="END")
        return rule, info

    def test_end_ok_returns_100(self):
        rule, info = self._make_rule_and_info("END_OK")
        assert completion_percent(info, rule) == 100

    def test_end_nok_returns_100(self):
        rule, info = self._make_rule_and_info("END_NOK")
        assert completion_percent(info, rule) == 100

    def test_end_neutral_returns_100(self):
        rule, info = self._make_rule_and_info("END_NEUTRAL")
        assert completion_percent(info, rule) == 100

    def test_normal_state_returns_less_than_100(self):
        rule = WorkflowRule(id="x", states={
            "START": {"state_type": "START", "transitions": [{"action": "go", "target": "END"}]},
            "END": {"state_type": "END_OK"},
        })
        info = WorkflowInfo(rule_id="x", current_step="START")
        assert completion_percent(info, rule) < 100


# ---------------------------------------------------------------------------
# WorkflowInfo.current_step_entered_at — timestamp tracking
# ---------------------------------------------------------------------------

class TestCurrentStepEnteredAt:

    def test_entered_at_none_initially(self):
        info = WorkflowInfo(rule_id="r", current_step="NEW")
        assert info.current_step_entered_at is None

    def test_apply_transition_sets_entered_at(self):
        info = WorkflowInfo(rule_id="r", current_step="NEW")
        before = datetime.now()
        info.apply_transition("go", "DONE")
        after = datetime.now()
        assert info.current_step_entered_at is not None
        ts = datetime.fromisoformat(info.current_step_entered_at)
        assert before <= ts <= after

    def test_apply_transition_updates_entered_at_on_each_step(self):
        info = WorkflowInfo(rule_id="r", current_step="A")
        info.apply_transition("step1", "B")
        ts1 = info.current_step_entered_at
        info.apply_transition("step2", "C")
        ts2 = info.current_step_entered_at
        assert ts2 >= ts1

    def test_entered_at_is_iso_format(self):
        info = WorkflowInfo(rule_id="r", current_step="X")
        info.apply_transition("move", "Y")
        parsed = datetime.fromisoformat(info.current_step_entered_at)
        assert isinstance(parsed, datetime)

    def test_history_still_records_transition(self):
        info = WorkflowInfo(rule_id="r", current_step="A")
        info.apply_transition("action1", "B", user="TESTER", comment="unit test")
        assert len(info.history) == 1
        log = info.history[0]
        assert "action1" in log.action
        assert log.user == "TESTER"


# ---------------------------------------------------------------------------
# JSON round-trip — state_type persists through WorkflowRule serialisation
# ---------------------------------------------------------------------------

class TestStateTypeRoundTrip:

    def test_state_type_survives_model_dump_and_parse(self):
        rule = WorkflowRule(id="rt", states={
            "s1": {"state_type": "START", "label": "Begin"},
            "s2": {"state_type": "END_OK", "label": "Done", "final": True},
        })
        data = rule.model_dump(mode="json")
        rule2 = WorkflowRule(**data)
        assert rule2.states["s1"].state_type == StateType.START
        assert rule2.states["s2"].state_type == StateType.END_OK

    def test_missing_state_type_defaults_to_normal(self):
        """Existing rules without state_type key load cleanly."""
        rule = WorkflowRule(id="legacy", states={
            "NEW": {"label": "New", "initial": True, "transitions": [{"action": "go", "target": "DONE"}]},
            "DONE": {"label": "Done", "final": True},
        })
        assert rule.states["NEW"].state_type == StateType.NORMAL
        assert rule.states["DONE"].state_type == StateType.NORMAL
        # Legacy flags still work
        assert rule.states["NEW"].is_start is True
        assert rule.states["DONE"].is_terminal is True
