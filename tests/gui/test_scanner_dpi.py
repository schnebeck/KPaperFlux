"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/gui/test_scanner_dpi.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Scanner resolution default: 300 dpi for new or unset settings,
                the nearest offered resolution if the device lacks 300, and
                stored user choices respected. MockScanner only, no discovery.
------------------------------------------------------------------------------
"""

from typing import List
from unittest.mock import patch

import pytest

from core.scanner import MockScanner
from gui.scanner_dialog import DEFAULT_DPI, ScannerDialog, nearest_resolution


@pytest.mark.parametrize("available, target, expected", [
    ([75, 150, 200, 300, 600], 300, 300),
    ([100, 200, 400], 300, 400),        # tie: prefer the higher resolution
    ([75, 150, 200], 300, 200),
    ([600, 1200], 300, 600),
    ([], 300, None),
])
def test_nearest_resolution(available: List[int], target: int, expected: int) -> None:
    """The device's closest resolution is used."""
    assert nearest_resolution(available, target) == expected


@pytest.fixture
def dialog(qtbot) -> ScannerDialog:
    """Dialog on the MockScanner without background discovery and with fresh settings."""
    with patch("gui.scanner_dialog.get_scanner_driver", return_value=MockScanner()), \
         patch.object(ScannerDialog, "_start_discovery"):
        dlg = ScannerDialog()
    qtbot.addWidget(dlg)
    dlg.settings.remove("last_dpi")
    for source in ("Flatbed", "ADF"):
        dlg.settings.remove(f"last_dpi_{source}")
    return dlg


def _select_source(dlg: ScannerDialog, source: str, resolutions: List[int]) -> None:
    """Simulates the device capabilities for one source and selects it."""
    dlg.device_caps = {"sources": [source], "resolutions": {source: resolutions}}
    dlg.source_combo.clear()
    dlg.source_combo.addItem(source)
    dlg._on_source_changed(0)


def test_default_is_300_dpi(dialog: ScannerDialog) -> None:
    """New or unset settings scan with 300 dpi."""
    assert DEFAULT_DPI == 300
    _select_source(dialog, "Flatbed", [75, 150, 200, 300, 600])
    assert dialog.dpi_combo.currentData() == "300"


def test_nearest_when_300_is_not_offered(dialog: ScannerDialog) -> None:
    """A device without 300 dpi gets its closest resolution."""
    _select_source(dialog, "ADF", [75, 150, 200, 600])
    assert dialog.dpi_combo.currentData() == "200"


def test_stored_choice_is_respected(dialog: ScannerDialog) -> None:
    """An existing user's last_dpi stays in use."""
    dialog.settings.setValue("last_dpi", "150")
    _select_source(dialog, "Flatbed", [75, 150, 200, 300, 600])
    assert dialog.dpi_combo.currentData() == "150"
    dialog.settings.setValue("last_dpi_ADF", "600")
    _select_source(dialog, "ADF", [75, 150, 200, 300, 600])
    assert dialog.dpi_combo.currentData() == "600"
    dialog.settings.remove("last_dpi")
    dialog.settings.remove("last_dpi_ADF")
