"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/gui/test_worker_shutdown.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Worker threads are stopped cooperatively, never terminated, and
                closing the window waits for a running analysis step.
------------------------------------------------------------------------------
"""
import threading

import pytest
from PyQt6.QtCore import QThread

from core.database import DatabaseManager
from gui import workers
from gui.main_window import MainWindow


class SlowWorker(QThread):
    """Runs until released; ignores cancel() for a while like a long engine call."""

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True

    def run(self) -> None:
        self.release.wait(5)


def test_stop_thread_never_terminates(qtbot):
    worker = SlowWorker()
    worker.start()

    assert workers.stop_thread(worker, wait_ms=50) is False
    assert worker.cancel_requested and worker.isRunning()
    assert worker in workers._detached_threads

    worker.release.set()
    qtbot.waitUntil(lambda: worker not in workers._detached_threads, timeout=3000)


def test_stop_thread_returns_when_worker_ends(qtbot):
    worker = SlowWorker()
    worker.release.set()
    worker.start()
    assert workers.stop_thread(worker, wait_ms=2000) is True


class FakeLoop:
    """Stands in for MainLoopWorker during a long analysis step."""

    def __init__(self) -> None:
        self.running = True
        self.stopped = False

    def isRunning(self) -> bool:
        return self.running

    def stop(self) -> None:
        self.stopped = True

    def wait(self, ms: int) -> bool:
        return not self.running


@pytest.fixture
def window(qtbot, tmp_path):
    db = DatabaseManager(str(tmp_path / "close.db"))
    db.init_db()
    mw = MainWindow(pipeline=None, db_manager=db)
    qtbot.addWidget(mw)
    mw.show()
    return mw


def test_close_waits_for_running_analysis_step(window, qapp):
    loop = FakeLoop()
    window.main_loop_worker = loop

    window.close()

    assert loop.stopped
    assert not window.isVisible()
    assert window._close_timer is not None and window._close_timer.isActive()
    assert not qapp.quitOnLastWindowClosed()

    loop.running = False
    window._close_when_idle()

    assert not window._close_timer.isActive()
    assert qapp.quitOnLastWindowClosed()


def test_similarity_search_can_be_cancelled(qtbot):
    from unittest.mock import MagicMock, patch

    calls = []

    def find_duplicates(threshold, progress_callback):
        for i in range(1000):
            progress_callback(i, 1000)
            calls.append(i)
        return [("a", "b", 1.0)]

    with patch("gui.workers.SimilarityManager") as manager_cls:
        manager_cls.return_value.find_duplicates.side_effect = find_duplicates
        worker = workers.SimilarityWorker(MagicMock(), MagicMock())
    worker.cancel()
    results = []
    worker.finished.connect(results.append)

    worker.run()  # synchronously

    assert results == [[]]
    assert calls == []
