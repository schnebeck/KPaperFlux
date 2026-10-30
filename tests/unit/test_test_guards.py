"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_test_guards.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    The test suite never touches the user's real home directory and
                fails fast instead of blocking on a modal dialog.
------------------------------------------------------------------------------
"""
import os
from pathlib import Path

import pytest
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QDialog, QMessageBox


def test_home_and_config_are_isolated() -> None:
    home = Path(os.environ["HOME"])
    config = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.ConfigLocation))
    assert home.name.startswith("kpaperflux-test-home-")
    assert home in config.parents


def test_unexpected_message_box_fails_fast(qapp) -> None:
    with pytest.raises(AssertionError, match="Unexpected modal dialog"):
        QMessageBox.question(None, "Title", "Text")


def test_unexpected_dialog_exec_fails_fast(qapp) -> None:
    with pytest.raises(AssertionError, match="Unexpected modal dialog"):
        QDialog().exec()
