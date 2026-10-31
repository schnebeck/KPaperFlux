"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_stamp_worm.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Stamping never modifies a vault original: stamps live in the
                derived copy '<vault>/derived/<uuid>.stamped.pdf'.
------------------------------------------------------------------------------
"""
import hashlib
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from core.stamper import DocumentStamper
from core.vault import remove_derived_files, resolve_view_path, stamped_path_for


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def original(tmp_path: Path) -> Path:
    path = tmp_path / "vault" / "file-uuid.pdf"
    path.parent.mkdir()
    c = canvas.Canvas(str(path))
    c.drawString(100, 100, "Synthetic original content")
    c.save()
    return path


@pytest.fixture
def stamper() -> DocumentStamper:
    return DocumentStamper()


def test_stamp_goes_into_derived_copy(stamper, original):
    digest = _sha(original)

    stamper.stamp_vault_file(str(original), "PAID")

    assert _sha(original) == digest
    assert stamper.get_stamps(str(original)) == []
    assert resolve_view_path(original) == str(stamped_path_for(original))
    assert [s["text"] for s in stamper.get_vault_stamps(str(original))] == ["PAID"]


def test_stamps_accumulate_and_can_be_removed_one_by_one(stamper, original):
    digest = _sha(original)
    stamper.stamp_vault_file(str(original), "PAID")
    stamper.stamp_vault_file(str(original), "BOOKED")
    stamps = stamper.get_vault_stamps(str(original))
    assert sorted(s["text"] for s in stamps) == ["BOOKED", "PAID"]

    paid_id = next(s["id"] for s in stamps if s["text"] == "PAID")
    assert stamper.unstamp_vault_file(str(original), stamp_id=paid_id)
    assert [s["text"] for s in stamper.get_vault_stamps(str(original))] == ["BOOKED"]

    assert stamper.unstamp_vault_file(str(original))
    assert not stamped_path_for(original).exists()
    assert resolve_view_path(original) == str(original)
    assert _sha(original) == digest


def test_stamp_baked_into_original_is_hidden_not_removed(stamper, original, tmp_path):
    # Simulates a file stamped in place by an older version
    baked = tmp_path / "baked.pdf"
    stamper.apply_stamp(str(original), str(baked), "OLD")
    original.write_bytes(baked.read_bytes())
    digest = _sha(original)

    assert stamper.unstamp_vault_file(str(original))

    assert _sha(original) == digest
    assert stamped_path_for(original).exists()
    assert stamper.get_vault_stamps(str(original)) == []


def test_remove_derived_files_drops_stamped_copy(stamper, original):
    stamper.stamp_vault_file(str(original), "PAID")

    remove_derived_files(original)

    assert not stamped_path_for(original).exists()

