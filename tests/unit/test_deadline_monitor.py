"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_deadline_monitor.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for core.deadline_monitor.compute_tier().
------------------------------------------------------------------------------
"""

from datetime import date, timedelta

import pytest

from core.deadline_monitor import UrgencyTier, compute_tier, URGENCY_ICON


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(delta_days: int) -> str:
    """Return ISO date string for today + delta_days."""
    return (date.today() + timedelta(days=delta_days)).isoformat()


# ---------------------------------------------------------------------------
# compute_tier — basic cases
# ---------------------------------------------------------------------------

class TestComputeTier:

    def test_none_input_returns_none_tier(self):
        assert compute_tier(None) == UrgencyTier.NONE

    def test_empty_string_returns_none_tier(self):
        assert compute_tier("") == UrgencyTier.NONE

    def test_invalid_string_returns_none_tier(self):
        assert compute_tier("not-a-date") == UrgencyTier.NONE

    def test_past_date_is_overdue(self):
        assert compute_tier(_iso(-1)) == UrgencyTier.OVERDUE

    def test_far_past_date_is_overdue(self):
        assert compute_tier(_iso(-365)) == UrgencyTier.OVERDUE

    def test_today_is_due_soon(self):
        # Due today = within warning window
        assert compute_tier(_iso(0)) == UrgencyTier.DUE_SOON

    def test_within_warning_window_is_due_soon(self):
        assert compute_tier(_iso(7)) == UrgencyTier.DUE_SOON

    def test_just_outside_warning_window_is_ok(self):
        assert compute_tier(_iso(8)) == UrgencyTier.OK

    def test_far_future_date_is_ok(self):
        assert compute_tier(_iso(365)) == UrgencyTier.OK

    def test_custom_warning_days(self):
        assert compute_tier(_iso(14), warning_days=14) == UrgencyTier.DUE_SOON
        assert compute_tier(_iso(15), warning_days=14) == UrgencyTier.OK

    def test_full_iso_timestamp_is_accepted(self):
        """Timestamps like '2025-02-14T00:00:00' must be handled (slice to 10 chars)."""
        assert compute_tier("2000-01-01T12:00:00") == UrgencyTier.OVERDUE


# ---------------------------------------------------------------------------
# UrgencyTier sorting order
# ---------------------------------------------------------------------------

class TestUrgencyTierSorting:

    def test_overdue_sorts_before_due_soon(self):
        assert UrgencyTier.OVERDUE < UrgencyTier.DUE_SOON

    def test_due_soon_sorts_before_ok(self):
        assert UrgencyTier.DUE_SOON < UrgencyTier.OK

    def test_ok_sorts_before_none(self):
        assert UrgencyTier.OK < UrgencyTier.NONE


# ---------------------------------------------------------------------------
# URGENCY_ICON coverage
# ---------------------------------------------------------------------------

class TestUrgencyIcon:

    def test_all_tiers_have_icon(self):
        for tier in UrgencyTier:
            assert tier in URGENCY_ICON

    def test_none_tier_icon_is_dash(self):
        assert URGENCY_ICON[UrgencyTier.NONE] == "—"
