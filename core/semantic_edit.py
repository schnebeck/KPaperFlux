"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/semantic_edit.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Writes values edited in the metadata editor's semantic table
                back into the semantic data dict (section and dotted path).
------------------------------------------------------------------------------
"""
from typing import Any, Dict


def _child(container: Dict[str, Any], key: str) -> Dict[str, Any]:
    """The dict stored under key, created if missing or None."""
    if container.get(key) is None:
        container[key] = {}
    return container[key]


def section_root(sd: Dict[str, Any], section: str) -> Dict[str, Any]:
    """
    Returns the container a semantic table section edits, creating it if needed.

    'Meta' is the meta header, 'Custom' the custom fields; any other section is a
    body ('Finance' -> bodies.finance_body, falling back to bodies.finance or a
    top-level key of that name).

    Args:
        sd: Semantic data as a dict (modified in place).
        section: Section label of the table row.

    Returns:
        The dict the row's path is relative to.
    """
    if section == "Meta":
        return _child(sd, "meta_header")
    if section == "Custom":
        return _child(sd, "custom_fields")

    key = section.lower()
    body_key = f"{key}_body"
    bodies = sd.get("bodies") or {}
    if body_key in bodies:
        return bodies[body_key]
    if key in bodies:
        return bodies[key]
    if key in sd:
        return sd[key]
    if body_key in sd:
        return sd[body_key]
    return _child(_child(sd, "bodies"), body_key)


def set_path(root: Any, field_path: str, value: Any) -> None:
    """
    Sets a value at a dotted path below root ('line_items.0.price'), creating
    missing dicts and list entries; numeric parts index lists.

    Args:
        root: Dict (or list) to write into.
        field_path: Dotted path relative to root.
        value: The value to store.
    """
    parts = field_path.split(".")
    target = root
    for i, part in enumerate(parts[:-1]):
        if part.isdigit() and isinstance(target, list):
            idx = int(part)
            while len(target) <= idx:
                target.append({})
            target = target[idx]
        elif part.isdigit():
            target = target.setdefault(part, {})
        else:
            if part not in target:
                target[part] = [] if parts[i + 1].isdigit() else {}
            target = target[part]

    last = parts[-1]
    if isinstance(target, list) and last.isdigit():
        idx = int(last)
        while len(target) <= idx:
            target.append(None)
        target[idx] = value
    else:
        target[last] = value
