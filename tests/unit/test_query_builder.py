"""
Regression tests for core.query_builder.QueryBuilder.

These tests exercise every operator, field type, and special case that was
previously embedded inside DatabaseManager._build_where_clause and friends.
They run without any database connection.
"""

import pytest
from datetime import date

from core.query_builder import QueryBuilder


@pytest.fixture
def qb() -> QueryBuilder:
    return QueryBuilder()


# ── map_field ──────────────────────────────────────────────────────────────

class TestMapField:
    def test_static_field_uuid(self, qb):
        assert qb.map_field("uuid") == "uuid"

    def test_static_field_amount(self, qb):
        expr = qb.map_field("amount")
        assert "grand_total_amount" in expr
        assert "CAST" in expr

    def test_static_field_expiry_date(self, qb):
        expr = qb.map_field("expiry_date")
        assert "COALESCE" in expr
        assert "termination_date" in expr

    def test_semantic_prefix(self, qb):
        expr = qb.map_field("semantic:meta_header.doc_date")
        assert expr == "json_extract(semantic_data, '$.meta_header.doc_date')"

    def test_json_prefix(self, qb):
        expr = qb.map_field("json:bodies.finance_body.invoice_number")
        assert expr == "json_extract(semantic_data, '$.bodies.finance_body.invoice_number')"

    def test_stamp_field_prefix(self, qb):
        expr = qb.map_field("stamp_field:Betrag")
        assert "form_fields" in expr
        assert "Betrag" in expr

    def test_known_column_passthrough(self, qb):
        assert qb.map_field("storage_location") == "storage_location"

    def test_unknown_field_is_not_pasted_into_sql(self, qb):
        assert qb.map_field("some_column") == "NULL"
        assert qb.map_field("1=1) OR (1") == "NULL"

    def test_invalid_semantic_path_is_rejected(self, qb):
        assert qb.map_field("semantic:foo'bar") == "NULL"
        assert qb.map_field("semantic:foo') OR 1=1 --") == "NULL"

    def test_valid_semantic_paths(self, qb):
        assert qb.map_field("semantic:workflows.rule-x.current_step") == \
            "json_extract(semantic_data, '$.workflows.rule-x.current_step')"
        assert qb.map_field("semantic:bodies.finance_body.line_items[0]").endswith("line_items[0]')")


class TestScopedWhere:
    def test_excludes_deleted_and_archived_by_default(self, qb):
        where, _ = qb.build_scoped_where({"field": "status", "op": "equals", "value": "NEW"})
        assert "deleted = 0" in where and "archived = 0" in where

    def test_query_on_archived_or_deleted_keeps_them(self, qb):
        where, _ = qb.build_scoped_where({"operator": "AND", "conditions": [
            {"field": "archived", "op": "equals", "value": True}]})
        assert "archived = 0" not in where and "deleted = 0" in where

    def test_text_mentioning_deleted_does_not_disable_the_scope(self, qb):
        where, _ = qb.build_scoped_where({"field": "cached_full_text", "op": "contains", "value": "deleted"})
        assert "deleted = 0" in where


# ── resolve_relative_date ──────────────────────────────────────────────────

class TestResolveRelativeDate:
    def test_non_string_passthrough(self, qb):
        assert qb.resolve_relative_date(42) == 42
        assert qb.resolve_relative_date(None) is None

    def test_last_7_days_returns_tuple(self, qb):
        result = qb.resolve_relative_date("LAST_7_DAYS")
        assert isinstance(result, tuple)
        start, end = result
        start_d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)
        assert (end_d - start_d).days == 7

    def test_last_30_days(self, qb):
        result = qb.resolve_relative_date("LAST_30_DAYS")
        start, end = result
        assert (date.fromisoformat(end) - date.fromisoformat(start)).days == 30

    def test_last_90_days(self, qb):
        result = qb.resolve_relative_date("LAST_90_DAYS")
        start, end = result
        assert (date.fromisoformat(end) - date.fromisoformat(start)).days == 90

    def test_this_month_starts_on_first(self, qb):
        result = qb.resolve_relative_date("THIS_MONTH")
        start, _ = result
        assert date.fromisoformat(start).day == 1

    def test_last_month_full_month(self, qb):
        result = qb.resolve_relative_date("LAST_MONTH")
        start, end = result
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
        assert s.day == 1
        assert e.month != date.today().month or e.year != date.today().year

    def test_this_year_starts_jan_1(self, qb):
        result = qb.resolve_relative_date("THIS_YEAR")
        start, _ = result
        d = date.fromisoformat(start)
        assert d.month == 1 and d.day == 1

    def test_last_year_full_year(self, qb):
        result = qb.resolve_relative_date("LAST_YEAR")
        start, end = result
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
        assert s.year == date.today().year - 1
        assert s.month == 1 and s.day == 1
        assert e.month == 12 and e.day == 31

    def test_relative_negative_days(self, qb):
        result = qb.resolve_relative_date("relative:-30d")
        d = date.fromisoformat(result)
        assert d < date.today()

    def test_relative_positive_days(self, qb):
        result = qb.resolve_relative_date("relative:7d")
        d = date.fromisoformat(result)
        assert d > date.today()

    def test_comma_split_to_tuple(self, qb):
        result = qb.resolve_relative_date("2025-01-01,2025-12-31")
        assert result == ("2025-01-01", "2025-12-31")

    def test_unknown_literal_passthrough(self, qb):
        assert qb.resolve_relative_date("SOME_FUTURE_LITERAL") == "SOME_FUTURE_LITERAL"


