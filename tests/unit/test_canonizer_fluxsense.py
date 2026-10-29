"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_canonizer_fluxsense.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Pipeline tests: Stage 0 entity -> FluxSense (mocked client)
                -> adapter -> persisted VirtualDocuments. Uses an in-memory
                database, real repositories and a small generated PDF.
------------------------------------------------------------------------------
"""

import copy
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import fitz
import pytest

from core.canonizer import CanonizerService, generate_smart_filename
from core.database import DatabaseManager
from core.engines.fluxsense_client import FluxSenseClient, FluxSenseError
from core.models.physical import PhysicalFile
from core.models.semantic import FinanceBody, SemanticExtraction, StatementBody
from core.models.virtual import DocumentStatus, SourceReference, VirtualDocument

FIXTURE = Path(__file__).parent.parent / "resources" / "fluxsense" / "synthetic_stack_result.json"


@pytest.fixture
def stack_result() -> Dict[str, Any]:
    """Synthetic 5-page FluxSense result: invoice (1-2), statement (3-4), letter (5)."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def db() -> DatabaseManager:
    """In-memory database with the full schema."""
    manager = DatabaseManager(":memory:")
    manager.init_db()
    return manager


@pytest.fixture
def physical_pdf(tmp_path: Path) -> Path:
    """A 5-page PDF standing in for a vault original."""
    path = tmp_path / "vault" / "file-a.pdf"
    path.parent.mkdir()
    doc = fitz.open()
    for index in range(5):
        page = doc.new_page()
        page.insert_text((72, 72), f"page {index + 1}")
    doc.save(str(path))
    doc.close()
    return path


class FakeClient(FluxSenseClient):
    """Records analyzed PDFs and replays prepared outcomes: a result dict, (result, page_texts) or an exception."""

    mode = "fake"

    def __init__(self, outcomes: List[Any]) -> None:
        self.outcomes = list(outcomes)
        self.analyzed: List[Dict[str, Any]] = []

    def analyze(self, pdf_path: Path) -> Dict[str, Any]:
        with fitz.open(str(pdf_path)) as doc:
            self.analyzed.append({"path": Path(pdf_path), "pages": doc.page_count,
                                  "texts": [doc[i].get_text().strip() for i in range(doc.page_count)]})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, tuple):
            result = copy.deepcopy(outcome[0])
            result["text_layer"]["pages"] = [{"page": i + 1, "text": t, "source": "ovis"} for i, t in enumerate(outcome[1])]
            return result
        return copy.deepcopy(outcome)

    def health(self) -> Dict[str, Any]:
        return {"status": "ok", "llm_backend": True}

    def server_url(self) -> str:
        return "http://ai-server.test:8080/v1"

    def complete_json(self, prompt: str, label: str) -> Any:
        return None


def _service(db: DatabaseManager, client: FakeClient) -> CanonizerService:
    """CanonizerService with real repositories and an isolated config."""
    with patch("core.canonizer.AppConfig", MagicMock()):
        return CanonizerService(db, engine_client=client)


def _ingest(service: CanonizerService, pdf: Path, pages: List[int], status: str = DocumentStatus.NEW,
            **doc_fields: Any) -> VirtualDocument:
    """Stores the physical file (with Stage 0 text) and one logical document."""
    service.physical_repo.save(PhysicalFile(
        uuid="file-a", original_filename="scan.pdf", file_path=str(pdf), page_count_phys=5,
        raw_ocr_data={str(i): f"stage0 text {i}" for i in range(1, 6)}))
    v_doc = VirtualDocument(uuid="doc-1", status=status, source_mapping=[SourceReference(file_uuid="file-a", pages=pages)],
                            **doc_fields)
    service.logical_repo.save(v_doc)
    return service.logical_repo.get_by_uuid("doc-1")


def _all_docs(service: CanonizerService) -> List[VirtualDocument]:
    """All persisted logical documents ordered by their first physical page."""
    rows = service.db.connection.execute("SELECT uuid FROM virtual_documents").fetchall()
    docs = [service.logical_repo.get_by_uuid(row[0]) for row in rows]
    return sorted(docs, key=lambda d: d.source_mapping[0].pages[0])


# ------------------------------------------------------------------ happy path

