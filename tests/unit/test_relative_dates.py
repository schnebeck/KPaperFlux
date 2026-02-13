import pytest
import json
from datetime import datetime, timedelta
from core.database import DatabaseManager

@pytest.fixture
def db():
    # We dont need a real file for private method testing
    return DatabaseManager(":memory:")

def test_resolve_relative_dates(db):
    now = datetime.now()
    today = now.date()
    
    # LAST_7_DAYS
    res = db._resolve_relative_date("LAST_7_DAYS")
    assert isinstance(res, tuple)
    assert res[1] == today.isoformat()
    assert res[0] == (today - timedelta(days=7)).isoformat()
    
    # LAST_MONTH
    res = db._resolve_relative_date("LAST_MONTH")
    assert isinstance(res, tuple)
    last_month_end = today.replace(day=1) - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    assert res[0] == last_month_start.isoformat()
    assert res[1] == last_month_end.isoformat()
    
    # THIS_YEAR
    res = db._resolve_relative_date("THIS_YEAR")
    assert res[0] == today.replace(month=1, day=1).isoformat()
    assert res[1] == today.isoformat()
    
    # Pass-through
    assert db._resolve_relative_date("2023-01-01") == "2023-01-01"
    assert db._resolve_relative_date(None) is None

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
