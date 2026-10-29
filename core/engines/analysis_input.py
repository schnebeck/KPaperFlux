"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/engines/analysis_input.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Provides the PDF that an analysis engine reads for one
                VirtualDocument: the vault original if the document is one
                complete, unrotated physical file, otherwise a temporary
                stitched copy of its pages. Vault files are only read (WORM).
------------------------------------------------------------------------------
"""

import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple

import fitz

from core.engines.fluxsense_adapter import PageRef, is_whole_file

# Resolves a physical file UUID to (vault path, page count); None if unknown.
PhysicalResolver = Callable[[str], Optional[Tuple[str, int]]]


def _pymupdf_lock() -> "threading.RLock":
    """
    The process-wide PyMuPDF lock. PyMuPDF is not thread-safe; FluxSense
    guards its own PyMuPDF access with fluxsense.pdflock.PYMUPDF_LOCK, so
    KPaperFlux code running beside concurrent analyses must take the same lock.
    """
    try:
        from fluxsense.pdflock import PYMUPDF_LOCK
    except ImportError:
        return _FALLBACK_LOCK
    return PYMUPDF_LOCK


_FALLBACK_LOCK = threading.RLock()


class AnalysisInputError(OSError):
    """Raised when the pages of a document cannot be assembled into a PDF."""


def stitch_pages(page_refs: List[PageRef], resolver: PhysicalResolver, target: Path) -> Path:
    """
    Writes the page sequence into a new PDF (same rotation semantics as the exporter).

    Args:
        page_refs: Flattened page sequence.
        resolver: Physical file resolver.
        target: Output path.

    Returns:
        The written path.

    Raises:
        AnalysisInputError: If a source file or page is missing.
    """
    with _pymupdf_lock():
        return _stitch_locked(page_refs, resolver, target)


def _stitch_locked(page_refs: List[PageRef], resolver: PhysicalResolver, target: Path) -> Path:
    """stitch_pages() body; the caller holds the PyMuPDF lock."""
    out = fitz.open()
    try:
        for ref in page_refs:
            resolved = resolver(ref.file_uuid)
            if not resolved or not Path(resolved[0]).exists():
                raise AnalysisInputError(f"Physical file {ref.file_uuid} is not available in the vault")
            with fitz.open(resolved[0]) as src:
                if not 1 <= ref.page <= src.page_count:
                    raise AnalysisInputError(f"Page {ref.page} does not exist in physical file {ref.file_uuid}")
                out.insert_pdf(src, from_page=ref.page - 1, to_page=ref.page - 1, rotate=ref.rotation or -1)
        out.save(str(target))
    except RuntimeError as e:  # PyMuPDF raises RuntimeError subclasses for unreadable PDFs
        raise AnalysisInputError(f"Cannot assemble analysis PDF: {e}") from e
    finally:
        out.close()
    return target


@contextmanager
def analysis_pdf(page_refs: List[PageRef], resolver: PhysicalResolver) -> Iterator[Path]:
    """
    Yields the PDF to analyze; a stitched temporary copy is deleted afterwards.

    Args:
        page_refs: Flattened page sequence of the document.
        resolver: Physical file resolver.

    Yields:
        Path of the PDF whose page i is page_refs[i - 1].

    Raises:
        AnalysisInputError: If the document has no pages or a source is missing.
    """
    if not page_refs:
        raise AnalysisInputError("Document has no pages")
    first = resolver(page_refs[0].file_uuid)
    if first and Path(first[0]).exists() and is_whole_file(page_refs, first[1]):
        yield Path(first[0])
        return
    with tempfile.TemporaryDirectory(prefix="kpaperflux-analysis-") as tmp:
        yield stitch_pages(page_refs, resolver, Path(tmp) / "document.pdf")
