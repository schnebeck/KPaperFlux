"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/gui/test_error_handler.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Unhandled exceptions are logged and shown instead of aborting.
------------------------------------------------------------------------------
"""
import sys
import threading
from unittest.mock import patch

from gui import error_handler


def _raise_and_handle():
    try:
        raise ValueError("synthetic failure")
    except ValueError:
        error_handler.handle_exception(*sys.exc_info())


def test_exception_in_gui_thread_is_logged_and_shown(qapp, caplog):
    with patch.object(error_handler.QMessageBox, "exec", return_value=0) as shown, \
         patch.object(error_handler.QMessageBox, "setDetailedText") as details:
        _raise_and_handle()

    shown.assert_called_once()
    assert "synthetic failure" in details.call_args.args[0]
    assert "Unhandled exception: ValueError: synthetic failure" in caplog.text


def test_exception_in_worker_thread_is_only_logged(qapp, caplog):
    with patch.object(error_handler.QMessageBox, "exec") as shown:
        worker = threading.Thread(target=_raise_and_handle)
        worker.start()
        worker.join()

    shown.assert_not_called()
    assert "synthetic failure" in caplog.text


def test_install_sets_the_hook():
    previous = sys.excepthook
    try:
        error_handler.install_exception_hook()
        assert sys.excepthook is error_handler.handle_exception
    finally:
        sys.excepthook = previous
