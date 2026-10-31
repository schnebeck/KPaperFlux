"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/gui/test_report_worker_lifecycle.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Report workers are released only after their thread has ended;
                hiding the view drops stale results without killing threads.
------------------------------------------------------------------------------
"""
import threading
from unittest.mock import MagicMock

import pytest

from core.database import DatabaseManager
from core.models.reporting import ReportComponent, ReportDefinition
from gui import workers
from gui.reporting import ReportingWidget


@pytest.fixture
def widget(qtbot):
    db = MagicMock(spec=DatabaseManager)
    db.search_documents_advanced.return_value = []
    w = ReportingWidget(db_manager=db)
    qtbot.addWidget(w)
    return w


def _definition() -> ReportDefinition:
    return ReportDefinition(id="r1", name="Synthetic", components=[ReportComponent(type="table")])


def test_finished_report_is_rendered_and_released(widget, qtbot):
    widget.repo_gen = MagicMock()
    widget.repo_gen.run_custom_report.return_value = {
        "title": "SYNTH_TITLE", "labels": [], "series": [], "table_rows": [{"x": 1}]}
    rendered = []
    widget.render_report = lambda results, definition, **kw: rendered.append(results["title"])

    widget._generate_report_for_definition(_definition())

    qtbot.waitUntil(lambda: not widget.pending_workers, timeout=3000)
    assert rendered == ["SYNTH_TITLE"]


def test_hiding_drops_stale_results_without_killing_the_thread(widget, qtbot):
    release = threading.Event()

    def slow_report(db, definition):
        release.wait(3)
        return {"title": "STALE", "labels": [], "series": [], "table_rows": []}
    widget.repo_gen = MagicMock()
    widget.repo_gen.run_custom_report.side_effect = slow_report
    rendered = []
    widget.render_report = lambda results, definition, **kw: rendered.append(results["title"])
    widget._generate_report_for_definition(_definition())
    worker = widget.pending_workers[0]

    widget._stop_all_workers()  # what hideEvent does
    assert worker.isRunning()
    assert worker in workers._detached_threads

    release.set()
    qtbot.waitUntil(lambda: worker not in workers._detached_threads, timeout=3000)
    assert rendered == []
