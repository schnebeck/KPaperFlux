"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/error_handler.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Global handler for unhandled exceptions: PyQt6 aborts the
                application on an exception in a slot unless sys.excepthook
                handles it. The handler logs it and informs the user.
------------------------------------------------------------------------------
"""
import sys
import threading
import traceback
from types import TracebackType
from typing import Optional, Type

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.logger import get_logger

logger = get_logger("gui.error_handler")

_showing_dialog = False


def handle_exception(exc_type: Type[BaseException], exc: BaseException,
                     tb: Optional[TracebackType]) -> None:
    """
    Logs an unhandled exception and, in the GUI thread, shows it in a dialog.
    The application keeps running.
    """
    global _showing_dialog
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    logger.critical(f"Unhandled exception: {exc_type.__name__}: {exc}", exc_info=(exc_type, exc, tb))

    if (QApplication.instance() is None or _showing_dialog
            or threading.current_thread() is not threading.main_thread()):
        return
    _showing_dialog = True
    try:
        title = QCoreApplication.translate("ErrorHandler", "Unexpected Error")
        text = QCoreApplication.translate(
            "ErrorHandler", "An unexpected error occurred. The application keeps running, "
                            "but the last action may be incomplete.\n\n%s") % f"{exc_type.__name__}: {exc}"
        box = QMessageBox(QMessageBox.Icon.Critical, title, text)
        box.setDetailedText("".join(traceback.format_exception(exc_type, exc, tb)))
        box.exec()
    finally:
        _showing_dialog = False


def install_exception_hook() -> None:
    """Installs handle_exception as sys.excepthook."""
    sys.excepthook = handle_exception
