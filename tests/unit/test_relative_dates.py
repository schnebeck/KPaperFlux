import pytest
import json
from datetime import datetime, timedelta
from core.database import DatabaseManager
from core.query_builder import QueryBuilder

@pytest.fixture
def qb():
    return QueryBuilder()

@pytest.fixture
def db():
    return DatabaseManager(":memory:")

def test_resolve_relative_dates(qb):
    now = datetime.now()
    today = now.date()

    # LAST_7_DAYS
    res = qb.resolve_relative_date("LAST_7_DAYS")
    assert isinstance(res, tuple)
    assert res[1] == today.isoformat()
    assert res[0] == (today - timedelta(days=7)).isoformat()

    # LAST_MONTH
    res = qb.resolve_relative_date("LAST_MONTH")
    assert isinstance(res, tuple)
    last_month_end = today.replace(day=1) - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    assert res[0] == last_month_start.isoformat()
    assert res[1] == last_month_end.isoformat()

    # THIS_YEAR
    res = qb.resolve_relative_date("THIS_YEAR")
    assert res[0] == today.replace(month=1, day=1).isoformat()
    assert res[1] == today.isoformat()

    # Pass-through
    assert qb.resolve_relative_date("2023-01-01") == "2023-01-01"
    assert qb.resolve_relative_date(None) is None

def test_trend_data_generation(db):
    """Test the dynamic scaling and auto-binning (Day/Month/Year)."""
    # 1. Day Binning (Close together)
    db.connection.execute("INSERT INTO virtual_documents (uuid, created_at, semantic_data, deleted) VALUES (?, ?, ?, 0)", 
                        ("u1", "2025-01-01 10:00:00", json.dumps({"meta_header": {"doc_date": "2025-01-01"}})))
    db.connection.execute("INSERT INTO virtual_documents (uuid, created_at, semantic_data, deleted) VALUES (?, ?, ?, 0)", 
                        ("u2", "2025-01-03 12:00:00", json.dumps({"meta_header": {"doc_date": "2025-01-03"}})))
    db.connection.commit()
    
    # Days=None triggers auto-scaling
    res_days = db.get_trend_data_advanced({}, days=None)
    assert len(res_days) == 3 # 1st, 2nd (empty), 3rd
    assert res_days[0] == 1.0
    assert res_days[1] == 0.0
    assert res_days[2] == 1.0

    # 2. Month Binning (Far apart)
    db.connection.execute("INSERT INTO virtual_documents (uuid, created_at, semantic_data, deleted) VALUES (?, ?, ?, 0)", 
                        ("u3", "2025-06-01 10:00:00", json.dumps({"meta_header": {"doc_date": "2025-06-01"}})))
    db.connection.commit()
    
    res_months = db.get_trend_data_advanced({}, days=None)
    # Jan to June = 6 months
    assert len(res_months) >= 6
    assert res_months[0] == 2.0 # Jan (u1, u2)
    assert res_months[5] == 1.0 # June (u3)
    assert sum(res_months) == 3.0


def _insert_dated(db, uuid: str, doc_date: str) -> None:
    db.connection.execute(
        "INSERT INTO virtual_documents (uuid, created_at, semantic_data, deleted) VALUES (?, ?, ?, 0)",
        (uuid, f"{doc_date} 10:00:00", json.dumps({"meta_header": {"doc_date": doc_date}})))
    db.connection.commit()


def test_trend_month_bins_cover_the_whole_range(db):
    """A 20-month span yields one point per month up to the last document."""
    _insert_dated(db, "first", "2024-01-15")
    _insert_dated(db, "last", "2025-08-10")

    res = db.get_trend_data_advanced({}, days=None)

    assert len(res) == 20  # 2024-01 .. 2025-08
    assert res[0] == 1.0 and res[-1] == 1.0
    assert sum(res) == 2.0


def test_trend_year_bins_cover_the_whole_range(db):
    _insert_dated(db, "first", "2000-03-01")
    _insert_dated(db, "last", "2025-03-01")

    res = db.get_trend_data_advanced({}, days=None)

    assert len(res) == 26  # 2000 .. 2025
    assert res[0] == 1.0 and res[-1] == 1.0
