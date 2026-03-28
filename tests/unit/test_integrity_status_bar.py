"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_integrity_status_bar.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for IntegrityStatusBar chip visibility and content
                logic. All tests are non-interactive (no dialog shown, no
                real QApplication event loops required beyond qtbot).
------------------------------------------------------------------------------
"""
from unittest.mock import MagicMock
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_v_doc(
    pdf_class: str = "C",
    is_immutable: bool = False,
    extraction_source: str | None = None,
    has_signatures: bool = False,
    finance_body: dict | None = None,
) -> MagicMock:
    """Build a minimal VirtualDocument mock."""
    doc = MagicMock()
    doc.pdf_class = pdf_class
    doc.is_immutable = is_immutable

    sd = MagicMock()
    sd.extraction_source = extraction_source

    audit = MagicMock()
    audit.signatures = {"issuer": "ACME"} if has_signatures else None
    sd.visual_audit = audit

    bodies: dict = {}
    if finance_body is not None:
        fb = MagicMock()
        fb.model_dump.return_value = finance_body
        bodies["finance_body"] = fb
    sd.bodies = bodies
    doc.semantic_data = sd
    return doc


# ---------------------------------------------------------------------------
# Bar visibility
# ---------------------------------------------------------------------------

class TestIntegrityStatusBarVisibility:

    def test_hidden_for_standard_pdf(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="C"))
        assert not bar.isVisible()

    def test_visible_for_signed_pdf(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="A"))
        assert bar.isVisible()

    def test_visible_for_zugferd_pdf(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="B"))
        assert bar.isVisible()

    def test_visible_for_signed_zugferd_pdf(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="AB"))
        assert bar.isVisible()

    def test_visible_for_hybrid_pdf(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="H"))
        assert bar.isVisible()

    def test_hidden_when_v_doc_is_none(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(None)
        assert not bar.isVisible()

    def test_visible_for_zugferd_native_extraction_source(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="C", extraction_source="ZUGFERD_NATIVE"))
        assert bar.isVisible()

    def test_visible_for_forensic_signature_in_audit(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="C", has_signatures=True))
        assert bar.isVisible()


# ---------------------------------------------------------------------------
# Signature chip
# ---------------------------------------------------------------------------

class TestSignatureChip:

    def test_sig_chip_visible_for_class_a(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="A"))
        assert bar._chip_sig.isVisible()

    def test_sig_chip_visible_for_class_ab(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="AB"))
        assert bar._chip_sig.isVisible()

    def test_sig_chip_hidden_for_class_b(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="B"))
        assert not bar._chip_sig.isVisible()

    def test_sig_chip_green_when_immutable(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="A", is_immutable=True))
        assert "#16a34a" in bar._chip_sig.styleSheet()

    def test_sig_chip_amber_when_not_immutable(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="A", is_immutable=False))
        assert "#d97706" in bar._chip_sig.styleSheet()


# ---------------------------------------------------------------------------
# ZUGFeRD chip
# ---------------------------------------------------------------------------

class TestZugferdChip:

    def test_zugferd_chip_visible_for_class_b(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="B"))
        assert bar._chip_zugferd.isVisible()

    def test_zugferd_chip_visible_for_class_ab(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="AB"))
        assert bar._chip_zugferd.isVisible()

    def test_zugferd_chip_hidden_for_class_a(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="A"))
        assert not bar._chip_zugferd.isVisible()

    def test_zugferd_chip_visible_when_native_extraction_source(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="C", extraction_source="ZUGFERD_NATIVE"))
        assert bar._chip_zugferd.isVisible()

    def test_zugferd_chip_stores_finance_data(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(
            _make_v_doc(pdf_class="B", finance_body={"invoice_number": "INV-001"})
        )
        assert bar._zugferd_data == {"invoice_number": "INV-001"}

    def test_zugferd_chip_label_shows_native_hint(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="C", extraction_source="ZUGFERD_NATIVE"))
        assert "native" in bar._chip_zugferd.text()


# ---------------------------------------------------------------------------
# Hybrid chip
# ---------------------------------------------------------------------------

class TestHybridChip:

    def test_hybrid_chip_visible_for_class_h(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="H"))
        assert bar._chip_hybrid.isVisible()

    def test_hybrid_chip_hidden_for_class_a(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="A"))
        assert not bar._chip_hybrid.isVisible()


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------

class TestClear:

    def test_clear_hides_bar(self, qtbot):
        from gui.widgets.integrity_status_bar import IntegrityStatusBar
        bar = IntegrityStatusBar()
        qtbot.addWidget(bar)
        bar.update_from_document(_make_v_doc(pdf_class="A"))
        assert bar.isVisible()
        bar.clear()
        assert not bar.isVisible()
