import pytest
from core.query_builder import QueryBuilder


@pytest.fixture
def qb():
    return QueryBuilder()


def test_json_query_generation(qb):
    """json: prefix fields are translated into json_extract SQL calls."""
    query = {"field": "json:stamps.cost_center", "op": "equals", "value": "10"}
    sql, params = qb.build_where(query)
    assert "json_extract" in sql
    assert "$.stamps.cost_center" in sql
    assert "10" in params


def test_json_contains_query(qb):
    """json: prefix with 'contains' generates a LIKE expression."""
    query = {"field": "json:status", "op": "contains", "value": "ready"}
    sql, params = qb.build_where(query)
    assert "LIKE" in sql
    assert "json_extract" in sql
    assert "%ready%" in params
