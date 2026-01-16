import pytest
from datetime import datetime, date
from gui.utils import format_date, format_datetime
from PyQt6.QtCore import QLocale, QLibraryInfo

def test_format_date_regression():
    """
    Test format_date to ensure it returns a formatted date string
    and not a literal format string.
    """
    d = date(2025, 12, 17)
    formatted = format_date(d)
    
    # We expect something like "17.12.2025" or locale specific.
    # Crucially, it should NOT contain "dd" or "MM" formatting chars literally if they are replaced.
    # But simpler: it MUST contain "2025".
    assert "2025" in formatted
    assert "17" in formatted
    assert "12" in formatted
    
    # Check against literal regression
    assert "dd" not in formatted
    assert "yyyy" not in formatted

def test_format_datetime_regression():
    """
    Test format_datetime to ensure it returns a formatted datetime string
    with time, preventing the "HH:MM:SS" literal regression.
    """
    dt = datetime(2026, 1, 16, 14, 30, 45)
    formatted = format_datetime(dt)
    
    # Should contain time components
    assert "14" in formatted
    assert "30" in formatted
    assert "45" in formatted
    assert "2026" in formatted
    
    # Regression check: The bug was that it returned "16.01.2026 HH:mm:ss" literal
    # or similar.
    assert "HH" not in formatted
    assert "mm" not in formatted
    assert "SS" not in formatted
    assert "ss" not in formatted

def test_format_iso_string_input():
    """Test compatibility with ISO string input."""
    iso_date = "2025-10-05"
    formatted = format_date(iso_date)
    assert "2025" in formatted
    assert "10" in formatted
    assert "05" in formatted
    
    iso_dt = "2025-10-05T12:00:00"
    formatted_dt = format_datetime(iso_dt)
    assert "12" in formatted_dt
    assert "00" in formatted_dt

def test_none_input():
    """Test handling of None input."""
    assert format_date(None) == ""
    assert format_datetime(None) == ""