def test_stack_is_split_into_logical_documents(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any]) -> None:
    """One scanned stack becomes three processed documents with engine review state."""
    client = FakeClient([stack_result])
    service = _service(db, client)
    v_doc = _ingest(service, physical_pdf, [1, 2, 3, 4, 5])

    assert service.process_virtual_document(v_doc) is True

    assert client.analyzed[0]["path"] == physical_pdf  # whole file: vault original, no copy
    docs = _all_docs(service)
    assert [d.source_mapping[0].pages for d in docs] == [[1, 2], [3, 4], [5]]
    assert docs[0].uuid == "doc-1"
    assert all(d.status == DocumentStatus.PROCESSED for d in docs)
    invoice, statement, letter = docs
    assert invoice.type_tags == ["INVOICE", "INBOUND", "CTX_PRIVATE"]
    assert isinstance(invoice.semantic_data.bodies["finance_body"], FinanceBody)
    assert isinstance(statement.semantic_data.bodies["statement_body"], StatementBody)
    assert invoice.ai_confidence == pytest.approx(0.88)
    assert invoice.semantic_data.engine.name == "fluxsense"
    assert invoice.semantic_data.engine.field_state("bodies.finance_body.due_date").auto_accepted is False
    assert invoice.semantic_data.visual_audit.meta_mode == "NONE"
    assert invoice.export_filename == "2026-03-14__Muster_Elektro_GmbH__INVOICE.pdf"
    assert invoice.cached_full_text == "stage0 text 1\nstage0 text 2"
    assert letter.cached_full_text == "stage0 text 5"
    assert invoice.sender_name == "Muster Elektro GmbH"
    assert invoice.total_gross is not None and float(invoice.total_gross) == 357.0


def test_partial_selection_is_stitched_and_mapped_back(db: DatabaseManager, physical_pdf: Path,
                                                       stack_result: Dict[str, Any]) -> None:
    """A document covering pages 3-4 of a file is analyzed as a 2-page copy."""
    statement_only = copy.deepcopy(stack_result)
    statement_only["logical_documents"] = [statement_only["logical_documents"][1]]
    statement_only["logical_documents"][0]["pages"] = [1, 2]
    client = FakeClient([statement_only])
    service = _service(db, client)
    v_doc = _ingest(service, physical_pdf, [3, 4])

    assert service.process_virtual_document(v_doc) is True
    assert client.analyzed[0]["pages"] == 2
    assert client.analyzed[0]["texts"] == ["page 3", "page 4"]
    assert client.analyzed[0]["path"] != physical_pdf
    assert not client.analyzed[0]["path"].exists()  # temporary copy removed
    doc = service.logical_repo.get_by_uuid("doc-1")
    assert doc.source_mapping[0].pages == [3, 4]
    assert doc.status == DocumentStatus.PROCESSED


def test_protected_document_is_not_split(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any]) -> None:
    """Immutable documents keep all pages in one entity."""
    service = _service(db, FakeClient([stack_result]))
    v_doc = _ingest(service, physical_pdf, [1, 2, 3, 4, 5], is_immutable=True)
    assert service.process_virtual_document(v_doc) is True
    docs = _all_docs(service)
    assert len(docs) == 1
    assert docs[0].source_mapping[0].pages == [1, 2, 3, 4, 5]
    assert docs[0].type_tags[0] == "INVOICE"


def test_reextraction_keeps_page_range(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any]) -> None:
    """STAGE2_PENDING ('Run Extraction') refreshes fields without re-segmentation."""
    service = _service(db, FakeClient([stack_result]))
    v_doc = _ingest(service, physical_pdf, [1, 2, 3, 4, 5], status=DocumentStatus.STAGE2_PENDING)
    assert service.process_virtual_document(v_doc) is True
    docs = _all_docs(service)
    assert len(docs) == 1 and docs[0].status == DocumentStatus.PROCESSED


def test_queue_processing_end_to_end(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any]) -> None:
    """The background loop entry point locks, analyzes and stores documents."""
    service = _service(db, FakeClient([stack_result]))
    _ingest(service, physical_pdf, [1, 2, 3, 4, 5], status=DocumentStatus.READY_FOR_PIPELINE)
    assert service.process_pending_documents(limit=5) == 1
    assert len(_all_docs(service)) == 3
    assert db.get_pending_pipeline_count() == 0


