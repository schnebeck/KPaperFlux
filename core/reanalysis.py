"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/reanalysis.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Carries the user's state of a document over to a new analysis
                result: workflow progress and values the user confirmed.
------------------------------------------------------------------------------
"""
import copy
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from core.logger import get_logger
from core.models.semantic import SemanticExtraction

logger = get_logger("reanalysis")

_MISSING = object()


def _get_path(data: Any, path: str) -> Any:
    """Value at a dotted path ('bodies.finance_body.iban', 'meta_header.references.0.ref_value')."""
    current = data
    for part in path.split("."):
        if isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def _copy_path(target: dict, source: dict, path: str) -> None:
    """
    Copies the value at a dotted path from *source* into *target*. Where *target*
    lacks a container on the way, the whole subtree is taken from *source*, so
    objects (e.g. a list entry) arrive complete.
    """
    parts = path.split(".")
    current_target: Any = target
    current_source: Any = source
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if isinstance(current_source, list):
            key: Any = int(part)
            value = current_source[key]
            if not isinstance(current_target, list):
                return
            if key >= len(current_target):
                if key == len(current_target):  # never leave a gap in the list
                    current_target.append(copy.deepcopy(value))
                return
        else:
            if not isinstance(current_target, dict):
                return
            key = part
            value = current_source[key]
            if key not in current_target:
                current_target[key] = copy.deepcopy(value)
                return
        if last or current_target[key] is None:
            current_target[key] = copy.deepcopy(value)
            return
        current_target, current_source = current_target[key], value


def confirmed_paths(semantic: Optional[SemanticExtraction]) -> List[str]:
    """Paths of the values the user edited or confirmed."""
    if semantic is None or semantic.engine is None:
        return []
    return [state.path for state in semantic.engine.fields if state.confirmed_by_user]


def carry_over_user_state(previous: Optional[SemanticExtraction], fresh: SemanticExtraction) -> SemanticExtraction:
    """
    Merges the user's state of the previous extraction into a fresh analysis result.

    Workflow progress (state and history) is kept, and values the user confirmed
    replace the new engine values at the same path; their review state stays confirmed.

    Args:
        previous: Semantic data before the re-analysis (None: nothing to keep).
        fresh: The new engine result.

    Returns:
        The merged semantic data (a new object).
    """
    if previous is None:
        return fresh
    merged = fresh.model_dump()
    old = previous.model_dump()

    for rule_id, workflow in (old.get("workflows") or {}).items():
        merged.setdefault("workflows", {})[rule_id] = workflow

    result = SemanticExtraction.model_validate(merged)
    old_states = {state.path: state for state in previous.engine.fields} if previous.engine else {}
    kept: Dict[str, Any] = {}
    for path in confirmed_paths(previous):
        value = _get_path(old, path)
        if value is _MISSING:
            continue
        candidate = copy.deepcopy(merged)
        _copy_path(candidate, old, path)
        try:
            result = SemanticExtraction.model_validate(candidate)
        except ValidationError as e:
            logger.warning(f"Confirmed value at '{path}' no longer fits the extraction; not kept: {e}")
            continue
        merged = candidate
        kept[path] = value
    if kept and result.engine is not None:
        new_states = {state.path: state for state in result.engine.fields}
        for path, value in kept.items():
            old_state = old_states[path]
            state = new_states.get(path)
            if state is None:
                result.engine.fields.append(old_state.model_copy())
            else:
                state.value = value
                state.confirmed_by_user = True
                state.confirmed_at = old_state.confirmed_at
        logger.info(f"Kept {len(kept)} user-confirmed value(s) across re-analysis")
    return result
