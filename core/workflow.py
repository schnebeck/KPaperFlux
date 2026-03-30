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
from enum import Enum
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
# Workflow field catalog
# ---------------------------------------------------------------------------

# Fields available in document_data when the workflow engine evaluates
# conditions and required_fields.  Each entry: (group_key, field_key, label).
# Labels are English source strings — translated in the GUI via tr().
WORKFLOW_FIELD_CATALOG: list[tuple[str, str, str]] = [
    # Finance / accounting
    ("finance", "total_gross",    "Gross Amount"),
    ("finance", "total_net",      "Net Amount"),
    ("finance", "total_tax",      "Tax Amount"),
    ("finance", "iban",           "IBAN"),
    ("finance", "bic",            "BIC"),
    ("finance", "currency",       "Currency"),
    ("finance", "order_number",   "Order Number"),
    ("finance", "customer_id",    "Customer ID"),
    ("finance", "payment_terms",  "Payment Terms"),
    # Document metadata
    ("document", "doc_date",       "Document Date"),
    ("document", "doc_number",     "Document Number"),
    ("document", "sender_name",    "Sender Name"),
    ("document", "recipient_name", "Recipient Name"),
    ("document", "direction",      "Direction"),
    ("document", "effective_type", "Document Type"),
    ("document", "pdf_class",      "PDF Class"),
    ("document", "ai_confidence",  "AI Confidence"),
    ("document", "page_count",     "Page Count"),
    # Contract / subscription
    ("contract", "termination_date",   "Termination Date"),
    ("contract", "valid_until",        "Valid Until"),
    ("contract", "service_period_end", "Service Period End"),
    ("contract", "is_recurring",       "Is Recurring"),
    ("contract", "frequency",          "Recurrence Frequency"),
    # Time-based computed values
    ("time", "AGE_DAYS",          "Document Age (days)"),
    ("time", "DAYS_IN_STATE",     "Days in Current State"),
    ("time", "DAYS_UNTIL_DUE",    "Days Until Due"),
    ("time", "DAYS_UNTIL_EXPIRY", "Days Until Expiry"),
]