# ------------------------------------------------------------------ failures

def test_unreachable_engine_holds_document_and_retry_succeeds(db: DatabaseManager, physical_pdf: Path,
                                                               stack_result: Dict[str, Any]) -> None:
    """Backend down: clear error state, no crash; 'Reprocess' later succeeds."""
    client = FakeClient([FluxSenseError("FluxSense service unreachable", "BACKEND_UNREACHABLE"), stack_result])
    service = _service(db, client)
    v_doc = _ingest(service, physical_pdf, [1, 2, 3, 4, 5])

    assert service.process_virtual_document(v_doc) is False
    held = service.logical_repo.get_by_uuid("doc-1")
    assert held.status == DocumentStatus.STAGE1_HOLD
    assert held.semantic_data.engine.status == "ERROR"
    assert "not reachable" in held.semantic_data.engine.errors[0]
    assert held.source_mapping[0].pages == [1, 2, 3, 4, 5]
    assert db.get_pending_pipeline_count() == 0  # no busy retry loop

    db.reset_document_for_reanalysis("doc-1")  # what 'Reprocess / Re-Analyze' does
    assert service.process_pending_documents(limit=5) == 1
    assert [d.status for d in _all_docs(service)] == [DocumentStatus.PROCESSED] * 3


def test_engine_error_status_holds_document(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any]) -> None:
    """A FluxSense result with status ERROR is not applied."""
    failed = copy.deepcopy(stack_result)
    failed["status"] = "ERROR"
    failed["errors"] = ["PDF has no pages"]
    service = _service(db, FakeClient([failed]))
    v_doc = _ingest(service, physical_pdf, [1, 2, 3, 4, 5])
    assert service.process_virtual_document(v_doc) is False
    held = service.logical_repo.get_by_uuid("doc-1")
    assert held.status == DocumentStatus.STAGE1_HOLD
    assert "PDF has no pages" in held.semantic_data.engine.errors


def test_failed_reextraction_keeps_existing_data(db: DatabaseManager, physical_pdf: Path) -> None:
    """A failed re-extraction goes to STAGE2_HOLD and keeps the previous fields."""
    service = _service(db, FakeClient([FluxSenseError("timeout", "BACKEND_TIMEOUT")]))
    previous = SemanticExtraction(meta_header={"doc_number": "KEEP-1"})
    v_doc = _ingest(service, physical_pdf, [1, 2], status=DocumentStatus.STAGE2_PENDING, semantic_data=previous)
    assert service.process_virtual_document(v_doc) is False
    held = service.logical_repo.get_by_uuid("doc-1")
    assert held.status == DocumentStatus.STAGE2_HOLD
    assert held.semantic_data.meta_header.doc_number == "KEEP-1"
    assert held.semantic_data.engine.status == "ERROR"


def test_failed_logical_document_is_held_others_processed(db: DatabaseManager, physical_pdf: Path,
                                                          stack_result: Dict[str, Any]) -> None:
    """PARTIAL result: the failed part waits on hold, the rest is processed."""
    partial = copy.deepcopy(stack_result)
    partial["status"] = "PARTIAL"
    partial["logical_documents"][2]["fields"] = {}
    partial["logical_documents"][2]["errors"] = ["Stage 2 extraction failed"]
    service = _service(db, FakeClient([partial]))
    v_doc = _ingest(service, physical_pdf, [1, 2, 3, 4, 5])
    assert service.process_virtual_document(v_doc) is True
    assert [d.status for d in _all_docs(service)] == [
        DocumentStatus.PROCESSED, DocumentStatus.PROCESSED, DocumentStatus.STAGE2_HOLD]


def test_missing_vault_file_holds_document(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any]) -> None:
    """A stitched input whose source is gone is an error state, not a crash."""
    service = _service(db, FakeClient([stack_result]))
    v_doc = _ingest(service, physical_pdf, [2, 3])
    physical_pdf.unlink()
    assert service.process_virtual_document(v_doc) is False
    assert service.logical_repo.get_by_uuid("doc-1").status == DocumentStatus.STAGE1_HOLD


