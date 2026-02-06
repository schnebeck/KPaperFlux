from decimal import Decimal
from typing import Any, Union

def format_currency(val: Union[float, Decimal, str], currency: str = "€", locale: str = "de") -> str:
    """
    Formats a numeric value as a locale-specific currency string.
    de: 1.234,56 €
    en: € 1,234.56
    """
    if val is None:
        return "---"
    
    try:
        amount = float(val)
        locale_clean = locale.split("_")[0].lower()
        
        if locale_clean == "de":
            s = f"{amount:,.2f}"
            formatted = s.replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
            return f"{formatted} {currency}".strip()
        else:
            # English/International default: 1,234.56 € (or € 1,234.56)
            # Standard formatting usually puts symbol first for EN, but let's keep it suffix-friendly
            # for invoice compatibility unless specified.
            s = f"{amount:,.2f}"
            if locale_clean == "en":
                 return f"{currency} {s}".strip() if currency != "EUR" else f"{s} EUR"
            return f"{s} {currency}".strip()

    except (ValueError, TypeError):
        return str(val)

def format_date(val: Any, locale: str = "de") -> str:
    """Formats an ISO date string."""
    if not val:
        return "---"
    
    val_str = str(val)
    locale_clean = locale.split("_")[0].lower()
    
    if "-" in val_str:
        try:
            from datetime import datetime
            dt = datetime.strptime(val_str.split("T")[0], "%Y-%m-%d")
            if locale_clean == "de":
                return dt.strftime("%d.%m.%Y")
            else:
                return dt.strftime("%Y-%m-%d") # ISO standard for EN
        except:
            pass
    return val_str
