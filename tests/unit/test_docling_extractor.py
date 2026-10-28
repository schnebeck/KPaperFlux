"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_docling_extractor.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Unit tests (mocked HTTP) for the docling-serve extractor and
                its integration into the pipeline text extraction.
------------------------------------------------------------------------------
"""

import hashlib
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.utils.docling_extractor import (
    PAGE_BREAK_MARKER,
    DoclingError,
    DoclingExtractor,
    pages_from_docling_json,
    pages_from_response,
)


def _docling_document() -> Dict[str, Any]:
    return {
        "schema_name": "DoclingDocument",
        "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/texts/1"}, {"$ref": "#/groups/0"}, {"$ref": "#/tables/0"}, {"$ref": "#/pictures/0"}, {"$ref": "#/texts/3"}]},
        "groups": [{"label": "list", "children": [{"$ref": "#/texts/2"}]}],
        "texts": [
            {"label": "title", "text": "Rechnung 2025-001", "prov": [{"page_no": 1}]},
            {"label": "text", "text": "Musterfirma GmbH", "prov": [{"page_no": 1}]},
            {"label": "list_item", "text": "Position A", "marker": "-", "prov": [{"page_no": 1}]},
            {"label": "section_header", "text": "AGB", "level": 1, "prov": [{"page_no": 2}]},
        ],
        "tables": [
            {"label": "table", "prov": [{"page_no": 2}], "data": {"grid": [
                [{"text": "Pos"}, {"text": "Betrag"}],
                [{"text": "1"}, {"text": "10,00 €"}],
            ]}},
        ],
        "pictures": [{"label": "picture", "prov": [{"page_no": 1}]}],
        "pages": {"1": {"page_no": 1}, "2": {"page_no": 2}},
    }


def test_pages_from_docling_json_splits_by_provenance() -> None:
    pages = pages_from_docling_json(_docling_document())
    assert set(pages) == {"1", "2"}
    assert pages["1"].startswith("# Rechnung 2025-001")
    assert "Musterfirma GmbH" in pages["1"]
    assert "- Position A" in pages["1"]
    assert "| Pos | Betrag |" in pages["2"]
    assert "| 1 | 10,00 € |" in pages["2"]
    assert "## AGB" in pages["2"]
    # Reading order: table precedes the section header on page 2
    assert pages["2"].index("| Pos") < pages["2"].index("## AGB")


def test_pages_from_response_prefers_json() -> None:
    response = {"status": "success", "document": {"md_content": "ignored", "json_content": _docling_document()}}
    assert set(pages_from_response(response)) == {"1", "2"}


def test_pages_from_response_page_break_marker_fallback() -> None:
    md = f"Page one{PAGE_BREAK_MARKER}Page two"
    response = {"status": "success", "document": {"md_content": md, "json_content": {"texts": [{"text": "x"}]}}}
    assert pages_from_response(response) == {"1": "Page one", "2": "Page two"}


def test_pages_from_response_whole_markdown_fallback() -> None:
    response = {"status": "partial_success", "errors": ["p3"], "document": {"md_content": "# All\nText"}}
    assert pages_from_response(response) == {"1": "# All\nText"}


def test_pages_from_response_failure_raises() -> None:
    with pytest.raises(DoclingError):
        pages_from_response({"status": "failure", "errors": ["boom"], "document": {}})


def test_form_data_standard_and_vlm() -> None:
    standard = DoclingExtractor("http://d:5001/", pipeline="standard").build_form_data(force_ocr=True)
    assert ("to_formats", "md") in standard and ("to_formats", "json") in standard
    assert ("pipeline", "standard") in standard
    assert ("force_ocr", "true") in standard
    assert ("image_export_mode", "placeholder") in standard
    assert ("ocr_lang", "de") in standard and ("ocr_lang", "en") in standard
    assert not any(k == "vlm_pipeline_model" for k, _ in standard)

    vlm = DoclingExtractor("http://d:5001", pipeline="vlm").build_form_data()
    assert ("pipeline", "vlm") in vlm
    assert ("vlm_pipeline_model", "granite_docling") in vlm

    with pytest.raises(ValueError):
        DoclingExtractor("http://d:5001", pipeline="magic")


@patch("core.utils.docling_extractor.requests.post")
def test_extract_pages_uploads_read_only(mock_post: MagicMock, tmp_path: Path) -> None:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": "success", "document": {"json_content": _docling_document()}, "processing_time": 1.2}
    mock_post.return_value = resp

    pages = DoclingExtractor("http://d:5001", timeout=77).extract_pages(pdf)

    assert set(pages) == {"1", "2"}
    args, kwargs = mock_post.call_args
    assert args[0] == "http://d:5001/v1/convert/file"
    assert kwargs["timeout"] == (10.0, 77)
    name, _fh, mime = kwargs["files"]["files"]
    assert name == "in.pdf" and mime == "application/pdf"
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == digest


@patch("core.utils.docling_extractor.requests.post")
def test_extract_pages_http_errors(mock_post: MagicMock, tmp_path: Path) -> None:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF")
    mock_post.side_effect = requests.exceptions.ConnectionError("down")
    with pytest.raises(DoclingError):
        DoclingExtractor("http://d:5001").extract_pages(pdf)

    mock_post.side_effect = None
    mock_post.return_value = MagicMock(status_code=422, text="validation error")
    with pytest.raises(DoclingError):
        DoclingExtractor("http://d:5001").extract_pages(pdf)


# --- Pipeline integration ----------------------------------------------------

def _pipeline(engine: str) -> Any:
    from core.pipeline import PipelineProcessor
    pipeline = PipelineProcessor.__new__(PipelineProcessor)
    pipeline.config = MagicMock()
    pipeline.config.get_ocr_engine.return_value = engine
    pipeline.config.get_docling_url.return_value = "http://d:5001"
    pipeline.config.get_docling_pipeline.return_value = "standard"
    pipeline.config.get_docling_timeout.return_value = 900
    return pipeline


def test_pipeline_uses_docling_when_configured(tmp_path: Path) -> None:
    pipeline = _pipeline("docling")
    with patch("core.utils.docling_extractor.DoclingExtractor.extract_pages", return_value={"1": "# Docling"}) as mock_extract, \
         patch.object(pipeline, "_run_ocr") as mock_ocr:
        assert pipeline._extract_text_map(tmp_path / "x.pdf") == {"1": "# Docling"}
    mock_extract.assert_called_once()
    mock_ocr.assert_not_called()


def test_pipeline_docling_failure_falls_back(tmp_path: Path) -> None:
    pipeline = _pipeline("docling")
    with patch("core.utils.docling_extractor.DoclingExtractor.extract_pages", side_effect=DoclingError("down")), \
         patch.object(pipeline, "_is_native_pdf", return_value=True), \
         patch.object(pipeline, "_extract_text_native", return_value={"1": "native"}):
        assert pipeline._extract_text_map(tmp_path / "x.pdf") == {"1": "native"}


def test_pipeline_default_engine_skips_docling(tmp_path: Path) -> None:
    pipeline = _pipeline("ocrmypdf")
    with patch("core.utils.docling_extractor.DoclingExtractor.extract_pages") as mock_extract, \
         patch.object(pipeline, "_is_native_pdf", return_value=False), \
         patch.object(pipeline, "_run_ocr", return_value={"1": "ocr"}):
        assert pipeline._extract_text_map(tmp_path / "x.pdf") == {"1": "ocr"}
    mock_extract.assert_not_called()