WORKFLOW_FIELD_GROUPS: dict[str, str] = {
    "finance":  "Finance",
    "document": "Document",
    "contract": "Contract / Subscription",
    "time":     "Time-based",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class StateType(str, Enum):
    """Semantic classification of a workflow state.

    Every state in a rule must have exactly one type.  The type drives colour
    coding, terminal detection, and analytics queries — without relying on
    fragile label-string heuristics.

    ``START``       — entry point (at most one per rule).
    ``NORMAL``      — intermediate task / waiting state.
    ``END_OK``      — positive terminal (paid, approved, completed).
    ``END_NOK``     — negative terminal (rejected, written-off, escalated).
    ``END_NEUTRAL`` — neutral terminal (cancelled, archived without outcome).
    """

    START = "START"
    NORMAL = "NORMAL"
    END_OK = "END_OK"
    END_NOK = "END_NOK"
    END_NEUTRAL = "END_NEUTRAL"


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
    state_type: StateType = StateType.NORMAL
    """Semantic type of this state.  Drives colour coding, terminal detection,
    and analytics.  ``END_*`` types imply ``final=True``; ``START`` implies
    ``initial=True`` — those legacy flags are still honoured for rules that
    pre-date ``state_type``."""
    final: bool = False
    initial: bool = False
    """Explicit start-state marker.  At most one state per rule should be True.
    When present, ``get_initial_state()`` returns this state without falling back
    to topology detection.  Existing rules without this flag continue to work
    via the topology heuristic (state with no incoming transitions)."""

    @property
    def is_terminal(self) -> bool:
        """True for any state from which no further transitions are expected."""
        return self.state_type in (StateType.END_OK, StateType.END_NOK, StateType.END_NEUTRAL) or self.final

    @property
    def is_start(self) -> bool:
        """True if this is the designated entry point of the workflow."""
        return self.state_type == StateType.START or self.initial


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
                # Non-numeric fallback: only = and != make sense for strings
                if cond.op == "=":
                    if str(val) != str(cond.value):
                        return False
                elif cond.op == "!=":
                    if str(val) == str(cond.value):
                        return False
                else:
                    # Ordering operators on non-numeric values are undefined → block
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
    """Return the designated start-state ID for *rule*.

    Resolution order:
    1. Explicit ``initial=True`` marker on a state (preferred).
    2. Topology heuristic: state with no incoming transitions.
    3. First state in ``rule.states`` (cycle-only graph fallback).
    """
    if not rule.states:
        return None
    # 1. Explicit START type or initial marker
    for sid, state in rule.states.items():
        if state.is_start:
            return sid
    # 2. Topology: state that is not the target of any transition
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
    if state and state.is_terminal:
        return 100
    total = len(rule.states)
    if not total:
        return 0
    visited = len(wf_info.history) + 1
    return min(99, round(visited / total * 100))


def sanitize_documents_for_rule(
    db_manager: Any,
    rule: WorkflowRule,
    stale_only: bool = False,
) -> tuple[int, list[str]]:
    """Reset linked documents to the initial state of *rule*.

    ``stale_only=False`` (default, used on explicit rule save):
        Resets ALL documents whose ``current_step`` is not already the initial
        state — even if their state is still technically valid.  Use this when
        the rule structure changed and all in-progress journeys should restart.

    ``stale_only=True`` (used at startup / background sweep):
        Only resets documents whose ``current_step`` is no longer a valid state
        ID in *rule*.  Documents in the middle of a valid journey are not touched.

    Only documents using the current ``semantic_data.workflows`` (plural) structure
    are processed.  Documents still carrying the legacy ``semantic_data.workflow``
    (singular) key must be converted first via
    ``scripts/migrate_workflow_to_multi.py``.

    Returns ``(reset_count, affected_uuids)``.
    """
    from core.models.semantic import WorkflowLog  # local import to avoid cycles

    valid_states: set[str] = set(rule.states.keys())
    initial: str = get_initial_state(rule) or next(iter(rule.states), "NEW")

    query = {
        "field": f"semantic:workflows.{rule.id}.current_step",
        "op": "is_not_empty",
        "value": None,
    }
    try:
        docs = db_manager.search_documents_advanced(query)
    except Exception:
        return 0, []

    affected: list[str] = []
    for doc in docs:
        sd = getattr(doc, "semantic_data", None)
        if sd is None or not hasattr(sd, "workflows"):
            continue
        wf_info = sd.workflows.get(rule.id)
        if wf_info is None:
            continue
        step = wf_info.current_step
        if step == initial:
            continue  # already at start — never reset
        if stale_only and step in valid_states:
            continue  # valid in-progress step — leave untouched in stale_only mode
        wf_info.history.append(WorkflowLog(
            action=f"SYSTEM_RESET: '{step}' -> '{initial}'",
            user="SYSTEM",
            comment=(
                f"State '{step}' is no longer valid in rule '{rule.id}'; "
                f"reset to initial state."
            ) if stale_only else (
                f"Rule '{rule.id}' was updated; document reset to initial state."
            ),
        ))
        wf_info.current_step = initial
        try:
            db_manager.update_document_metadata(doc.uuid, {"semantic_data": sd})
            affected.append(doc.uuid)
        except Exception as exc:
            logger.error(f"sanitize_documents_for_rule: failed to save {doc.uuid}: {exc}")

    return len(affected), affected


def count_legacy_workflow_documents(db_manager: Any, rule_id: str) -> int:
    """Return the number of documents still using the legacy ``workflow`` (singular) key.

    A non-zero result means ``scripts/migrate_workflow_to_multi.py`` must be run
    before those documents are visible to ``sanitize_documents_for_rule``.
    """
    query = {
        "field": "semantic:workflow.rule_id",
        "op": "equals",
        "value": rule_id,
    }
    try:
        return db_manager.count_documents_advanced(query)
    except Exception:
        return 0


def build_workflow_data(doc: Any, days_in_state: int = 0) -> dict:
    """Build the ``document_data`` dict passed to :class:`WorkflowEngine`.

    Extracts all fields listed in :data:`WORKFLOW_FIELD_CATALOG` from a
    ``VirtualDocument`` instance.  Uses the document's computed properties
    (``doc.total_gross``, ``doc.iban``, etc.) which already handle the
    deep navigation into nested semantic bodies — so this function never
    reaches into raw nested dicts itself.

    Computed time-based values (``AGE_DAYS``, ``DAYS_IN_STATE``,
    ``DAYS_UNTIL_DUE``, ``DAYS_UNTIL_EXPIRY``) are derived on the fly.

    *doc* — a ``VirtualDocument`` instance.
    *days_in_state* — how many days the document has been in its current
    workflow state; pass 0 when the caller does not track this.
    """
    from datetime import date as _date

    sd = getattr(doc, "semantic_data", None)
    today = _date.today()

    def _prop(attr: str, default: Any = None) -> Any:
        """Read a property from doc (preferred) or fall back to sd."""
        val = getattr(doc, attr, None)
        if val is not None:
            return val
        return getattr(sd, attr, default) if sd is not None else default

    def _body(body_key: str, field: str, default: Any = None) -> Any:
        """Read a field from a named semantic body dict."""
        if sd is None:
            return default
        bodies = getattr(sd, "bodies", {})
        body = bodies.get(body_key)
        if body is None:
            return default
        if isinstance(body, dict):
            return body.get(field, default)
        return getattr(body, field, default)

    def _financial(field: str) -> Any:
        """Read a field via SemanticExtraction.get_financial_value()."""
        if sd is None or not hasattr(sd, "get_financial_value"):
            return None
        return sd.get_financial_value(field)

    def _sem(field: str, default: Any = None) -> Any:
        """Read a top-level attribute or body field from SemanticExtraction."""
        if sd is None:
            return default
        val = getattr(sd, field, None)
        if val is not None:
            return val
        # Fallback: search all bodies for the field
        bodies = getattr(sd, "bodies", {})
        for body in bodies.values():
            if isinstance(body, dict):
                if field in body:
                    return body[field]
            else:
                bval = getattr(body, field, None)
                if bval is not None:
                    return bval
        return default

    def _days_until(date_str: Any) -> Optional[int]:
        if not date_str:
            return None
        try:
            d = _date.fromisoformat(str(date_str)[:10])
            return (d - today).days
        except (ValueError, TypeError):
            return None

    # Document age from doc_date property (already resolved via meta_header)
    age_days: Optional[int] = None
    raw_date = _prop("doc_date") or getattr(doc, "created_at", None)
    if raw_date:
        try:
            d = _date.fromisoformat(str(raw_date)[:10])
            age_days = (today - d).days
        except (ValueError, TypeError) as exc:
            logger.debug(f"build_workflow_data: could not parse doc_date '{raw_date}': {exc}")

    return {
        # Finance — resolved via VirtualDocument properties and get_financial_value
        "total_gross":   _prop("total_gross"),
        "total_net":     _prop("total_net"),
        "total_tax":     _prop("total_tax"),
        "iban":          _prop("iban"),
        "bic":           _prop("bic"),
        "currency":      _prop("currency"),
        "order_number":  _financial("order_number"),
        "customer_id":   _financial("customer_id"),
        "payment_terms": _financial("payment_terms"),
        # Document metadata — resolved via VirtualDocument properties
        "doc_date":       _prop("doc_date"),
        "doc_number":     _prop("doc_number"),
        "sender_name":    _prop("sender_name"),
        "recipient_name": _prop("recipient_name"),
        "direction":      getattr(sd, "direction", None) if sd else None,
        "effective_type": _prop("effective_type"),
        "pdf_class":      getattr(doc, "pdf_class", None),
        "ai_confidence":  getattr(sd, "ai_confidence", None) if sd else None,
        "page_count":     getattr(doc, "page_count", None) or getattr(doc, "page_count_virt", None),
        # Contract — from legal_body and subscription_info bodies
        "termination_date":   _body("legal_body", "termination_date"),
        "valid_until":        _body("legal_body", "valid_until"),
        "service_period_end": _body("subscription_info", "service_period_end"),
        "is_recurring":       _body("subscription_info", "is_recurring"),
        "frequency":          _body("subscription_info", "frequency"),
        # Time-based
        "AGE_DAYS":          age_days,
        "DAYS_IN_STATE":     days_in_state,
        "DAYS_UNTIL_DUE":    _days_until(_sem("due_date")),
        "DAYS_UNTIL_EXPIRY": _days_until(_sem("valid_until") or _sem("termination_date")),
    }
