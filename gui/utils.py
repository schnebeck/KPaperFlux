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
        
    return locale.toString(d, "dd.MM.yyyy")

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
    # User requested "Date+Time-Stamp" (likely with seconds).
    # "dd.MM.yyyy HH:mm:ss" is a safe standard for DE/ISO-like. 
    # But to respect locale, we try to use system format but ensure seconds.
    # FormatType.MediumFormat usually adds seconds.
    return locale.toString(dt, "dd.MM.yyyy HH:mm:ss")
