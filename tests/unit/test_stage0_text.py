"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_stage0_text.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Stage 0 text extraction: no OCR run when the analysis engine
                delivers the text layer (library and REST mode).
                Inputs come from fluxsense.testdata (recorded seeds).
------------------------------------------------------------------------------
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.database import DatabaseManager
from core.pipeline import PipelineProcessor
from core.vault import DocumentVault, searchable_path_for
from tests.generated_docs import SEED_INVOICE, generate


@pytest.fixture
def digital_invoice(tmp_path: Path) -> object:
    """Generated digital invoice (text layer), recorded seed."""
    return generate(tmp_path / "gen", "invoice", SEED_INVOICE, scan=False)


@pytest.fixture
def scan_invoice(tmp_path: Path) -> object:
    """The same invoice as image-only scan (no text layer)."""
    return generate(tmp_path / "gen_scan", "invoice", SEED_INVOICE, scan=True)


def _pipeline(tmp_path: Path, mode: str) -> PipelineProcessor:
    """Pipeline on a temporary vault and in-memory DB with the given FluxSense mode."""
    db = DatabaseManager(":memory:")
    db.init_db()
    pipeline = PipelineProcessor(vault=DocumentVault(tmp_path / "vault"), db=db)
    pipeline.config = MagicMock()
    pipeline.config.get_fluxsense_mode.return_value = mode
    pipeline.config.get_ocr_engine.return_value = "ocrmypdf"
    return pipeline


def test_library_mode_scan_gets_no_stage0_ocr(tmp_path: Path, scan_invoice: object) -> None:
    """Scans are not OCRed in Stage 0: FluxSense delivers their text; no derived searchable PDF."""
    pipeline = _pipeline(tmp_path, "library")
    with patch.object(pipeline, "_run_ocr") as run_ocr:
        phys = pipeline._ingest_physical_file(str(scan_invoice.path))
    run_ocr.assert_not_called()
    assert phys.raw_ocr_data == {}
    assert phys.page_count_phys == len(scan_invoice.docs[0].pages)
    assert not searchable_path_for(phys.file_path).exists()


def test_library_mode_digital_keeps_native_text(tmp_path: Path, digital_invoice: object) -> None:
    """Digital PDFs keep their exact native text layer (contains the generator's truth)."""
    pipeline = _pipeline(tmp_path, "library")
    with patch.object(pipeline, "_run_ocr") as run_ocr:
        phys = pipeline._ingest_physical_file(str(digital_invoice.path))
    run_ocr.assert_not_called()
    truth = digital_invoice.docs[0].truth
    assert sorted(phys.raw_ocr_data) == [str(i + 1) for i in range(len(digital_invoice.docs[0].pages))]
    assert truth["doc_number"] in phys.raw_ocr_data["1"]


def test_rest_mode_also_skips_stage0_ocr(tmp_path: Path, scan_invoice: object) -> None:
    """REST responses carry the text layer too (include_page_text), so Stage 0 never OCRs."""
    pipeline = _pipeline(tmp_path, "rest")
    with patch.object(pipeline, "_run_ocr") as run_ocr:
        phys = pipeline._ingest_physical_file(str(scan_invoice.path))
    run_ocr.assert_not_called()
    assert phys.raw_ocr_data == {}


def test_explicit_force_ocr_is_unchanged(tmp_path: Path, scan_invoice: object) -> None:
    """'Force OCR / Searchable PDF' still runs OCR (and produces the derived searchable copy)."""
    pipeline = _pipeline(tmp_path, "library")
    with patch.object(pipeline, "_run_ocr", return_value={"1": "forced"}) as run_ocr:
        assert pipeline._extract_text_map(scan_invoice.path, force_ocr=True) == {"1": "forced"}
    run_ocr.assert_called_once()
