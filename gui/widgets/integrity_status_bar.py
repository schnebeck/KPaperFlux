"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/integrity_status_bar.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Slim read-only status bar displayed below the PDF viewer
                toolbar. Shows clickable chips for digital signature status,
                ZUGFeRD/EN 16931 structured data, and Hybrid PDF containers.
                Hidden automatically for plain scanned documents.
------------------------------------------------------------------------------
"""
import json
from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from core.logger import get_logger

logger = get_logger("gui.widgets.integrity_status_bar")

# PDF class constants (mirrors PDFClass enum values in core/utils/forensics.py)
_PDF_CLASS_SIGNED = {"A", "AB"}
_PDF_CLASS_ZUGFERD = {"B", "AB"}
_PDF_CLASS_HYBRID = {"H"}

_CHIP_STYLE = (
    "QPushButton {{"
    "  border-radius: 10px; padding: 1px 8px; font-size: 11px;"
    "  font-weight: bold; color: white; background: {color}; border: none;"
    "}}"
    "QPushButton:hover {{ background: {hover}; }}"
)


def _make_chip(label: str, color: str, hover: str, tooltip: str) -> QPushButton:
    btn = QPushButton(label)
    btn.setFixedHeight(20)
    btn.setStyleSheet(_CHIP_STYLE.format(color=color, hover=hover))
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


class _DetailDialog(QDialog):
    """Generic scrollable JSON detail dialog."""

    def __init__(self, title: str, data: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(600, 400)

        layout = QVBoxLayout(self)
        viewer = QTextEdit()
        viewer.setReadOnly(True)
        viewer.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        viewer.setFontFamily("monospace")

        if isinstance(data, (dict, list)):
            text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        else:
            text = str(data) if data else self.tr("No details available.")
        viewer.setPlainText(text)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout.addWidget(viewer)
        layout.addWidget(buttons)


class IntegrityStatusBar(QFrame):
    """
    Slim horizontal bar (28 px) inserted between PDF viewer toolbar and canvas.

    Shows status chips for:
      🛡 Signature  — PDFClass A / AB  (green if immutable-locked, amber otherwise)
      ⚙ ZUGFeRD    — PDFClass B / AB  or extraction_source == 'ZUGFERD_NATIVE'
      📎 Hybrid     — PDFClass H

    The bar is hidden when no chips are active (plain scan / standard PDF).
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._lbl_prefix = QLabel()
        self._lbl_prefix.setStyleSheet("color: #6c757d; font-size: 11px;")
        layout.addWidget(self._lbl_prefix)

        self._chip_sig = _make_chip("", "#16a34a", "#15803d", "")
        self._chip_zugferd = _make_chip("", "#2563eb", "#1d4ed8", "")
        self._chip_hybrid = _make_chip("", "#7c3aed", "#6d28d9", "")

        layout.addWidget(self._chip_sig)
        layout.addWidget(self._chip_zugferd)
        layout.addWidget(self._chip_hybrid)
        layout.addStretch()

        # Store payloads for click handlers
        self._sig_data: Optional[dict] = None
        self._zugferd_data: Optional[dict] = None

        self._chip_sig.clicked.connect(self._on_sig_clicked)
        self._chip_zugferd.clicked.connect(self._on_zugferd_clicked)
        self._chip_hybrid.clicked.connect(self._on_hybrid_clicked)

        self.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_from_document(self, v_doc: Any) -> None:
        """
        Reads forensic fields from a VirtualDocument and refreshes all chips.
        Hides the bar entirely when no chips are visible.

        Args:
            v_doc: A VirtualDocument instance (typed as Any to avoid circular
                   import — duck-typing is sufficient here).
        """
        if v_doc is None:
            self.setVisible(False)
            return

        pdf_class: str = getattr(v_doc, "pdf_class", "C") or "C"
        is_immutable: bool = getattr(v_doc, "is_immutable", False)
        sd = getattr(v_doc, "semantic_data", None)
        extraction_source: str = getattr(sd, "extraction_source", None) if sd else None
        visual_audit = getattr(sd, "visual_audit", None) if sd else None
        bodies: dict = getattr(sd, "bodies", {}) if sd else {}

        # --- Signature chip ---
        show_sig = pdf_class in _PDF_CLASS_SIGNED or bool(
            visual_audit and getattr(visual_audit, "signatures", None)
        )
        if show_sig:
            if is_immutable:
                self._apply_chip(self._chip_sig, "🛡 Signature", "#16a34a", "#15803d",
                                 self.tr("Digital signature verified — document is immutable"))
            else:
                self._apply_chip(self._chip_sig, "🛡 Signature", "#d97706", "#b45309",
                                 self.tr("Digital signature detected — not yet immutability-locked"))
            self._sig_data = (
                visual_audit.signatures if visual_audit and hasattr(visual_audit, "signatures") else None
            )
        self._chip_sig.setVisible(show_sig)

        # --- ZUGFeRD chip ---
        show_zugferd = pdf_class in _PDF_CLASS_ZUGFERD or extraction_source == "ZUGFERD_NATIVE"
        if show_zugferd:
            source_hint = " (native)" if extraction_source == "ZUGFERD_NATIVE" else ""
            self._apply_chip(self._chip_zugferd, f"⚙ ZUGFeRD{source_hint}", "#2563eb", "#1d4ed8",
                             self.tr("EN 16931 / ZUGFeRD structured data embedded. Click to inspect."))
            finance = bodies.get("finance_body")
            if finance is not None and hasattr(finance, "model_dump"):
                self._zugferd_data = finance.model_dump(mode="json")
            elif isinstance(finance, dict):
                self._zugferd_data = finance
            else:
                self._zugferd_data = None
        self._chip_zugferd.setVisible(show_zugferd)

        # --- Hybrid chip ---
        show_hybrid = pdf_class in _PDF_CLASS_HYBRID
        self._chip_hybrid.setVisible(show_hybrid)
        if show_hybrid:
            self._apply_chip(self._chip_hybrid, "📎 Hybrid PDF", "#7c3aed", "#6d28d9",
                             self.tr("KPaperFlux Hybrid Container — original signed document embedded"))

        any_visible = show_sig or show_zugferd or show_hybrid
        self._lbl_prefix.setText(self.tr("Document integrity:") if any_visible else "")
        self.setVisible(any_visible)

    def clear(self) -> None:
        """Hides the bar (e.g. when the viewer is cleared)."""
        self.setVisible(False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_chip(btn: QPushButton, label: str, color: str, hover: str, tooltip: str) -> None:
        btn.setText(label)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(_CHIP_STYLE.format(color=color, hover=hover))

    # ------------------------------------------------------------------
    # Click handlers
    # ------------------------------------------------------------------

    def _on_sig_clicked(self) -> None:
        dlg = _DetailDialog(
            self.tr("Signature Details"),
            self._sig_data,
            self,
        )
        dlg.exec()

    def _on_zugferd_clicked(self) -> None:
        dlg = _DetailDialog(
            self.tr("ZUGFeRD / EN 16931 Finance Data"),
            self._zugferd_data,
            self,
        )
        dlg.exec()

    def _on_hybrid_clicked(self) -> None:
        _DetailDialog(
            self.tr("Hybrid PDF"),
            self.tr(
                "This document is a KPaperFlux Hybrid Container.\n\n"
                "It combines a human-readable scan with an immutable signed "
                "digital original embedded as an attachment.\n\n"
                "Use Export → Save Attachment to extract the original."
            ),
            self,
        ).exec()

    def changeEvent(self, event: Any) -> None:
        from PyQt6.QtCore import QEvent
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self) -> None:
        """Re-apply current locale to visible chips (called on LanguageChange)."""
        self._lbl_prefix.setText(self.tr("Document integrity:") if self.isVisible() else "")
