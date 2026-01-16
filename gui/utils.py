from PyQt6.QtCore import QLocale, QDate, QDateTime, QTime, Qt
from datetime import datetime, date

def format_date(d) -> str:
# ... (omitted)

    if isinstance(dt, datetime):
        # Convert to QDateTime
        # Note: QDate(y, m, d) -> QDateTime(qdate, qtime)
        dt = QDateTime(
            QDate(dt.year, dt.month, dt.day),
            QTime(dt.hour, dt.minute, dt.second)
        )
    elif isinstance(dt, date):
         dt = QDate(dt.year, dt.month, dt.day) # Fallback if just date passed
            
    # QLocale ShortFormat for DateTime often includes Time, but let's be explicit if needed.
    # User requested "Date+Time-Stamp" (likely with seconds).
    # "dd.MM.yyyy HH:mm:ss" is a safe standard for DE/ISO-like. 
    # But to respect locale, we try to use system format but ensure seconds.
    # FormatType.MediumFormat usually adds seconds.
    return locale.toString(dt, "dd.MM.yyyy HH:mm:ss")
