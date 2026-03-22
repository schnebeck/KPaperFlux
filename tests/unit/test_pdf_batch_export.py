"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_pdf_batch_export.py
Version:        1.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Code
Description:    Tests for export_to_pdf_batch() and export_to_zip() covering
                single-file page subsets, multi-file stitching with
                path_resolver, rotation, fallback paths, and ZIP PDF inclusion
                for vault-stored (source_mapping) documents.
------------------------------------------------------------------------------
"""

import os
import zipfile
from pathlib import Path

import fitz
import pytest

from core.exporter import DocumentExporter
from core.models.virtual import VirtualDocument, SourceReference


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf(path: Path, num_pages: int, label: str = "Page") -> Path:
    """Create a minimal real PDF with text labels so page identity is verifiable."""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{label} {i + 1}")
    doc.save(str(path))
    doc.close()
    return path


def _page_texts(pdf_path: Path) -> list[str]:
    """Return the first text line from every page of a PDF."""
    texts = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            texts.append(page.get_text().strip())
    return texts


def _doc_with_mapping(refs: list[SourceReference]) -> VirtualDocument:
    return VirtualDocument(uuid="test-doc", source_mapping=refs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_export_legacy_no_source_mapping(tmp_path):
    """Legacy document without source_mapping: entire physical file is copied."""
    src = _make_pdf(tmp_path / "src.pdf", num_pages=3, label="Legacy")
    doc = VirtualDocument(uuid="leg1", file_path=str(src))

    out = tmp_path / "out.pdf"
    DocumentExporter.export_to_pdf_batch([doc], str(out))

    assert out.exists()
    texts = _page_texts(out)
    assert texts == ["Legacy 1", "Legacy 2", "Legacy 3"]


def test_export_single_ref_all_pages(tmp_path):
    """Single SourceReference covering all pages — output matches source."""
    src = _make_pdf(tmp_path / "src.pdf", num_pages=3, label="Full")
    uuid = "phys-001"
    ref = SourceReference(file_uuid=uuid, pages=[1, 2, 3])
    doc = _doc_with_mapping([ref])

    resolver = {uuid: str(src)}
    out = tmp_path / "out.pdf"
    DocumentExporter.export_to_pdf_batch([doc], str(out), path_resolver=resolver.get)

    texts = _page_texts(out)
    assert texts == ["Full 1", "Full 2", "Full 3"]


def test_export_single_ref_page_subset(tmp_path):
    """Single SourceReference selecting only pages 1 and 3 — middle page skipped."""
    src = _make_pdf(tmp_path / "src.pdf", num_pages=3, label="Sub")
    uuid = "phys-002"
    ref = SourceReference(file_uuid=uuid, pages=[1, 3])
    doc = _doc_with_mapping([ref])

    out = tmp_path / "out.pdf"
    DocumentExporter.export_to_pdf_batch([doc], str(out), path_resolver={uuid: str(src)}.get)

    texts = _page_texts(out)
    assert len(texts) == 2
    assert texts[0] == "Sub 1"
    assert texts[1] == "Sub 3"


def test_export_multi_file_stitch(tmp_path):
    """Two SourceReferences from different physical files are stitched in order."""
    src_a = _make_pdf(tmp_path / "a.pdf", num_pages=2, label="FileA")
    src_b = _make_pdf(tmp_path / "b.pdf", num_pages=2, label="FileB")
    uuid_a, uuid_b = "phys-a", "phys-b"

    refs = [
        SourceReference(file_uuid=uuid_a, pages=[1, 2]),
        SourceReference(file_uuid=uuid_b, pages=[1, 2]),
    ]
    doc = _doc_with_mapping(refs)
    resolver = {uuid_a: str(src_a), uuid_b: str(src_b)}

    out = tmp_path / "out.pdf"
    DocumentExporter.export_to_pdf_batch([doc], str(out), path_resolver=resolver.get)

    texts = _page_texts(out)
    assert texts == ["FileA 1", "FileA 2", "FileB 1", "FileB 2"]


def test_export_multi_file_interleaved_pages(tmp_path):
    """Pages from two sources can be interleaved via separate SourceReferences."""
    src_a = _make_pdf(tmp_path / "a.pdf", num_pages=3, label="A")
    src_b = _make_pdf(tmp_path / "b.pdf", num_pages=3, label="B")
    uuid_a, uuid_b = "phys-a2", "phys-b2"

    # Take p3 from A, then p1+p2 from B
    refs = [
        SourceReference(file_uuid=uuid_a, pages=[3]),
        SourceReference(file_uuid=uuid_b, pages=[1, 2]),
    ]
    doc = _doc_with_mapping(refs)
    resolver = {uuid_a: str(src_a), uuid_b: str(src_b)}

    out = tmp_path / "out.pdf"
    DocumentExporter.export_to_pdf_batch([doc], str(out), path_resolver=resolver.get)

    texts = _page_texts(out)
    assert texts == ["A 3", "B 1", "B 2"]


def test_export_rotation_applied(tmp_path):
    """SourceReference with rotation=90 produces a rotated page."""
    src = _make_pdf(tmp_path / "src.pdf", num_pages=1, label="Rot")
    uuid = "phys-rot"
    ref = SourceReference(file_uuid=uuid, pages=[1], rotation=90)
    doc = _doc_with_mapping([ref])

    out = tmp_path / "out.pdf"
    DocumentExporter.export_to_pdf_batch([doc], str(out), path_resolver={uuid: str(src)}.get)

    assert out.exists()
    with fitz.open(str(out)) as result:
        assert result.page_count == 1
        assert result[0].rotation == 90


def test_export_multiple_documents_merged(tmp_path):
    """Multiple VirtualDocuments are appended sequentially into one PDF."""
    src1 = _make_pdf(tmp_path / "d1.pdf", num_pages=2, label="Doc1")
    src2 = _make_pdf(tmp_path / "d2.pdf", num_pages=2, label="Doc2")
    uuid1, uuid2 = "phys-d1", "phys-d2"

    doc1 = _doc_with_mapping([SourceReference(file_uuid=uuid1, pages=[1, 2])])
    doc2 = _doc_with_mapping([SourceReference(file_uuid=uuid2, pages=[1, 2])])
    resolver = {uuid1: str(src1), uuid2: str(src2)}

    out = tmp_path / "out.pdf"
    DocumentExporter.export_to_pdf_batch([doc1, doc2], str(out), path_resolver=resolver.get)

    texts = _page_texts(out)
    assert texts == ["Doc1 1", "Doc1 2", "Doc2 1", "Doc2 2"]


def test_export_resolver_returns_none_falls_back_to_file_path(tmp_path):
    """If resolver returns None, doc.file_path is used as fallback."""
    src = _make_pdf(tmp_path / "src.pdf", num_pages=2, label="Fallback")
    uuid = "phys-unknown"
    ref = SourceReference(file_uuid=uuid, pages=[1, 2])
    doc = _doc_with_mapping([ref])
    doc.file_path = str(src)  # Set fallback path

    # Resolver that always returns None
    out = tmp_path / "out.pdf"
    DocumentExporter.export_to_pdf_batch([doc], str(out), path_resolver=lambda _: None)

    texts = _page_texts(out)
    assert texts == ["Fallback 1", "Fallback 2"]


def test_export_missing_physical_file_skipped(tmp_path):
    """SourceReference pointing to non-existent file is silently skipped."""
    src = _make_pdf(tmp_path / "real.pdf", num_pages=2, label="Real")
    uuid_real, uuid_ghost = "phys-real", "phys-ghost"

    refs = [
        SourceReference(file_uuid=uuid_ghost, pages=[1]),   # file does not exist
        SourceReference(file_uuid=uuid_real, pages=[1, 2]),
    ]
    doc = _doc_with_mapping(refs)
    resolver = {uuid_real: str(src), uuid_ghost: "/nonexistent/ghost.pdf"}

    out = tmp_path / "out.pdf"
    DocumentExporter.export_to_pdf_batch([doc], str(out), path_resolver=resolver.get)

    texts = _page_texts(out)
    assert texts == ["Real 1", "Real 2"]


def test_export_progress_callback_called(tmp_path):
    """progress_callback receives values from 1–100 and ends at 100."""
    src = _make_pdf(tmp_path / "src.pdf", num_pages=1, label="P")
    uuid = "phys-prog"
    doc = _doc_with_mapping([SourceReference(file_uuid=uuid, pages=[1])])
    resolver = {uuid: str(src)}

    recorded: list[int] = []
    out = tmp_path / "out.pdf"
    DocumentExporter.export_to_pdf_batch(
        [doc], str(out), path_resolver=resolver.get, progress_callback=recorded.append
    )

    assert len(recorded) > 0
    assert recorded[-1] == 100
    assert all(0 < v <= 100 for v in recorded)


# ---------------------------------------------------------------------------
# export_to_zip — PDF inclusion with source_mapping
# ---------------------------------------------------------------------------

def test_zip_includes_pdf_for_legacy_doc(tmp_path):
    """Legacy doc (no source_mapping, file_path set) is added directly to ZIP."""
    src = _make_pdf(tmp_path / "src.pdf", num_pages=2, label="Leg")
    doc = VirtualDocument(uuid="leg-zip", original_filename="invoice.pdf", file_path=str(src))

    out = tmp_path / "export.zip"
    DocumentExporter.export_to_zip([doc], str(out), include_pdfs=True)

    with zipfile.ZipFile(out) as zf:
        assert "documents/invoice.pdf" in zf.namelist()
        pdf_bytes = zf.read("documents/invoice.pdf")
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        assert pdf.page_count == 2


def test_zip_stitches_vault_doc_into_pdf(tmp_path):
    """Vault doc with source_mapping is stitched and included in ZIP."""
    src = _make_pdf(tmp_path / "vault.pdf", num_pages=4, label="V")
    uuid = "phys-zip-v"
    ref = SourceReference(file_uuid=uuid, pages=[1, 3])  # only pages 1 and 3
    doc = VirtualDocument(
        uuid="virt-zip",
        original_filename="stitched.pdf",
        source_mapping=[ref],
    )
    resolver = {uuid: str(src)}

    out = tmp_path / "export.zip"
    DocumentExporter.export_to_zip([doc], str(out), include_pdfs=True, path_resolver=resolver.get)

    with zipfile.ZipFile(out) as zf:
        assert "documents/stitched.pdf" in zf.namelist()
        pdf_bytes = zf.read("documents/stitched.pdf")
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        assert pdf.page_count == 2
        assert "V 1" in pdf[0].get_text()
        assert "V 3" in pdf[1].get_text()


def test_zip_stitches_multi_source_vault_doc(tmp_path):
    """Vault doc spanning two physical files is stitched correctly in ZIP."""
    src_a = _make_pdf(tmp_path / "a.pdf", num_pages=2, label="A")
    src_b = _make_pdf(tmp_path / "b.pdf", num_pages=2, label="B")
    uuid_a, uuid_b = "phys-za", "phys-zb"

    refs = [
        SourceReference(file_uuid=uuid_a, pages=[2]),
        SourceReference(file_uuid=uuid_b, pages=[1]),
    ]
    doc = VirtualDocument(uuid="virt-multi", original_filename="multi.pdf", source_mapping=refs)
    resolver = {uuid_a: str(src_a), uuid_b: str(src_b)}

    out = tmp_path / "export.zip"
    DocumentExporter.export_to_zip([doc], str(out), include_pdfs=True, path_resolver=resolver.get)

    with zipfile.ZipFile(out) as zf:
        pdf_bytes = zf.read("documents/multi.pdf")
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        assert pdf.page_count == 2
        assert "A 2" in pdf[0].get_text()
        assert "B 1" in pdf[1].get_text()


def test_zip_skips_pdf_when_no_resolver_and_no_file_path(tmp_path):
    """Vault doc without resolver and without file_path yields no PDF in ZIP (no crash)."""
    ref = SourceReference(file_uuid="phys-ghost", pages=[1])
    doc = VirtualDocument(uuid="ghost", original_filename="ghost.pdf", source_mapping=[ref])

    out = tmp_path / "export.zip"
    DocumentExporter.export_to_zip([doc], str(out), include_pdfs=True)

    with zipfile.ZipFile(out) as zf:
        assert "documents/ghost.pdf" not in zf.namelist()
        assert "manifest.xlsx" in zf.namelist()


def test_zip_temp_files_cleaned_up(tmp_path):
    """No temp stitched PDFs remain on disk after export."""
    import glob
    src = _make_pdf(tmp_path / "src.pdf", num_pages=2, label="T")
    uuid = "phys-tmp"
    doc = VirtualDocument(
        uuid="tmp-doc",
        original_filename="doc.pdf",
        source_mapping=[SourceReference(file_uuid=uuid, pages=[1, 2])],
    )
    resolver = {uuid: str(src)}

    import tempfile
    before = set(glob.glob(os.path.join(tempfile.gettempdir(), "stitch_*.pdf")))

    out = tmp_path / "export.zip"
    DocumentExporter.export_to_zip([doc], str(out), include_pdfs=True, path_resolver=resolver.get)

    after = set(glob.glob(os.path.join(tempfile.gettempdir(), "stitch_*.pdf")))
    assert after == before  # no new stitch_ files left behind
