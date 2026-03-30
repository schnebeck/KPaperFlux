"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_app_bus.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for the ApplicationBus event broker.
------------------------------------------------------------------------------
"""
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication

from gui.app_bus import ApplicationBus


class TestApplicationBus:
    """Tests for the ApplicationBus thin signal broker."""

    def test_bus_instantiates_cleanly(self, qapp) -> None:
        """ApplicationBus can be created without error."""
        bus = ApplicationBus()
        assert bus is not None
        bus.deleteLater()

    def test_bus_has_expected_signals(self) -> None:
        """ApplicationBus exposes the required signal attributes on the class."""
        assert hasattr(ApplicationBus, "metadata_saved"), (
            "ApplicationBus must define metadata_saved signal"
        )
        assert hasattr(ApplicationBus, "filter_changed"), (
            "ApplicationBus must define filter_changed signal"
        )

    def test_metadata_saved_signal_propagates(self, qapp) -> None:
        """Connecting a slot to bus.metadata_saved and emitting delivers the call."""
        bus = ApplicationBus()
        slot = MagicMock()

        bus.metadata_saved.connect(slot)
        bus.metadata_saved.emit()

        slot.assert_called_once()
        bus.deleteLater()

    def test_metadata_saved_multiple_subscribers(self, qapp) -> None:
        """All subscribers connected to bus.metadata_saved receive the emission."""
        bus = ApplicationBus()
        slot_a = MagicMock()
        slot_b = MagicMock()
        slot_c = MagicMock()

        bus.metadata_saved.connect(slot_a)
        bus.metadata_saved.connect(slot_b)
        bus.metadata_saved.connect(slot_c)
        bus.metadata_saved.emit()

        slot_a.assert_called_once()
        slot_b.assert_called_once()
        slot_c.assert_called_once()
        bus.deleteLater()

    def test_filter_changed_signal_propagates(self, qapp) -> None:
        """Connecting a slot to bus.filter_changed and emitting delivers the dict."""
        bus = ApplicationBus()
        received: list[dict] = []

        bus.filter_changed.connect(received.append)
        criteria = {"fulltext": "invoice", "status": "NEW"}
        bus.filter_changed.emit(criteria)

        assert len(received) == 1
        assert received[0] == criteria
        bus.deleteLater()

    def test_filter_changed_multiple_subscribers(self, qapp) -> None:
        """All subscribers connected to bus.filter_changed receive the same dict."""
        bus = ApplicationBus()
        slot_a = MagicMock()
        slot_b = MagicMock()

        bus.filter_changed.connect(slot_a)
        bus.filter_changed.connect(slot_b)
        criteria = {"status": "DONE"}
        bus.filter_changed.emit(criteria)

        slot_a.assert_called_once_with(criteria)
        slot_b.assert_called_once_with(criteria)
        bus.deleteLater()

    def test_bus_does_not_import_gui_widgets(self) -> None:
        """ApplicationBus must not depend on any gui sub-modules (only PyQt6)."""
        import importlib
        import sys

        # Reload the module in isolation to inspect its dependencies.
        # The module should only import from PyQt6.
        module = sys.modules.get("gui.app_bus")
        assert module is not None, "gui.app_bus must be importable"

        # Verify the module file imports nothing from gui.* (structural check)
        import inspect
        source = inspect.getsource(module)
        # Should not contain any "from gui." imports beyond the module itself
        lines = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("from gui.", "import gui."))
        ]
        assert lines == [], (
            f"ApplicationBus must not import from gui.*; found: {lines}"
        )
