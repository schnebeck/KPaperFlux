"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/integration/test_scan_import_path.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Scan path end to end: MockScanner (returning a generated,
                image-only scan from fluxsense.testdata, recorded seed, plus an
                ADF blank page) -> ScannerDialog result -> start_import_process
                -> ImportWorker -> Stage 0 -> FluxSense (mocked, answering from
                the generator's ground truth) -> adapter -> database. Checks the
                split, engine page text as full text, search and the blank-page
                purge. No modal dialogs.
------------------------------------------------------------------------------
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import fitz
import pytest
from PyQt6.QtWidgets import QDialog

from core.canonizer import CanonizerService
from core.database import DatabaseManager
from core.engines.fluxsense_client import FluxSenseClient
from core.models.virtual import DocumentStatus
from core.pipeline import PipelineProcessor
from core.scanner import MockScanner
from core.vault import DocumentVault
from tests.generated_docs import SEED_STACK, append_blank_page, generate, page_texts


@pytest.fixture
def generated_scan(tmp_path: Path) -> Any:
    """Generated scan-variant stack (letter 2 pages + enclosure 1 page), image-only."""
    gen = generate(tmp_path / "gen", "stack", SEED_STACK, scan=True)
    with fitz.open(str(gen.path)) as doc:
        assert all(not doc[i].get_text().strip() for i in range(doc.page_count))  # no text layer
    return gen


class GeneratedPagesScanner(MockScanner):
    """MockScanner whose ADF returns the pages of a given PDF (one file per page, like a real scan)."""

    def __init__(self, source_pdf: Path, workdir: Path) -> None:
        self.source_pdf = source_pdf
        self.workdir = workdir

    def scan_pages(self, device_name: str, dpi: int = 300, color_mode: str = "Color", source: str = "ADF",
                   duplex_mode: str = "LongEdge", page_format: str = "A4", progress_callback: Any = None) -> List[str]:
        paths: List[str] = []
        with fitz.open(str(self.source_pdf)) as src:
            for index in range(src.page_count):
                out = fitz.open()
                out.insert_pdf(src, from_page=index, to_page=index)
                path = self.workdir / f"scan_page_{index + 1}.pdf"
                out.save(str(path))
                out.close()
                paths.append(str(path))
                if progress_callback:
                    progress_callback(index + 1, src.page_count)
        return paths


class TruthEngine(FluxSenseClient):
    """FluxSense stand-in: answers from the generator's ground truth (segmentation, fields, page text)."""

    mode = "fake"

    def __init__(self, generated: Any) -> None:
        self.generated = generated
        self.calls: List[int] = []

    def analyze(self, pdf_path: Path) -> Dict[str, Any]:
        with fitz.open(str(pdf_path)) as doc:
            pages = doc.page_count
        self.calls.append(pages)
        docs, texts, first = [], [], 1
        if pages == 1 and len(self.calls) > 1:  # the separated blank page
            return self._result([{"type": "OTHER", "pages": [1], "fields": {"meta_header": {}, "bodies": {}}}], [""])
        for doc in self.generated.docs:
            count = len(doc.pages)
            truth = doc.truth
            docs.append({
                "type": doc.doc_types[0], "pages": list(range(first, first + count)),
                "fields": {"meta_header": {"sender": {"company": truth.get("sender")},
                                           "recipient": {"name": truth.get("recipient")},
                                           "doc_date": truth.get("doc_date"), "doc_number": truth.get("doc_number")},
                           "bodies": {"correspondence_body": {"subject": doc.summary}}},
            })
            texts += page_texts(doc)
            first += count
        texts += [""] * (pages - len(texts))  # trailing blank page: no text, in no document
        return self._result(docs, texts)

    @staticmethod
    def _result(docs: List[Dict[str, Any]], texts: List[str]) -> Dict[str, Any]:
        logical = []
        for index, doc in enumerate(docs):
            entry = {"index": index, "type_tags": [doc["type"]], "direction": "INBOUND", "tenant_context": "PRIVATE",
                     "confidence": 0.9, "evidence": [], "trust": {"score": 0.9}, "errors": [], "tables": [],
                     "plausibility": {"status": "PASS", "score": 1.0, "checks": []}}
            entry.update(doc)
            logical.append(entry)
        return {"fluxsense_version": "test", "status": "OK", "error_code": None, "logical_documents": logical,
                "text_layer": {"engine": "fake", "pages": [{"page": i + 1, "text": t, "source": "ocr"} for i, t in enumerate(texts)]}}

    def health(self) -> Dict[str, Any]:
        return {"status": "ok", "llm_backend": True}

    def server_url(self) -> Optional[str]:
        return "http://ai.test/v1"

    def complete_json(self, prompt: str, label: str) -> Any:
        return None


class AcceptingSplitter:
    """SplitterDialog stand-in: the user accepts the given split without a modal dialog."""

    instructions: List[Dict[str, Any]] = []

    def __init__(self, pipeline: Any, parent: Any = None) -> None:
        self.import_instructions: List[Dict[str, Any]] = []

    def load_for_batch_import(self, file_infos: List[Dict[str, Any]]) -> None:
        path = file_infos[0]["path"]
        self.import_instructions = [
            {"pages": [{"file_path": path, "file_uuid": None, "file_page_index": i, "rotation": 0,
                        "is_protected": False, "pdf_class": "C"} for i in group], "locked": False}
            for group in AcceptingSplitter.instructions
        ]

    def exec(self) -> int:
        return QDialog.DialogCode.Accepted


@pytest.fixture
def app_window(qtbot, tmp_path: Path) -> Any:
    """MainWindow on a temporary vault and database (background worker disabled)."""
    from gui.main_window import MainWindow
    db = DatabaseManager(str(tmp_path / "kpf.db"))
    db.init_db()
    pipeline = PipelineProcessor(vault=DocumentVault(tmp_path / "vault"), db=db)
    with patch("gui.main_window.MainLoopWorker"):
        window = MainWindow(pipeline=pipeline, db_manager=db)
    qtbot.addWidget(window)
    return window


def _scan(qtbot, scanner: MockScanner) -> str:
    """Runs the real ScannerDialog scan on the given driver (ADF) and returns its result file."""
    from gui.scanner_dialog import ScannerDialog
    with patch("gui.scanner_dialog.get_scanner_driver", return_value=scanner), \
         patch.object(ScannerDialog, "_start_discovery"):
        dialog = ScannerDialog()
    qtbot.addWidget(dialog)
    dialog.device_combo.addItem("Mock Scanner", "mock:1")
    dialog.source_combo.addItem("ADF")
    dialog.dpi_combo.addItem("300 dpi", "300")
    with qtbot.waitSignal(dialog.accepted, timeout=30000):
        dialog.start_scan()
    return dialog.get_scanned_file()


def _import_and_analyze(qtbot, window: Any, path: str, generated: Any, groups: List[List[int]]) -> TruthEngine:
    """start_import_process -> ImportWorker -> Stage 0, then the canonizer with the truth engine."""
    AcceptingSplitter.instructions = groups
    with patch("gui.splitter_dialog.SplitterDialog", AcceptingSplitter), \
         patch("gui.utils.show_notification"), patch("gui.utils.show_selectable_message_box"):
        window.start_import_process([path], move_source=True)
        qtbot.waitUntil(lambda: window.doc_controller.import_worker is None, timeout=30000)
    engine = TruthEngine(generated)
    with patch("core.canonizer.AppConfig", MagicMock()):
        canonizer = CanonizerService(window.pipeline.db, engine_client=engine,
                                     physical_repo=window.pipeline.physical_repo, logical_repo=window.pipeline.logical_repo)
    while canonizer.process_pending_documents(limit=1):
        pass
    return engine


def _search_word(generated: Any) -> str:
    """A long word printed only in the first logical document (from the generator's page text)."""
    other = " ".join(" ".join(page_texts(d)) for d in generated.docs[1:])
    for word in re.findall(r"[A-Za-zÄÖÜäöüß]{8,}", " ".join(page_texts(generated.docs[0]))):
        if word not in other:
            return word
    pytest.skip("generated document has no distinctive word")


def test_scan_to_database_with_engine_text_and_split(qtbot, tmp_path: Path, app_window: Any, generated_scan: Any) -> None:
    """Whole ADF scan as one entity: split per the engine, full text from the engine, searchable; blank page in no document."""
    scan_with_blank = append_blank_page(generated_scan.path, tmp_path / "with_blank.pdf")
    scanned = _scan(qtbot, GeneratedPagesScanner(scan_with_blank, tmp_path))
    pages_total = sum(len(d.pages) for d in generated_scan.docs) + 1  # documents + blank page

    _import_and_analyze(qtbot, app_window, scanned, generated_scan, [list(range(pages_total))])

    db = app_window.pipeline.db
    docs = sorted(db.get_all_documents(), key=lambda d: d.source_mapping[0].pages[0])
    expected_ranges = [entry["pages"] for entry in generated_scan.entry["logical_documents"]]
    assert [[p for ref in d.source_mapping for p in ref.pages] for d in docs] == expected_ranges
    assert all(d.status == DocumentStatus.PROCESSED for d in docs)
    assert all(pages_total not in ref.pages for d in docs for ref in d.source_mapping)  # blank page in no document
    for doc, generated_doc in zip(docs, generated_scan.docs):
        assert doc.cached_full_text == "\n".join(page_texts(generated_doc))
        if generated_doc.truth.get("doc_number"):
            assert doc.doc_number == generated_doc.truth["doc_number"]

    word = _search_word(generated_scan)
    assert [d.uuid for d in db.search_documents(word)] == [docs[0].uuid]


def test_separated_adf_blank_page_is_purged(qtbot, tmp_path: Path, app_window: Any, generated_scan: Any) -> None:
    """A blank last page split off as its own entity has no text after the engine and is purged."""
    scan_with_blank = append_blank_page(generated_scan.path, tmp_path / "with_blank.pdf")
    scanned = _scan(qtbot, GeneratedPagesScanner(scan_with_blank, tmp_path))
    doc_pages = sum(len(d.pages) for d in generated_scan.docs)

    engine = _import_and_analyze(qtbot, app_window, scanned, generated_scan,
                                 [list(range(doc_pages)), [doc_pages]])

    db = app_window.pipeline.db
    remaining = db.get_all_documents()
    assert engine.calls == [doc_pages, 1]  # both entities went through the engine
    assert len(remaining) == len(generated_scan.docs)
    assert all(doc_pages + 1 not in ref.pages for d in remaining for ref in d.source_mapping)
    assert db.get_pending_pipeline_count() == 0
