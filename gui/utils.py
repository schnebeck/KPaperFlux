import subprocess
import shutil
from datetime import datetime, date
from typing import Optional

from PyQt6.QtCore import QLocale, QDate, QDateTime, QTime, Qt
from PyQt6.QtWidgets import QMessageBox

from core.logger import get_logger
from core.utils.formatting import format_date as _core_format_date

logger = get_logger("gui.utils")


def format_date(d: Optional[str | date | datetime]) -> str:
    """
    Format a date object (or ISO string) to a localized string (e.g. 31.12.2024).
    Delegates to core.utils.formatting using the Qt system locale.
    """
    if not d:
        return ""
    locale_name = QLocale.system().name()  # e.g. "de_DE"
    val_str = d.isoformat() if isinstance(d, (date, datetime)) else str(d)
    result = _core_format_date(val_str, locale=locale_name)
    return "" if result == "---" else result


def format_datetime(dt: Optional[str | date | datetime]) -> str:
    """
    Format a datetime object (or ISO string) to a localized string (e.g. 31.12.2024 14:30:00).
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
        dt = QDateTime(
            QDate(dt.year, dt.month, dt.day),
            QTime(dt.hour, dt.minute, dt.second)
        )
    elif isinstance(dt, date):
        dt = QDate(dt.year, dt.month, dt.day)

    return locale.toString(dt, "dd.MM.yyyy HH:mm:ss")


def show_selectable_message_box(
    parent: Optional[object],
    title: str,
    text: str,
    icon: Optional[QMessageBox.Icon] = None,
    buttons: Optional[QMessageBox.StandardButton] = None,
) -> int:
    """
    Shows a QMessageBox with text selection enabled.
    Supports both positional and keyword arguments for icon and buttons.
    """
    msg = QMessageBox(parent)
    if title:
        msg.setWindowTitle(title)
    if text:
        msg.setText(text)

    # Handle case where icon might be buttons (if called from old QMessageBox sites)
    if isinstance(icon, QMessageBox.StandardButton):
        if buttons is None:
            buttons = icon
            icon = QMessageBox.Icon.NoIcon

    if icon:
        msg.setIcon(icon)
    if buttons:
        msg.setStandardButtons(buttons)
    else:
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)

    msg.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.LinksAccessibleByMouse
    )

    return msg.exec()


def show_notification(parent: Optional[object], title: str, text: str, duration: int = 3000) -> None:
    """
    Shows a system-level notification using notify-send (FreeDesktop).
    Falls back to logging if notify-send is unavailable.
    """
    if shutil.which("notify-send"):
        try:
            subprocess.run(
                ["notify-send", "-a", "KPaperFlux", "-t", str(duration), title, text],
                check=False,
            )
        except Exception as e:
            logger.warning(f"Failed to send system notification: {e}")
    else:
        logger.info(f"[Notification] {title}: {text}")
