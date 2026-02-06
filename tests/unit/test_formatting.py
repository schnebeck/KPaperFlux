import pytest
from core.utils.formatting import format_currency, format_date

# --- GERMAN (DE) TESTS ---

def test_currency_formatting_de():
    """Verifies German currency formatting."""
    assert format_currency(1234.56, "€", locale="de") == "1.234,56 €"
    assert format_currency(16.9, "€", locale="de") == "16,90 €"

def test_currency_no_extra_dot_before_symbol_de():
    """Regression test for the extra dot bug in German locale."""
    result = format_currency(269.99, "€", locale="de")
    assert result == "269,99 €"
    assert "." not in result.split(",")[-1]

def test_date_formatting_de():
    """Verifies German date format (DD.MM.YYYY)."""
    assert format_date("2025-06-13", locale="de") == "13.06.2025"

# --- ENGLISH (EN) TESTS ---

def test_currency_formatting_en():
    """Verifies English currency formatting (Symbol prefix, dot as decimal)."""
    # Note: Standard EN formatting often prefix symbols.
    assert format_currency(1234.56, "€", locale="en") == "€ 1,234.56"
    assert format_currency(16.9, "$", locale="en") == "$ 16.90"
    
def test_currency_formatting_en_fallback():
    """Verifies that for EUR we might keep suffix if requested, but default EN is prefix."""
    assert format_currency(1234.56, "EUR", locale="en") == "1,234.56 EUR"

def test_date_formatting_en():
    """Verifies English date format (defaults to ISO YYYY-MM-DD for consistency)."""
    assert format_date("2025-06-13", locale="en") == "2025-06-13"

# --- EDGE CASES ---

def test_formatting_none_handling():
    """Ensures None returns the fallback regardless of locale."""
    assert format_currency(None, locale="de") == "---"
    assert format_currency(None, locale="en") == "---"
    assert format_date(None, locale="de") == "---"
    assert format_date(None, locale="en") == "---"
