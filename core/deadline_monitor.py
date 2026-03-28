"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/deadline_monitor.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Urgency-tier computation for document deadlines.
                Stateless helper: takes a date string, returns an UrgencyTier.
------------------------------------------------------------------------------
"""

from enum import IntEnum
from datetime import date, timedelta
from typing import Optional


class UrgencyTier(IntEnum):
    """
    Urgency tiers for deadline-based document classification.

    Integer values are intentionally ordered so that sorting ascending
    puts the most urgent documents first.
    """

    OVERDUE = 0   # deadline is in the past
    DUE_SOON = 1  # deadline within warning_days
    OK = 2        # deadline set but comfortably in the future
    NONE = 3      # no deadline field present


URGENCY_ICON: dict[UrgencyTier, str] = {
    UrgencyTier.OVERDUE:  "🔴",
    UrgencyTier.DUE_SOON: "🟡",
    UrgencyTier.OK:       "🟢",
    UrgencyTier.NONE:     "—",
}

URGENCY_TOOLTIP: dict[UrgencyTier, str] = {
    UrgencyTier.OVERDUE:  "Overdue",
    UrgencyTier.DUE_SOON: "Due soon",
    UrgencyTier.OK:       "OK",
    UrgencyTier.NONE:     "",
}


def compute_tier(date_str: Optional[str], warning_days: int = 7) -> UrgencyTier:
    """
    Compute the urgency tier for a document based on its deadline date.

    Args:
        date_str: ISO-format date string (YYYY-MM-DD or full ISO timestamp).
                  ``None`` or empty string → ``UrgencyTier.NONE``.
        warning_days: Days before the deadline that trigger ``DUE_SOON``.
                      Defaults to 7.

    Returns:
        UrgencyTier enum value.
    """
    if not date_str:
        return UrgencyTier.NONE
    try:
        due = date.fromisoformat(str(date_str)[:10])
    except ValueError:
        return UrgencyTier.NONE
    today = date.today()
    if due < today:
        return UrgencyTier.OVERDUE
    if due <= today + timedelta(days=warning_days):
        return UrgencyTier.DUE_SOON
    return UrgencyTier.OK