def test_no_logical_documents_marks_processed(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any]) -> None:
    """FluxSense found nothing: the document is processed without semantic data."""
    stack_result["logical_documents"] = []
    service = _service(db, FakeClient([stack_result]))
    v_doc = _ingest(service, physical_pdf, [1, 2, 3, 4, 5])
    assert service.process_virtual_document(v_doc) is True
    assert service.logical_repo.get_by_uuid("doc-1").status == DocumentStatus.PROCESSED


def test_blank_document_is_discarded_after_analysis(db: DatabaseManager, physical_pdf: Path,
                                                    stack_result: Dict[str, Any]) -> None:
    """Empty-text gate runs after the engine: a trailing page without any text is purged."""
    blank = copy.deepcopy(stack_result)
    blank["logical_documents"] = [blank["logical_documents"][2]]
    blank["logical_documents"][0]["pages"] = [1]
    client = FakeClient([(blank, ["   "])])
    service = _service(db, client)
    service.physical_repo.save(PhysicalFile(uuid="file-a", original_filename="scan.pdf", file_path=str(physical_pdf),
                                            page_count_phys=5, raw_ocr_data={}))
    v_doc = VirtualDocument(uuid="doc-1", source_mapping=[SourceReference(file_uuid="file-a", pages=[5])])
    service.logical_repo.save(v_doc)
    assert service.process_virtual_document(v_doc) is True
    assert len(client.analyzed) == 1
    assert service.logical_repo.get_by_uuid("doc-1") is None


def test_document_without_pages_is_skipped(db: DatabaseManager) -> None:
    """A document whose source has no pages (e.g. an unreadable file) is not left locked."""
    client = FakeClient([])
    service = _service(db, client)
    v_doc = VirtualDocument(uuid="doc-1", source_mapping=[])
    service.logical_repo.save(v_doc)
    assert service.process_virtual_document(v_doc) is True
    assert service.logical_repo.get_by_uuid("doc-1").status == DocumentStatus.SKIPPED_EMPTY
    assert client.analyzed == []


# ------------------------------------------------------------------ text from the engine (no Stage 0 OCR)

def test_scan_text_comes_from_the_engine(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any]) -> None:
    """Scan: Stage 0 stored no text; the engine's page texts fill the physical pages, full text and FTS."""
    texts = [f"engine ocr page {i}" for i in range(1, 6)]
    service = _service(db, FakeClient([(stack_result, texts)]))
    service.physical_repo.save(PhysicalFile(uuid="file-a", original_filename="scan.pdf", file_path=str(physical_pdf),
                                            page_count_phys=5, raw_ocr_data={}))
    v_doc = VirtualDocument(uuid="doc-1", source_mapping=[SourceReference(file_uuid="file-a", pages=[1, 2, 3, 4, 5])])
    service.logical_repo.save(v_doc)

    assert service.process_virtual_document(v_doc) is True
    assert service.physical_repo.get_by_uuid("file-a").raw_ocr_data == {str(i): f"engine ocr page {i}" for i in range(1, 6)}
    invoice, statement, letter = _all_docs(service)
    assert invoice.cached_full_text == "engine ocr page 1\nengine ocr page 2"
    assert letter.cached_full_text == "engine ocr page 5"
    hits = db.connection.execute("SELECT uuid FROM virtual_documents_fts WHERE virtual_documents_fts MATCH ?",
                                 ('"engine ocr page 4"',)).fetchall()
    assert [row[0] for row in hits] == [statement.uuid]


def test_digital_text_layer_is_kept(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any]) -> None:
    """Digital PDF: the native Stage 0 text wins; only pages without text take the engine text."""
    texts = [f"engine page {i}" for i in range(1, 6)]
    service = _service(db, FakeClient([(stack_result, texts)]))
    service.physical_repo.save(PhysicalFile(uuid="file-a", original_filename="d.pdf", file_path=str(physical_pdf),
                                            page_count_phys=5, raw_ocr_data={"1": "native 1", "2": "native 2", "3": "native 3",
                                                                             "4": "native 4", "5": ""}))
    v_doc = VirtualDocument(uuid="doc-1", source_mapping=[SourceReference(file_uuid="file-a", pages=[1, 2, 3, 4, 5])])
    service.logical_repo.save(v_doc)
    assert service.process_virtual_document(v_doc) is True
    stored = service.physical_repo.get_by_uuid("file-a").raw_ocr_data
    assert stored["1"] == "native 1" and stored["4"] == "native 4"
    assert stored["5"] == "engine page 5"
    assert _all_docs(service)[0].cached_full_text == "native 1\nnative 2"


