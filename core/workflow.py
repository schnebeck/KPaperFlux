"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/workflow.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Workflow data models, engine, registry, and locale-aware
                label resolution.  Workflow rules are user-defined and stored
                in the creator's language; the l10n dict holds per-locale
                patches for name, description, and state labels.
------------------------------------------------------------------------------
"""

import json
import locale as _locale_mod
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Module-level locale state
# ---------------------------------------------------------------------------

_user_locale: str = ""
_DEFAULT_FALLBACK_LOCALE: str = "en"


def set_user_locale(locale_code: str) -> None:
    """Set the display locale used for workflow label resolution.

    Call once at application startup with the active UI language code
    (e.g. ``"de"``, ``"fr"``).  Accepts full locale strings like ``"de_DE"``
    and strips to the two-letter language code automatically.
    """
    global _user_locale
    _user_locale = locale_code.split("_")[0].lower() if locale_code else ""


def get_user_locale() -> str:
    """Return the active display locale for workflow labels.

    Falls back to the OS locale, then to ``"en"`` if nothing is configured.
    """
    if _user_locale:
        return _user_locale
    try:
        loc = _locale_mod.getlocale()[0] or "en"
        return loc.split("_")[0].lower()
    except Exception:
        return "en"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class WorkflowCondition(BaseModel):
    """Specific logical condition for a transition."""
    field: str
    op: str  # >, <, >=, <=, =, !=
    value: Any


def make_state_id() -> str:
    """Return a short opaque ID for a newly created workflow state."""
    return f"s_{uuid4().hex[:8]}"


def make_action_id() -> str:
    """Return a short opaque ID for a newly created workflow transition action."""
    return f"t_{uuid4().hex[:8]}"


class WorkflowTransition(BaseModel):
    action: str
    """Stable internal identifier — auto-generated for new transitions, preserved forever."""
    label: str = ""
    """User-visible button / arrow text.  Falls back to *action* when empty."""
    target: str
    required_fields: List[str] = Field(default_factory=list)
    conditions: List[WorkflowCondition] = Field(default_factory=list)
    user_interaction: bool = False
    auto: bool = False
    icon: Optional[str] = None


class WorkflowState(BaseModel):
    label: str = ""
    transitions: List[WorkflowTransition] = Field(default_factory=list)
    final: bool = False


class WorkflowL10nPatch(BaseModel):
    """Partial localization override for a WorkflowRule in one locale.

    Only the fields the translator wants to override need to be provided;
    anything left empty falls back to the rule's native (creator) values.
    """
    name: str = ""
    description: str = ""
    states: Dict[str, str] = Field(default_factory=dict)   # state_id  → label
    actions: Dict[str, str] = Field(default_factory=dict)  # action_id → label


class WorkflowRule(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    creator_locale: str = ""
    """ISO 639-1 code of the language in which name/description/labels were
    originally written.  Empty means unknown (native fields are used as-is)."""
    l10n: Dict[str, WorkflowL10nPatch] = Field(default_factory=dict)
    """Per-locale overrides.  Key = ISO 639-1 code (e.g. ``"fr"``).
    Only fields that differ from the creator locale need to be set."""
    states: Dict[str, WorkflowState] = Field(default_factory=dict)
    triggers: Dict[str, List[Any]] = Field(default_factory=dict)
    node_positions: Dict[str, List[float]] = Field(default_factory=dict)
    """Manual node positions [x, y] set by the user in the graph editor.
    When present for a state, overrides the auto-layout algorithm."""
    transition_anchors: Dict[str, List[str]] = Field(default_factory=dict)
    """Custom anchor points per transition.  Key: ``'src_state_id:action'``.
    Value: ``[src_anchor, tgt_anchor]`` e.g. ``['right', 'bottom-left']``."""
    transition_bends: Dict[str, List[float]] = Field(default_factory=dict)
    """Midpoint displacement [dx, dy] applied to the bezier curve of a transition.
    Key: ``'src_state_id:action'``.  Stored only when non-zero."""

    # ── Locale resolution ─────────────────────────────────────────────────

    def _best_locale(self, requested: str = "") -> str:
        """Return the best available l10n key for *requested* locale.

        Resolution order:
          1. ``requested`` locale (if present in l10n)
          2. ``"en"`` fallback (if present and different from requested)
          3. ``""`` — use native creator fields
        """
        locale = (requested or get_user_locale()).lower()
        if locale in self.l10n:
            return locale
        if (
            _DEFAULT_FALLBACK_LOCALE in self.l10n
            and locale != _DEFAULT_FALLBACK_LOCALE
        ):
            return _DEFAULT_FALLBACK_LOCALE
        return ""

    def get_display_name(self, locale: str = "") -> str:
        """Return the rule name in the best available locale."""
        loc = self._best_locale(locale)
        if loc and self.l10n[loc].name:
            return self.l10n[loc].name
        return self.name

    def get_description(self, locale: str = "") -> str:
        """Return the rule description in the best available locale."""
        loc = self._best_locale(locale)
        if loc and self.l10n[loc].description:
            return self.l10n[loc].description
        return self.description

    def get_action_label(self, action_id: str, locale: str = "") -> str:
        """Return the display label for an action in the best available locale.

        Resolution order: l10n patch → transition's own label → action_id.
        """
        loc = self._best_locale(locale)
        if loc and action_id in self.l10n[loc].actions:
            return self.l10n[loc].actions[action_id]
        for state in self.states.values():
            for t in state.transitions:
                if t.action == action_id:
                    return t.label if t.label else action_id
        return action_id

    def get_state_label(self, step: str, locale: str = "") -> str:
        """Return the display label for *step* in the best available locale.

        Falls back through: locale patch → English patch → creator label → state ID.
        """
        loc = self._best_locale(locale)
        if loc and step in self.l10n[loc].states:
            return self.l10n[loc].states[step]
        state_def = self.states.get(step)
        return state_def.label if (state_def and state_def.label) else step


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class WorkflowEngine:
    def __init__(self, rule: WorkflowRule):
        self.rule = rule

    def get_next_state(
        self, current_state: str, action: str, data: Optional[Dict[str, Any]] = None
    ) -> str:
        state = self.rule.states.get(current_state)
        if not state:
            raise ValueError(
                f"State {current_state} not found in rule {self.rule.id}"
            )
        for trans in state.transitions:
            if trans.action == action:
                if data is None or self.evaluate_transition(trans, data):
                    return trans.target
        raise ValueError(
            f"Action {action} not allowed/applicable in state {current_state}"
        )

    def can_transition(
        self, current_state: str, action: str, data: Dict[str, Any]
    ) -> bool:
        state = self.rule.states.get(current_state)
        if not state:
            return False
        for trans in state.transitions:
            if trans.action == action:
                if self.evaluate_transition(trans, data):
                    return True
        return False

    def get_auto_transition(
        self, current_state: str, data: Dict[str, Any]
    ) -> Optional[str]:
        """Return the target of the first applicable auto-transition, or None."""
        state = self.rule.states.get(current_state)
        if not state:
            return None
        for trans in state.transitions:
            if trans.auto:
                if self.evaluate_transition(trans, data):
                    return trans.target
        return None

    def process_auto_transitions(
        self, start_state: str, data: Dict[str, Any], max_depth: int = 10
    ) -> str:
        """Follow auto-transitions until none match or max_depth is reached."""
        current = start_state
        for _ in range(max_depth):
            nxt = self.get_auto_transition(current, data)
            if not nxt or nxt == current:
                break
            current = nxt
        return current

    def evaluate_transition(
        self, transition: WorkflowTransition, data: Dict[str, Any]
    ) -> bool:
        for field in transition.required_fields:
            if field not in data or data[field] is None:
                return False
        for cond in transition.conditions:
            val = data.get(cond.field)
            if val is None:
                return False
            try:
                fval, fcond = float(val), float(cond.value)
                if cond.op == ">" and not (fval > fcond):
                    return False
                elif cond.op == "<" and not (fval < fcond):
                    return False
                elif cond.op == ">=" and not (fval >= fcond):
                    return False
                elif cond.op == "<=" and not (fval <= fcond):
                    return False
                elif cond.op == "=" and str(val) != str(cond.value):
                    return False
                elif cond.op == "!=" and str(val) == str(cond.value):
                    return False
            except (ValueError, TypeError):
                if cond.op == "=":
                    if str(val) != str(cond.value):
                        return False
                else:
                    return False
        return True


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

from core.logger import get_logger
logger = get_logger("core.workflow")


class WorkflowRuleRegistry:
    """Singleton registry for managing document workflow rules."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.rules = {}
        return cls._instance

    def load_from_directory(self, path: str) -> None:
        """Load all .json files from *path* as WorkflowRule objects."""
        self.rules.clear()
        if not Path(path).exists():
            logger.warning(f"Workflow directory not found: {path}")
            return
        for entry in Path(path).iterdir():
            if entry.suffix == ".json":
                try:
                    with open(entry, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    rule = WorkflowRule(**data)
                    self.rules[rule.id] = rule
                    logger.info(f"Loaded workflow rule: {rule.id}")
                except Exception as e:
                    logger.error(f"Failed to load rule from {entry}: {e}")

    def get_rule(self, rule_id: str) -> Optional[WorkflowRule]:
        return self.rules.get(rule_id)

    def find_rules_for_tags(self, tags: List[str]) -> List[WorkflowRule]:
        """Return all rules whose type_tag triggers match any of *tags*."""
        return [
            rule for rule in self.rules.values()
            if any(t in tags for t in rule.triggers.get("type_tags", []))
        ]

    def find_rule_for_tags(self, tags: List[str]) -> Optional[WorkflowRule]:
        """Deprecated: returns only the first matching rule."""
        matches = self.find_rules_for_tags(tags)
        return matches[0] if matches else None

    def list_rules(self) -> List[WorkflowRule]:
        return list(self.rules.values())

    def get_all_steps(self) -> List[str]:
        """Return all unique state IDs across all loaded rules."""
        steps: set[str] = set()
        for rule in self.rules.values():
            steps.update(rule.states.keys())
        return sorted(steps)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_initial_state(rule: WorkflowRule) -> Optional[str]:
    """Return the state ID with no incoming transitions (= starting state).

    Falls back to the first key in ``rule.states`` when every state is
    targeted (cycle-only graph — unlikely in practice).
    """
    if not rule.states:
        return None
    targeted: set[str] = {
        t.target for s in rule.states.values() for t in s.transitions
    }
    candidates = [sid for sid in rule.states if sid not in targeted]
    return candidates[0] if candidates else next(iter(rule.states))


def completion_percent(wf_info: Any, rule: WorkflowRule) -> int:
    """Return 0–100 progress for a workflow instance.

    A final state always returns 100.  All other states return at most 99,
    calculated from visited states vs. total states in the rule.
    """
    state = rule.states.get(wf_info.current_step)
    if state and state.final:
        return 100
    total = len(rule.states)
    if not total:
        return 0
    visited = len(wf_info.history) + 1
    return min(99, round(visited / total * 100))
