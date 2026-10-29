"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/generated_docs.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Test document inputs from FluxSense's synthetic generator
                (fluxsense.testdata): fictional data, deterministic per
                recorded seed, digital and image-only scan variants with
                exact ground truth. Tests assert against the generator's
                truth, never against hard-coded document content.
------------------------------------------------------------------------------
"""

from pathlib import Path
from typing import Any, List

import fitz
import pytest

# Recorded seeds (change only together with the tests that use them).
SEED_INVOICE: int = 3
SEED_STACK: int = 7
SEED_STATEMENT: int = 5


def testdata() -> Any:
    """The generator module; skips the test if FluxSense is not installed."""
    return pytest.importorskip("fluxsense.testdata")


def generate(directory: Path, kind: str, seed: int, scan: bool) -> Any:
    """
    Generates one document file.

    Args:
        directory: Output directory.
        kind: Generator kind (e.g. 'invoice', 'stack', 'bank_statement').
        seed: Recorded seed.
        scan: True for the image-only scan variant.

    Returns:
        fluxsense.testdata.GeneratedFile (path, docs with truth, ...).
    """
    directory.mkdir(parents=True, exist_ok=True)
    return testdata().generate_file(directory, seed=seed, index=0, kind=kind, scan=scan)


def page_texts(doc: Any) -> List[str]:
    """Printed text of each page of a generated logical document (no rendering)."""
    return ["\n".join(page.lines()) for page in doc.pages]


def concat_pdfs(paths: List[Path], target: Path) -> Path:
    """Concatenates PDFs (e.g. several generated documents into one stack)."""
    out = fitz.open()
    for path in paths:
        with fitz.open(str(path)) as src:
            out.insert_pdf(src)
    out.save(str(target))
    out.close()
    return target


def append_blank_page(path: Path, target: Path) -> Path:
    """Appends an empty page, as an ADF scan of a blank back side produces it."""
    out = fitz.open()
    with fitz.open(str(path)) as src:
        out.insert_pdf(src)
        rect = src[0].rect
    out.new_page(width=rect.width, height=rect.height)
    out.save(str(target))
    out.close()
    return target