def test_stitched_page_texts_map_to_physical_pages(db: DatabaseManager, physical_pdf: Path,
                                                   stack_result: Dict[str, Any]) -> None:
    """Engine page i of a stitched input is stored on the physical page it came from."""
    statement_only = copy.deepcopy(stack_result)
    statement_only["logical_documents"] = [statement_only["logical_documents"][1]]
    statement_only["logical_documents"][0]["pages"] = [1, 2]
    service = _service(db, FakeClient([(statement_only, ["ocr of p3", "ocr of p4"])]))
    service.physical_repo.save(PhysicalFile(uuid="file-a", original_filename="scan.pdf", file_path=str(physical_pdf),
                                            page_count_phys=5, raw_ocr_data={}))
    v_doc = VirtualDocument(uuid="doc-1", source_mapping=[SourceReference(file_uuid="file-a", pages=[3, 4])])
    service.logical_repo.save(v_doc)
    assert service.process_virtual_document(v_doc) is True
    assert service.physical_repo.get_by_uuid("file-a").raw_ocr_data == {"3": "ocr of p3", "4": "ocr of p4"}


def test_document_owned_by_other_worker_is_skipped(db: DatabaseManager, physical_pdf: Path) -> None:
    """A document in another PROCESSING state is left alone."""
    client = FakeClient([])
    service = _service(db, client)
    v_doc = _ingest(service, physical_pdf, [1, 2], status=DocumentStatus.PROCESSING_S1_5)
    assert service.process_virtual_document(v_doc) is False
    assert client.analyzed == []


# ------------------------------------------------------------------ helpers

def test_engine_client_created_from_settings_and_reset() -> None:
    """The client follows the configured mode; reset picks up changed settings."""
    config = MagicMock()
    config.get_fluxsense_mode.return_value = "rest"
    config.get_fluxsense_url.return_value = "http://svc:8765"
    config.get_fluxsense_timeout.return_value = 60
    config.get_private_profile_json.return_value = '{"name": "Erika Mustermann"}'
    config.get_business_profile_json.return_value = ""
    with patch("core.canonizer.AppConfig", MagicMock(return_value=config)):
        service = CanonizerService(MagicMock(), physical_repo=MagicMock(), logical_repo=MagicMock())
    client = service.get_engine_client()
    assert client.mode == "rest" and service.get_engine_client() is client
    service.reset_engine_client()
    config.get_fluxsense_mode.return_value = "library"
    assert service.get_engine_client().mode == "library"


def test_generate_smart_filename() -> None:
    """Export filenames: date, cleaned sender, primary type."""
    sem = SemanticExtraction(meta_header={"doc_date": "2026-01-02", "sender": {"company": "ACME & Söhne GmbH"}})
    assert generate_smart_filename(sem, ["INVOICE", "INBOUND"]) == "2026-01-02__ACME__Söhne_GmbH__INVOICE.pdf"
    assert generate_smart_filename(None, []) == "0000-00-00__Unknown__DOC.pdf"
    assert generate_smart_filename(SemanticExtraction(), []) == "0000-00-00__Unknown__DOC.pdf"


# ------------------------------------------------------------------ interrupted analysis

def test_interrupted_analysis_is_requeued_and_processed(db: DatabaseManager, physical_pdf: Path,
                                                        stack_result: Dict[str, Any]) -> None:
    """Regression (e2e): a quit during a long FluxSense call must not leave the document locked forever."""
    service = _service(db, FakeClient([stack_result]))
    _ingest(service, physical_pdf, [1, 2, 3, 4, 5], status=DocumentStatus.PROCESSING_S1)
    other = VirtualDocument(uuid="doc-2", status=DocumentStatus.PROCESSING_S2,
                            source_mapping=[SourceReference(file_uuid="file-a", pages=[5])])
    service.logical_repo.save(other)
    assert db.get_pending_pipeline_count() == 0

    assert service.release_interrupted_documents() == 2
    assert service.logical_repo.get_by_uuid("doc-1").status == DocumentStatus.READY_FOR_PIPELINE
    assert service.logical_repo.get_by_uuid("doc-2").status == DocumentStatus.STAGE2_PENDING
    assert service.release_interrupted_documents() == 0


