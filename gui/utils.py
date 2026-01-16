from PyQt6.QtCore import QLocale
from datetime import datetime, date

def format_date(d) -> str:
    """
    Format a date object (or ISO string) to localized string (e.g. 31.12.2024).
    """
    if not d:
        return ""
    
    locale = QLocale.system()
    
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d).date()
        except ValueError:
            return d # Return raw if parse fails
            
    if isinstance(d, datetime):
        d = d.date()
        
    return locale.toString(d, QLocale.FormatType.ShortFormat)

def format_datetime(dt) -> str:
    """
    Format a datetime object (or ISO string) to localized string (e.g. 31.12.2024 14:30).
    """
    if not dt:
        return ""
        
    locale = QLocale.system()
    
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return dt
            
    # QLocale ShortFormat for DateTime often includes Time, but let's be explicit if needed.
    # Actually ShortFormat usually is "dd.MM.yyyy HH:mm" in DE.
    # Let's rely on QLocale to match system preference exactly.
    return locale.toString(dt, QLocale.FormatType.ShortFormat)
