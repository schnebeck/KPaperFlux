"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/query_builder.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Pure SQL fragment builder for structured filter query dicts.
                Extracted from DatabaseManager to make the query logic
                independently testable and extensible without touching the
                database connection layer.
------------------------------------------------------------------------------
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from core.logger import get_logger

logger = get_logger("core.query_builder")


class QueryBuilder:
    """
    Translates structured filter query dicts into SQL WHERE clause fragments.

    Stateless — all public methods are pure transformations with no side
    effects and no database connection required.  The class exists solely to
    be instantiated once inside DatabaseManager and reused across queries.

    Supported query node shapes
    ---------------------------
    Leaf condition::

        {"field": "status", "op": "equals", "value": "DONE", "negate": False}

    Group::

        {"operator": "AND", "conditions": [...]}
    """

    # ── Field → SQL expression map ────────────────────────────────────────────
    # Maps logical field names used in filter queries to the corresponding SQL
    # expressions.  Add new queryable fields here — no other file needs to
    # change.  workflow_step is intentionally absent; it is handled by a
    # json_each subquery in build_where().
    FIELD_MAP: Dict[str, str] = {
        "uuid":               "uuid",
        "status":             "status",
        "page_count_virt":    "page_count_virt",
        "created_at":         "created_at",
        "last_processed_at":  "last_processed_at",
        "last_used":          "last_used",
        "cached_full_text":   "cached_full_text",
        "original_filename":  "export_filename",
        "deleted":            "deleted",
        "type_tags":          "type_tags",
        "sender":             "json_extract(semantic_data, '$.meta_header.sender.name')",
        "doc_date":           "json_extract(semantic_data, '$.meta_header.doc_date')",
        "amount":             (
            "CAST(json_extract(semantic_data,"
            " '$.bodies.finance_body.monetary_summation.grand_total_amount') AS REAL)"
        ),
        "direction":          "json_extract(semantic_data, '$.direction')",
        "tenant_context":     "json_extract(semantic_data, '$.tenant_context')",
        "classification":     "json_extract(type_tags, '$[0]')",
        "visual_audit_mode":  (
            "COALESCE(json_extract(semantic_data, '$.visual_audit.meta_mode'), 'NONE')"
        ),
        "archived":           "archived",
        "storage_location":   "storage_location",
        "ai_confidence":      "ai_confidence",
        "process_id":         "process_id",
        "expiry_date": (
            "COALESCE("
            "json_extract(semantic_data, '$.bodies.legal_body.termination_date'), "
            "json_extract(semantic_data, '$.bodies.legal_body.valid_until'), "
            "json_extract(semantic_data, '$.bodies.finance_body.due_date'))"
        ),
        "stamp_text": (
            "(SELECT group_concat(COALESCE(json_extract(s.value, '$.raw_content'), '')) "
            " FROM json_each(json_extract(semantic_data, '$.visual_audit.layer_stamps')) AS s)"
        ),
        "stamp_type": (
            "(SELECT group_concat(COALESCE(json_extract(s.value, '$.type'), '')) "
            " FROM json_each(json_extract(semantic_data, '$.visual_audit.layer_stamps')) AS s)"
        ),
    }

    # ── Public API ────────────────────────────────────────────────────────────

    def build_where(self, node: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """
        Recursively translates a query node into a SQL WHERE fragment.

        Args:
            node: Leaf condition dict or group dict (see class docstring).

        Returns:
            Tuple of (sql_fragment, bound_parameters).
        """
        if "field" in node:
            return self._build_leaf(node)

        if "conditions" in node:
            return self._build_group(node)

        return "1=1", []

    def map_field(self, field: str) -> str:
        """
        Maps a logical field name to its SQL expression.

        Handles three resolution strategies in order:
        1. Static FIELD_MAP lookup.
        2. ``semantic:`` / ``json:`` prefix → dynamic json_extract path.
        3. ``stamp_field:`` prefix → correlated subquery over stamp form fields.
        4. Fallback: return field name as-is (column pass-through).

        Args:
            field: Logical field name.

        Returns:
            SQL expression string.
        """
        if field in self.FIELD_MAP:
            return self.FIELD_MAP[field]

        if field.startswith(("json:", "semantic:")):
            path = field.split(":", 1)[1].replace("'", "''")
            return f"json_extract(semantic_data, '$.{path}')"

        if field.startswith("stamp_field:"):
            label = field[12:].replace("'", "''")
            return (
                f"(SELECT group_concat(COALESCE(json_extract(f.value, '$.normalized_value'), "
                f"json_extract(f.value, '$.raw_value'))) "
                f" FROM json_each(COALESCE(json_extract(semantic_data, '$.visual_audit.layer_stamps'), "
                f" json_extract(semantic_data, '$.layer_stamps'))) AS s, "
                f" json_each(json_extract(s.value, '$.form_fields')) AS f "
                f" WHERE json_extract(f.value, '$.label') = '{label}')"
            )

        return field

    def map_op(self, expr: str, op: str, val: Any) -> Tuple[str, List[Any]]:
        """
        Translates a logical operator + value into a SQL condition fragment.

        Relative date literals (e.g. ``LAST_MONTH``) are resolved before the
        operator is applied; a resolved range tuple automatically promotes the
        operator to ``between``.

        Args:
            expr: SQL expression string for the left-hand side.
            op:   Operator name (``equals``, ``contains``, ``gt``, …).
            val:  Raw value from the query dict.

        Returns:
            Tuple of (sql_fragment, bound_parameters).
        """
        resolved = self.resolve_relative_date(val)

        # Range tuple → force between regardless of original op
        if isinstance(resolved, tuple) and len(resolved) == 2:
            op = "between"
            val = list(resolved)
        else:
            val = resolved

        if isinstance(val, str):
            if val.lower() == "true":
                val = True
            elif val.lower() == "false":
                val = False

        if op == "equals":
            if isinstance(val, list):
                if not val:
                    return "1=1", []
                placeholders = ", ".join(["?"] * len(val))
                return f"{expr} COLLATE NOCASE IN ({placeholders})", val
            return f"{expr} = ? COLLATE NOCASE", [val]

        if op == "contains":
            if expr in ("type_tags", "tags"):
                if isinstance(val, list):
                    if not val:
                        return "1=1", []
                    clauses = [
                        f"EXISTS (SELECT 1 FROM json_each({expr}) WHERE value = ? COLLATE NOCASE)"
                        for _ in val
                    ]
                    return "(" + " OR ".join(clauses) + ")", val
                return (
                    f"EXISTS (SELECT 1 FROM json_each({expr}) WHERE value = ? COLLATE NOCASE)",
                    [val],
                )
            if isinstance(val, list):
                if not val:
                    return "1=1", []
                clauses = [f"{expr} LIKE ?" for _ in val]
                params = [f"%{v}%" for v in val]
                return "(" + " OR ".join(clauses) + ")", params
            return f"{expr} LIKE ?", [f"%{val}%"]

        if op == "starts_with":
            return f"{expr} LIKE ?", [f"{val}%"]

        if op in ("gt", "gte", "lt", "lte"):
            sql_ops = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
            return f"{expr} {sql_ops[op]} ?", [val]

        if op == "is_empty":
            return f"{expr} IS NULL OR {expr} = ''", []

        if op == "is_not_empty":
            return f"{expr} IS NOT NULL AND {expr} != ''", []

        if op == "between":
            if isinstance(val, list) and len(val) == 2:
                return f"{expr} BETWEEN ? AND ?", [val[0], val[1]]

        if op == "in":
            if not val:
                return "1=0", []
            if isinstance(val, (list, tuple, set)):
                placeholders = ", ".join(["?"] * len(val))
                return f"{expr} COLLATE NOCASE IN ({placeholders})", list(val)
            return f"{expr} = ? COLLATE NOCASE", [val]

        return "1=1", []

    def resolve_relative_date(self, val: Any) -> Any:
        """
        Translates relative date literals into absolute date strings or
        (start, end) tuples.

        Known literals: ``LAST_7_DAYS``, ``LAST_30_DAYS``, ``LAST_90_DAYS``,
        ``THIS_MONTH``, ``LAST_MONTH``, ``THIS_YEAR``, ``LAST_YEAR``,
        ``relative:<N>d``.  Comma-separated ``"a,b"`` strings are split into
        ``(a, b)`` tuples.  All other values are returned unchanged.

        Args:
            val: Raw value from the query dict.

        Returns:
            Resolved value — scalar, tuple, or original value.
        """
        if not isinstance(val, str):
            return val

        today = datetime.now().date()

        _LITERALS: Dict[str, Any] = {
            "TODAY":        today.isoformat(),
            "LAST_7_DAYS":  ((today - timedelta(days=7)).isoformat(), today.isoformat()),
            "LAST_30_DAYS": ((today - timedelta(days=30)).isoformat(), today.isoformat()),
            "LAST_90_DAYS": ((today - timedelta(days=90)).isoformat(), today.isoformat()),
            "THIS_MONTH":   (today.replace(day=1).isoformat(), today.isoformat()),
            "THIS_YEAR":    (today.replace(month=1, day=1).isoformat(), today.isoformat()),
        }
        if val in _LITERALS:
            return _LITERALS[val]

        if val == "LAST_MONTH":
            end = today.replace(day=1) - timedelta(days=1)
            return (end.replace(day=1).isoformat(), end.isoformat())

        if val == "LAST_YEAR":
            y = today.year - 1
            return (
                today.replace(year=y, month=1, day=1).isoformat(),
                today.replace(year=y, month=12, day=31).isoformat(),
            )

        if val.startswith("relative:"):
            try:
                offset_str = val.split(":")[1]
                unit = offset_str[-1]
                amount = int(offset_str[:-1])
                if unit == "d":
                    return (today + timedelta(days=amount)).isoformat()
            except Exception as e:
                logger.error(f"Failed to parse relative date '{val}': {e}")

        if "," in val and len(val.split(",")) == 2:
            return tuple(val.split(","))

        return val

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_leaf(self, node: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """Handles a single field/op/value condition node."""
        field = node["field"]
        op = node["op"]
        val = node.get("value")
        negate = node.get("negate", False)

        # workflow_step: cross-rule — matches if ANY active workflow has the step
        if field == "workflow_step":
            clause, params = self._build_workflow_step_clause(op, val)
            if negate:
                return f"NOT ({clause})", params
            return clause, params

        expr = self.map_field(field)
        clause, params = self.map_op(expr, op, val)

        if negate:
            return f"NOT ({clause})", params
        return clause, params

    def _build_group(self, node: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """Handles AND/OR groups of sub-conditions."""
        logic_op = str(node.get("operator", "AND")).upper()
        sub_clauses: List[str] = []
        all_params: List[Any] = []

        for cond in node["conditions"]:
            clause, params = self.build_where(cond)
            if clause:
                sub_clauses.append(f"({clause})")
                all_params.extend(params)

        if not sub_clauses:
            return "1=1", []

        return f" {logic_op} ".join(sub_clauses), all_params

    def _build_workflow_step_clause(self, op: str, val: Any) -> Tuple[str, List[Any]]:
        """
        Builds the workflow_step subquery — checks if ANY active workflow in
        the json dict has the given current_step value.
        """
        wf_json = "json_extract(semantic_data, '$.workflows')"
        if op == "is_not_empty":
            return (
                f"({wf_json} IS NOT NULL AND {wf_json} != '{{}}')",
                [],
            )
        if op == "in" and isinstance(val, list):
            placeholders = ",".join("?" * len(val))
            return (
                f"EXISTS (SELECT 1 FROM json_each({wf_json}) "
                f"WHERE json_extract(value, '$.current_step') IN ({placeholders}))",
                list(val),
            )
        # equals / contains / any other op → exact match
        return (
            f"EXISTS (SELECT 1 FROM json_each({wf_json}) "
            f"WHERE json_extract(value, '$.current_step') = ?)",
            [val],
        )