def test_main_loop_worker_releases_locks_on_start() -> None:
    """The background worker re-queues interrupted documents before its loop starts."""
    from gui.workers import MainLoopWorker
    pipeline = MagicMock()
    with patch("gui.workers.CanonizerService") as canonizer_cls:
        worker = MainLoopWorker(pipeline, None)
        worker.is_running = False
        worker.run()
    canonizer_cls.return_value.release_interrupted_documents.assert_called_once()


# ------------------------------------------------------------------ batches

def _ingest_many(service: CanonizerService, pdf: Path, count: int) -> None:
    """One physical file and `count` single-page documents waiting in the queue."""
    service.physical_repo.save(PhysicalFile(uuid="file-a", original_filename="scan.pdf", file_path=str(pdf),
                                            page_count_phys=5, raw_ocr_data={str(i): f"stage0 text {i}" for i in range(1, 6)}))
    for index in range(count):
        service.logical_repo.save(VirtualDocument(uuid=f"doc-{index}", status=DocumentStatus.READY_FOR_PIPELINE,
                                                  source_mapping=[SourceReference(file_uuid="file-a", pages=[index + 1])]))


def _single_page_result(stack_result: Dict[str, Any]) -> Dict[str, Any]:
    """Letter result covering page 1 of a 1-page input."""
    one = copy.deepcopy(stack_result)
    one["logical_documents"] = [one["logical_documents"][2]]
    one["logical_documents"][0]["pages"] = [1]
    return one


def test_failure_holds_only_the_failed_document(db: DatabaseManager, physical_pdf: Path,
                                                stack_result: Dict[str, Any]) -> None:
    """Hold logic per document within one batch."""
    one = _single_page_result(stack_result)
    service = _service(db, FakeClient([FluxSenseError("backend unreachable", "BACKEND_UNREACHABLE"), one]))
    _ingest_many(service, physical_pdf, 2)
    assert service.process_pending_documents(limit=2) == 1
    statuses = sorted(d.status for d in _all_docs(service))
    assert statuses == sorted([DocumentStatus.PROCESSED, DocumentStatus.STAGE1_HOLD])


def test_unexpected_engine_exception_holds_instead_of_locking(db: DatabaseManager, physical_pdf: Path,
                                                              stack_result: Dict[str, Any]) -> None:
    """A foreign exception inside the engine thread puts the document on hold."""
    one = _single_page_result(stack_result)
    service = _service(db, FakeClient([OSError("disk full"), one]))
    _ingest_many(service, physical_pdf, 2)
    assert service.process_pending_documents(limit=2) == 1
    held = [d for d in _all_docs(service) if d.status == DocumentStatus.STAGE1_HOLD]
    assert len(held) == 1 and "disk full" in held[0].semantic_data.engine.errors[0]
    assert db.get_pending_pipeline_count() == 0


def test_coding_errors_still_stop_the_worker(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any]) -> None:
    """Critical errors are re-raised (after holding the document), as before."""
    service = _service(db, FakeClient([TypeError("bug")]))
    _ingest_many(service, physical_pdf, 1)
    with pytest.raises(TypeError):
        service.process_pending_documents(limit=1)
    assert service.logical_repo.get_by_uuid("doc-0").status == DocumentStatus.STAGE1_HOLD


def test_interrupted_batch_is_requeued(db: DatabaseManager, physical_pdf: Path) -> None:
    """Both documents of an interrupted batch come back to the queue."""
    service = _service(db, FakeClient([]))
    _ingest_many(service, physical_pdf, 2)
    assert len(service._lock_pending(2)) == 2
    assert db.get_pending_pipeline_count() == 0
    assert service.release_interrupted_documents() == 2
    assert db.get_pending_pipeline_count() == 2