# ── map_op ────────────────────────────────────────────────────────────────

class TestMapOp:
    def test_equals_scalar(self, qb):
        sql, params = qb.map_op("status", "equals", "DONE")
        assert "= ?" in sql
        assert params == ["DONE"]

    def test_equals_list(self, qb):
        sql, params = qb.map_op("status", "equals", ["DONE", "NEW"])
        assert "IN" in sql
        assert params == ["DONE", "NEW"]

    def test_equals_empty_list(self, qb):
        sql, params = qb.map_op("status", "equals", [])
        assert sql == "1=1"

    def test_contains_plain(self, qb):
        sql, params = qb.map_op("export_filename", "contains", "invoice")
        assert "LIKE" in sql
        assert params == ["%invoice%"]

    def test_contains_json_array_field(self, qb):
        sql, params = qb.map_op("type_tags", "contains", "INVOICE")
        assert "json_each" in sql
        assert params == ["INVOICE"]

    def test_contains_json_array_list(self, qb):
        sql, params = qb.map_op("type_tags", "contains", ["INVOICE", "ORDER"])
        assert "json_each" in sql
        assert len(params) == 2

    def test_starts_with(self, qb):
        sql, params = qb.map_op("uuid", "starts_with", "abc")
        assert sql.endswith("LIKE ?")
        assert params == ["abc%"]

    def test_gt(self, qb):
        sql, params = qb.map_op("ai_confidence", "gt", 0.8)
        assert "> ?" in sql
        assert params == [0.8]

    def test_lte(self, qb):
        sql, params = qb.map_op("page_count_virt", "lte", 5)
        assert "<= ?" in sql

    def test_is_empty(self, qb):
        sql, params = qb.map_op("doc_date", "is_empty", None)
        assert "IS NULL" in sql
        assert params == []

    def test_is_not_empty(self, qb):
        sql, params = qb.map_op("doc_date", "is_not_empty", None)
        assert "IS NOT NULL" in sql

    def test_between(self, qb):
        sql, params = qb.map_op("created_at", "between", ["2025-01-01", "2025-12-31"])
        assert "BETWEEN" in sql
        assert len(params) == 2

    def test_in_list(self, qb):
        sql, params = qb.map_op("status", "in", ["NEW", "DONE"])
        assert "IN" in sql
        assert len(params) == 2

    def test_in_empty_returns_false(self, qb):
        sql, params = qb.map_op("status", "in", [])
        assert sql == "1=0"

    def test_date_range_auto_promotes_to_between(self, qb):
        sql, params = qb.map_op("created_at", "equals", "LAST_7_DAYS")
        assert "BETWEEN" in sql

    def test_bool_string_true_coercion(self, qb):
        sql, params = qb.map_op("deleted", "equals", "true")
        assert params == [True]

    def test_bool_string_false_coercion(self, qb):
        sql, params = qb.map_op("deleted", "equals", "false")
        assert params == [False]

    def test_unknown_op_returns_tautology(self, qb):
        sql, params = qb.map_op("status", "does_not_exist", "x")
        assert sql == "1=1"


# ── build_where ───────────────────────────────────────────────────────────

