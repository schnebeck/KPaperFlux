from PyQt6.QtCore import QLocale, QDate, QDateTime, QTime, Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtWidgets import QMessageBox, QWidget, QLabel, QVBoxLayout, QApplication
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

    if isinstance(d, (datetime, date)):
        # Convert to QDate
        d = QDate(d.year, d.month, d.day)

    return locale.toString(d, "dd.MM.yyyy")

def format_datetime(dt) -> str:
    """
    Format a datetime object (or ISO string) to localized string (e.g. 31.12.2024 14:30:00).
    """
    if not dt:
        return ""

    locale = QLocale.system()

    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return dt

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

def show_selectable_message_box(parent, title, text, icon=None, buttons=None):
    """
    Shows a QMessageBox with text selection enabled.
    Supports both positional and keyword arguments for icon and buttons.
    """
    msg = QMessageBox(parent)
    if title: msg.setWindowTitle(title)
    if text: msg.setText(text)

    # Handle case where icon might be buttons (if called from old QMessageBox sites)
    if isinstance(icon, QMessageBox.StandardButton):
        # It's likely buttons
        if buttons is None:
            buttons = icon
            icon = QMessageBox.Icon.NoIcon

    if icon: msg.setIcon(icon)
    if buttons:
        msg.setStandardButtons(buttons)
    else:
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)

    # Enable text selection
    msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)

    return msg.exec()

import subprocess
import shutil

def show_notification(parent, title, text, duration=3000):
    """
    Shows a system-level notification using notify-send (FreeDesktop).
    """
    if shutil.which("notify-send"):
        try:
            # -t specifies timeout in ms. -a (app name).
            subprocess.run(["notify-send", "-a", "KPaperFlux", "-t", str(duration), title, text], check=False)
        except Exception as e:
            print(f"[ERROR] Failed to send system notification: {e}")
    else:
        # Fallback to console if notify-send is missing
        print(f"[Notification] {title}: {text}")