def test_unreachable_server_is_recorded_with_a_generic_message(db: DatabaseManager, physical_pdf: Path,
                                                               stack_result: Dict[str, Any]) -> None:
    """Library mode: FluxSense returns status ERROR with error_code BACKEND_UNREACHABLE -> address + settings hint."""
    down = copy.deepcopy(stack_result)
    down["status"] = "ERROR"
    down["error_code"] = "BACKEND_UNREACHABLE"
    down["ai_calls"] = [{"label": "Stage 1.1", "model": "m", "ok": False, "error": "Backend unreachable: [Errno 111] refused"}]
    service = _service(db, FakeClient([down]))
    v_doc = _ingest(service, physical_pdf, [1, 2, 3, 4, 5])
    assert service.process_virtual_document(v_doc) is False
    engine = service.logical_repo.get_by_uuid("doc-1").semantic_data.engine
    assert engine.error_code == "BACKEND_UNREACHABLE"
    assert engine.server_url == "http://ai-server.test:8080/v1"
    assert engine.errors[0] == "AI server not reachable at http://ai-server.test:8080/v1. Please check the AI server settings."
    assert not any("wake" in e.lower() or "wol" in e.lower() for e in engine.errors)


def test_unreachable_rest_service_is_recorded_with_a_generic_message(db: DatabaseManager, physical_pdf: Path) -> None:
    """REST mode: a refused connection carries the unreachable flag."""
    service = _service(db, FakeClient([FluxSenseError("FluxSense service unreachable at http://x", "BACKEND_UNREACHABLE")]))
    v_doc = _ingest(service, physical_pdf, [1, 2])
    assert service.process_virtual_document(v_doc) is False
    engine = service.logical_repo.get_by_uuid("doc-1").semantic_data.engine
    assert engine.error_code == "BACKEND_UNREACHABLE"
    assert engine.errors[1].startswith("FluxSense service unreachable")


def test_other_failures_have_no_unreachable_code(db: DatabaseManager, physical_pdf: Path) -> None:
    """Unclassified failures keep their own message and no code."""
    service = _service(db, FakeClient([FluxSenseError("FluxSense HTTP 422")]))
    v_doc = _ingest(service, physical_pdf, [1, 2])
    service.process_virtual_document(v_doc)
    engine = service.logical_repo.get_by_uuid("doc-1").semantic_data.engine
    assert engine.error_code is None and engine.errors[0] == "FluxSense HTTP 422"


def test_ai_server_url_setting_is_passed_to_the_client() -> None:
    """An explicitly set AI server URL reaches the library factory; empty keeps FluxSense's config."""
    config = MagicMock()
    config.get_fluxsense_mode.return_value = "library"
    config.get_fluxsense_url.return_value = ""
    config.get_fluxsense_timeout.return_value = 60
    config.get_private_profile_json.return_value = ""
    config.get_business_profile_json.return_value = ""
    config.get_fluxsense_llm_url.return_value = "http://my-ai:8080/v1"
    with patch("core.canonizer.AppConfig", MagicMock(return_value=config)), \
         patch("core.canonizer.create_fluxsense_client") as create:
        CanonizerService(MagicMock(), physical_repo=MagicMock(), logical_repo=MagicMock()).get_engine_client()
    assert create.call_args.kwargs["llm_url"] == "http://my-ai:8080/v1"



@pytest.mark.parametrize("code, expected", [
    ("BACKEND_TIMEOUT", "did not answer in time"),
    ("CONTEXT_OVERFLOW", "too large for the AI model's context window"),
    ("INPUT_INVALID", "could not be read as a PDF"),
])
def test_error_codes_map_to_hold_messages(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any],
                                          code: str, expected: str) -> None:
    """Each FluxSense error code holds the document with its own generic message (no string matching)."""
    failed = copy.deepcopy(stack_result)
    failed["status"] = "ERROR"
    failed["error_code"] = code
    service = _service(db, FakeClient([failed]))
    v_doc = _ingest(service, physical_pdf, [1, 2])
    assert service.process_virtual_document(v_doc) is False
    held = service.logical_repo.get_by_uuid("doc-1")
    assert held.status == DocumentStatus.STAGE1_HOLD
    assert held.semantic_data.engine.error_code == code
    assert expected in held.semantic_data.engine.errors[0]