class TestBuildWhere:
    def test_simple_leaf(self, qb):
        node = {"field": "status", "op": "equals", "value": "DONE"}
        sql, params = qb.build_where(node)
        assert "status" in sql
        assert params == ["DONE"]

    def test_negated_leaf(self, qb):
        node = {"field": "status", "op": "equals", "value": "DONE", "negate": True}
        sql, params = qb.build_where(node)
        assert sql.startswith("NOT (")

    def test_and_group(self, qb):
        node = {
            "operator": "AND",
            "conditions": [
                {"field": "status", "op": "equals", "value": "DONE"},
                {"field": "deleted", "op": "equals", "value": False},
            ],
        }
        sql, params = qb.build_where(node)
        assert " AND " in sql
        assert len(params) == 2

    def test_or_group(self, qb):
        node = {
            "operator": "OR",
            "conditions": [
                {"field": "status", "op": "equals", "value": "NEW"},
                {"field": "status", "op": "equals", "value": "DONE"},
            ],
        }
        sql, params = qb.build_where(node)
        assert " OR " in sql

    def test_empty_group_returns_tautology(self, qb):
        node = {"operator": "AND", "conditions": []}
        sql, params = qb.build_where(node)
        assert sql == "1=1"
        assert params == []

    def test_unknown_node_returns_tautology(self, qb):
        sql, params = qb.build_where({"something": "else"})
        assert sql == "1=1"

    def test_nested_groups(self, qb):
        node = {
            "operator": "AND",
            "conditions": [
                {"field": "deleted", "op": "equals", "value": False},
                {
                    "operator": "OR",
                    "conditions": [
                        {"field": "status", "op": "equals", "value": "NEW"},
                        {"field": "status", "op": "equals", "value": "DONE"},
                    ],
                },
            ],
        }
        sql, params = qb.build_where(node)
        assert " AND " in sql
        assert " OR " in sql
        assert len(params) == 3

    def test_semantic_field_in_leaf(self, qb):
        node = {"field": "semantic:meta_header.doc_date", "op": "equals", "value": "2025-01-01"}
        sql, params = qb.build_where(node)
        assert "json_extract" in sql
        assert params == ["2025-01-01"]


# ── workflow_step special case ────────────────────────────────────────────

class TestWorkflowStep:
    def test_is_not_empty(self, qb):
        node = {"field": "workflow_step", "op": "is_not_empty"}
        sql, params = qb.build_where(node)
        assert "workflows" in sql
        assert params == []

    def test_equals(self, qb):
        node = {"field": "workflow_step", "op": "equals", "value": "PAID"}
        sql, params = qb.build_where(node)
        assert "json_each" in sql
        assert "current_step" in sql
        assert params == ["PAID"]

    def test_in_list(self, qb):
        node = {"field": "workflow_step", "op": "in", "value": ["PAID", "DONE"]}
        sql, params = qb.build_where(node)
        assert "IN" in sql
        assert params == ["PAID", "DONE"]

    def test_negated_workflow_step(self, qb):
        node = {"field": "workflow_step", "op": "equals", "value": "NEW", "negate": True}
        sql, params = qb.build_where(node)
        assert sql.startswith("NOT (")


class TestValueAndOperatorSafety:
    def test_text_with_one_comma_stays_text(self, qb):
        where, params = qb.build_where({"field": "sender", "op": "contains", "value": "Mueller, Hans"})
        assert "BETWEEN" not in where
        assert any("Mueller, Hans" in str(p) for p in params)

    def test_decimal_comma_value_stays_text(self, qb):
        where, _ = qb.build_where({"field": "amount", "op": "equals", "value": "12,50"})
        assert "BETWEEN" not in where

    def test_date_range_string_becomes_day_range(self, qb):
        where, params = qb.build_where({"field": "created_at", "op": "equals", "value": "2026-10-01,2026-10-31"})
        assert "substr(created_at, 1, 10) BETWEEN ? AND ?" in where
        assert params == ["2026-10-01", "2026-10-31"]

    def test_invalid_group_operator_matches_nothing(self, qb):
        where, params = qb.build_where({"operator": "AND 1=1) OR (1", "conditions": [
            {"field": "status", "op": "equals", "value": "NEW"}]})
        assert where == "1=0" and params == []


def test_today_range_includes_todays_timestamps(tmp_path):
    from datetime import datetime
    from core.database import DatabaseManager
    db = DatabaseManager(str(tmp_path / "range.db"))
    db.init_db()
    db.connection.execute("INSERT INTO virtual_documents (uuid, created_at, deleted, archived) VALUES (?, ?, 0, 0)",
                          ("today", datetime.now().isoformat()))
    db.connection.commit()

    docs = db.search_documents_advanced({"field": "created_at", "op": "equals", "value": "LAST_7_DAYS"})

    assert [d.uuid for d in docs] == ["today"]