def test_failed_scan_is_held_not_purged(db: DatabaseManager, physical_pdf: Path, stack_result: Dict[str, Any]) -> None:
    """Regression: a scan without Stage 0 text and an unreachable server must be held, not purged as blank."""
    down = copy.deepcopy(stack_result)
    down["status"] = "ERROR"
    down["error_code"] = "BACKEND_UNREACHABLE"
    down["text_layer"]["pages"] = []
    service = _service(db, FakeClient([down]))
    service.physical_repo.save(PhysicalFile(uuid="file-a", original_filename="scan.pdf", file_path=str(physical_pdf),
                                            page_count_phys=5, raw_ocr_data={}))
    v_doc = VirtualDocument(uuid="doc-1", source_mapping=[SourceReference(file_uuid="file-a", pages=[5])])
    service.logical_repo.save(v_doc)
    assert service.process_virtual_document(v_doc) is False
    assert service.logical_repo.get_by_uuid("doc-1").status == DocumentStatus.STAGE1_HOLD


# ------------------------------------------------------------------ concurrent analysis

class ConcurrentFakeClient(FakeClient):
    """FakeClient that measures how many analyses overlap and in which threads they run."""

    def __init__(self, outcomes: List[Any], delay: float) -> None:
        super().__init__(outcomes)
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.threads: List[str] = []
        self._lock = threading.Lock()

    def analyze(self, pdf_path: Path) -> Dict[str, Any]:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.threads.append(threading.current_thread().name)
            outcome = self.outcomes.pop(0)
        try:
            time.sleep(self.delay)
        finally:
            with self._lock:
                self.active -= 1
        if isinstance(outcome, Exception):
            raise outcome
        return copy.deepcopy(outcome)


def test_two_documents_are_analyzed_concurrently_with_serial_db_writes(db: DatabaseManager, physical_pdf: Path,
                                                                       stack_result: Dict[str, Any]) -> None:
    """Engine calls overlap; every database write happens in the calling (worker) thread."""
    one = _single_page_result(stack_result)
    client = ConcurrentFakeClient([one, one], delay=0.3)
    service = _service(db, client)
    _ingest_many(service, physical_pdf, 2)
    caller = threading.current_thread().name
    writers: List[str] = []
    original_save = service.logical_repo.save
    service.logical_repo.save = lambda doc: (writers.append(threading.current_thread().name), original_save(doc))[1]

    started = time.monotonic()
    assert service.process_pending_documents(limit=2, max_parallel=2) == 2
    elapsed = time.monotonic() - started

    assert client.max_active == 2
    assert elapsed < 0.55  # two 0.3 s engine calls overlapped
    assert caller not in client.threads
    assert writers and set(writers) == {caller}
    assert [d.status for d in _all_docs(service)] == [DocumentStatus.PROCESSED] * 2


def test_parallel_failure_holds_only_the_failed_document(db: DatabaseManager, physical_pdf: Path,
                                                         stack_result: Dict[str, Any]) -> None:
    """Hold logic per document also under concurrency."""
    one = _single_page_result(stack_result)
    service = _service(db, ConcurrentFakeClient([FluxSenseError("down", "BACKEND_UNREACHABLE"), one], delay=0.1))
    _ingest_many(service, physical_pdf, 2)
    assert service.process_pending_documents(limit=2, max_parallel=2) == 1
    assert sorted(d.status for d in _all_docs(service)) == sorted([DocumentStatus.PROCESSED, DocumentStatus.STAGE1_HOLD])


def test_parallel_unexpected_exception_holds_instead_of_locking(db: DatabaseManager, physical_pdf: Path,
                                                                stack_result: Dict[str, Any]) -> None:
    """A foreign exception in an engine thread puts only that document on hold."""
    one = _single_page_result(stack_result)
    service = _service(db, ConcurrentFakeClient([OSError("disk full"), one], delay=0.05))
    _ingest_many(service, physical_pdf, 2)
    assert service.process_pending_documents(limit=2, max_parallel=2) == 1
    assert db.get_pending_pipeline_count() == 0
    assert sum(1 for d in _all_docs(service) if d.status == DocumentStatus.STAGE1_HOLD) == 1


def test_stitching_uses_the_process_wide_pymupdf_lock() -> None:
    """KPaperFlux's PyMuPDF use beside concurrent FluxSense analyses takes FluxSense's lock."""
    from core.engines import analysis_input
    pdflock = pytest.importorskip("fluxsense.pdflock")
    assert analysis_input._pymupdf_lock() is pdflock.PYMUPDF_LOCK
