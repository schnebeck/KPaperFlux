"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/workflow_dashboard.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Workflow dashboard and processing widgets: WorkflowRuleCard,
                _CardBoard, WorkflowDashboardWidget, WorkflowProcessingWidget.
------------------------------------------------------------------------------
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QTimer, QSettings, QPoint, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QMessageBox, QSplitter,
    QScrollArea, QProgressBar,
)

from core.logger import get_logger
from core.workflow import WorkflowRule, WorkflowRuleRegistry
from gui.cockpit import CELL_WIDTH, CELL_HEIGHT, SPACING, MARGIN, StatCard
from gui.widgets.workflow_graph import WorkflowGraphWidget

logger = get_logger("gui.widgets.workflow_dashboard")

_RULE_CARD_COLORS = [
    "#6366f1", "#f59e0b", "#10b981", "#ec4899",
    "#0ea5e9", "#84cc16", "#f97316", "#14b8a6",
]


class WorkflowRuleCard(QFrame):
    """Card tile for a workflow rule, styled like StatCard."""

    def __init__(self, rule: "WorkflowRule", open_count: int, done_count: int,
                 color: str, parent=None):
        super().__init__(parent)
        self.rule_id = rule.id
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setObjectName("WorkflowRuleCard")
        self.setFixedSize(CELL_WIDTH, CELL_HEIGHT)
        self._pos_anim = QPropertyAnimation(self, b"pos")
        self._pos_anim.setDuration(350)
        self._pos_anim.setEasingCurve(QEasingCurve.Type.OutQuint)
        from gui.theme import (
            CLR_BORDER, CLR_TEXT, CLR_TEXT_SECONDARY, CLR_TEXT_MUTED,
            FONT_BASE, FONT_LG, FONT_METRIC, FONT_ICON, PROGRESS_H,
            RADIUS_MD, progress_bar as _progress_bar,
        )
        self.setStyleSheet(f"""
            QFrame#WorkflowRuleCard {{
                background: white;
                border: 1px solid {CLR_BORDER};
                border-radius: {RADIUS_MD}px;
            }}
            QFrame#WorkflowRuleCard:hover {{
                border: 1.5px solid {color};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 12)
        layout.setSpacing(4)

        # Title row
        title_row = QHBoxLayout()
        icon_lbl = QLabel("🔄")
        icon_lbl.setStyleSheet(
            f"font-size: {FONT_ICON}px; background: {color}25; padding: 5px; border-radius: {RADIUS_MD}px;"
        )
        title_row.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)
        name_lbl = QLabel(rule.get_display_name() or rule.id)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(f"color: {CLR_TEXT_SECONDARY}; font-weight: 600; font-size: {FONT_BASE}px;")
        title_row.addWidget(name_lbl, 1, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(title_row)

        # Open count (big number)
        count_lbl = QLabel(str(open_count))
        count_lbl.setStyleSheet(f"color: {CLR_TEXT}; font-weight: 800; font-size: {FONT_METRIC}px;")
        layout.addWidget(count_lbl)

        open_lbl = QLabel(self.tr("open"))
        open_lbl.setStyleSheet(f"color: {CLR_TEXT_MUTED}; font-size: {FONT_LG}px;")
        layout.addWidget(open_lbl)

        layout.addStretch()

        # Completion rate bar
        total = open_count + done_count
        rate_pct = round(done_count / total * 100) if total > 0 else 0
        rate_row = QHBoxLayout()
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(rate_pct)
        bar.setFixedHeight(PROGRESS_H)
        bar.setTextVisible(False)
        bar.setStyleSheet(_progress_bar(color))
        rate_row.addWidget(bar, 1)
        rate_lbl = QLabel(f"{rate_pct}%")
        rate_lbl.setStyleSheet(f"color: {CLR_TEXT_MUTED}; font-size: {FONT_LG}px; min-width: 32px;")
        rate_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rate_row.addWidget(rate_lbl)
        layout.addLayout(rate_row)

    def move_animated(self, new_pos: "QPoint") -> None:
        if self.pos() == new_pos:
            return
        self._pos_anim.stop()
        self._pos_anim.setEndValue(new_pos)
        self._pos_anim.start()


class _CardBoard(QWidget):
    """Scrollable grid that holds both fixed StatCards and draggable WorkflowRuleCards.

    Row 0 contains the three overview StatCards (not draggable).
    Row 1+ contains WorkflowRuleCards that can be freely rearranged.
    """

    navigate_clicked = pyqtSignal(dict)   # overview card click
    process_clicked = pyqtSignal(str)     # rule card click → rule_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._overview: List["StatCard"] = []
        self._rule_cards: List[WorkflowRuleCard] = []
        self._rule_cfgs: List[Dict[str, Any]] = []
        self._dragging: Optional[WorkflowRuleCard] = None
        self._drag_start_mouse = QPoint()
        self._drag_start_widget = QPoint()
        self._drag_moved = False

    # ── geometry helpers ──────────────────────────────────────────────────────

    def _pos(self, row: int, col: int) -> QPoint:
        return QPoint(
            MARGIN + col * (CELL_WIDTH + SPACING),
            MARGIN + row * (CELL_HEIGHT + SPACING),
        )

    def _cell(self, pos: QPoint):
        col = max(0, int((pos.x() - MARGIN + (CELL_WIDTH + SPACING) // 2) // (CELL_WIDTH + SPACING)))
        row = max(0, int((pos.y() - MARGIN + (CELL_HEIGHT + SPACING) // 2) // (CELL_HEIGHT + SPACING)))
        return row, col

    def _resize(self):
        if self._rule_cfgs:
            max_row = max(c["row"] for c in self._rule_cfgs)
            max_col = max(c["col"] for c in self._rule_cfgs)
        else:
            max_row, max_col = 1, 2
        self.setFixedSize(
            MARGIN * 2 + (max(2, max_col) + 1) * (CELL_WIDTH + SPACING),
            MARGIN * 2 + (max(1, max_row) + 1) * (CELL_HEIGHT + SPACING),
        )

    # ── public API ────────────────────────────────────────────────────────────

    def set_cards(
        self,
        overview: List,
        rule_cards: List[WorkflowRuleCard],
        rule_cfgs: List[Dict[str, Any]],
    ) -> None:
        self._overview = overview
        self._rule_cards = rule_cards
        self._rule_cfgs = rule_cfgs
        self._resize()

    # ── drag handling ─────────────────────────────────────────────────────────

    def _find_card(self, child):
        if isinstance(child, (StatCard, WorkflowRuleCard)):
            return child
        if child and isinstance(child.parent(), (StatCard, WorkflowRuleCard)):
            return child.parent()
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        card = self._find_card(self.childAt(event.position().toPoint()))
        if isinstance(card, StatCard):
            self.navigate_clicked.emit({"query": card.filter_query})
        elif isinstance(card, WorkflowRuleCard):
            self._dragging = card
            self._drag_start_mouse = event.position().toPoint()
            self._drag_start_widget = card.pos()
            self._drag_moved = False
            card.raise_()
            card.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return super().mouseMoveEvent(event)
        delta = event.position().toPoint() - self._drag_start_mouse
        if not self._drag_moved and delta.manhattanLength() > 5:
            self._drag_moved = True
        if self._drag_moved:
            new_pos = self._drag_start_widget + delta
            self._dragging.move(new_pos)
            row, col = self._cell(new_pos)
            row = max(1, row)  # prevent dragging into overview row 0
            self._handle_swap(row, col)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._dragging:
            return super().mouseReleaseEvent(event)
        self._dragging.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if not self._drag_moved:
            self.process_clicked.emit(self._dragging.rule_id)
        else:
            idx = self._rule_cards.index(self._dragging)
            cfg = self._rule_cfgs[idx]
            self._dragging.move_animated(self._pos(cfg["row"], cfg["col"]))
            self._save_order()
        self._dragging = None
        super().mouseReleaseEvent(event)

    def _handle_swap(self, target_row: int, target_col: int):
        drag_idx = self._rule_cards.index(self._dragging)
        orig_row = self._rule_cfgs[drag_idx]["row"]
        orig_col = self._rule_cfgs[drag_idx]["col"]
        if orig_row == target_row and orig_col == target_col:
            return
        for i, cfg in enumerate(self._rule_cfgs):
            if i != drag_idx and cfg["row"] == target_row and cfg["col"] == target_col:
                cfg["row"] = orig_row
                cfg["col"] = orig_col
                self._rule_cards[i].move_animated(self._pos(orig_row, orig_col))
                break
        self._rule_cfgs[drag_idx]["row"] = target_row
        self._rule_cfgs[drag_idx]["col"] = target_col
        self._resize()

    def _save_order(self):
        order = [{"rule_id": c["rule_id"], "row": c["row"], "col": c["col"]}
                 for c in self._rule_cfgs]
        settings = QSettings()
        settings.setValue("workflow_dashboard/rule_order", json.dumps(order))


class WorkflowDashboardWidget(QWidget):
    """Overview of workflow performance and document distribution."""
    navigation_requested = pyqtSignal(dict)
    process_requested = pyqtSignal(list, str, str)  # docs, rule_id, label

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self._rules: List[WorkflowRule] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: #f3f4f6;")

        self._board = _CardBoard()
        self._board.navigate_clicked.connect(self.navigation_requested.emit)
        self._board.process_clicked.connect(self._on_rule_card_clicked)

        scroll.setWidget(self._board)
        layout.addWidget(scroll)

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
            self.refresh()
        super().changeEvent(event)

    def retranslate_ui(self):
        self.refresh()

    def refresh(self):
        """Fetch fresh data from DB and rebuild all cards."""
        if not self.db_manager:
            return

        # Clear previous cards
        for card in self._board._overview + self._board._rule_cards:
            card.deleteLater()

        # ── Overview row (row 0, fixed) ───────────────────────────────────────
        total_q = {"field": "workflow_step", "op": "is_not_empty", "value": None}
        urgent_q = {"field": "workflow_step", "op": "equals", "value": "URGENT"}
        new_q = {"field": "workflow_step", "op": "equals", "value": "NEW"}

        overview_data = [
            (self.tr("Total in Pipeline"), total_q, "#3b82f6"),
            (self.tr("Urgent Actions"), urgent_q, "#ef4444"),
            (self.tr("New Tasks"), new_q, "#10b981"),
        ]
        overview_cards = []
        for col, (title, query, color) in enumerate(overview_data):
            _raw = self.db_manager.count_documents_advanced(query)
            count = int(_raw) if isinstance(_raw, (int, float)) else 0
            card = StatCard(title, count, color, query, parent=self._board)
            card.move(self._board._pos(0, col))
            card.show()
            overview_cards.append(card)

        # ── Rule cards (row 1+, draggable) ────────────────────────────────────
        registry = WorkflowRuleRegistry()
        rules = registry.list_rules()
        self._rules = rules

        # Load saved order
        settings = QSettings()
        try:
            saved_order = json.loads(settings.value("workflow_dashboard/rule_order", "[]"))
        except Exception:
            saved_order = []
        saved_positions = {e["rule_id"]: (e["row"], e["col"]) for e in saved_order if "rule_id" in e}

        rule_cfgs: List[Dict[str, Any]] = []
        used: set = set()

        for i, rule in enumerate(rules):
            if rule.id in saved_positions:
                row, col = saved_positions[rule.id]
                row = max(1, row)
            else:
                # Auto-place: 3 columns starting at row 1
                row = 1 + i // 3
                col = i % 3
            # Resolve conflicts
            while (row, col) in used:
                col += 1
                if col > 5:
                    col = 0
                    row += 1
            used.add((row, col))
            rule_cfgs.append({"rule_id": rule.id, "row": row, "col": col})

        rule_cards: List[WorkflowRuleCard] = []
        for cfg, rule in zip(rule_cfgs, rules):
            field = f"semantic:workflows.{rule.id}.current_step"
            total_q_r = {"field": field, "op": "is_not_empty", "value": None}
            _raw_total = self.db_manager.count_documents_advanced(total_q_r)
            total = int(_raw_total) if isinstance(_raw_total, (int, float)) else 0
            final_states = [sid for sid, s in rule.states.items() if s.final]
            done = 0
            if final_states:
                done_q = {"field": field, "op": "in", "value": final_states}
                _raw_done = self.db_manager.count_documents_advanced(done_q)
                done = int(_raw_done) if isinstance(_raw_done, (int, float)) else 0
            color = _RULE_CARD_COLORS[rules.index(rule) % len(_RULE_CARD_COLORS)]
            card = WorkflowRuleCard(rule, total - done, done, color, parent=self._board)
            card.move(self._board._pos(cfg["row"], cfg["col"]))
            card.show()
            rule_cards.append(card)

        self._board.set_cards(overview_cards, rule_cards, rule_cfgs)

    def _on_rule_card_clicked(self, rule_id: str) -> None:
        rule = next((r for r in self._rules if r.id == rule_id), None)
        if not rule:
            return
        field = f"semantic:workflows.{rule.id}.current_step"
        query = {"field": field, "op": "is_not_empty", "value": None}
        self._open_processing(rule, query)

    def _open_processing(self, rule, query: dict) -> None:
        """Fetch open documents for *rule* and emit process_requested."""
        if not self.db_manager:
            return
        try:
            all_docs = self.db_manager.search_documents_advanced(query)
            # Keep only docs not yet in a final state
            open_docs = [
                doc for doc in all_docs
                if doc.semantic_data
                and rule.id in doc.semantic_data.workflows
                and not (
                    rule.states.get(doc.semantic_data.workflows[rule.id].current_step)
                    and rule.states[doc.semantic_data.workflows[rule.id].current_step].final
                )
            ]
            label = self.tr("Processing: %s") % (rule.get_display_name() or rule.id)
            self.process_requested.emit(open_docs, rule.id, label)
        except Exception as exc:
            logger.warning(f"Failed to load docs for processing: {exc}")


class WorkflowProcessingWidget(QWidget):
    """Active workflow processing view.

    Left panel — three visually separated sections stacked top-to-bottom:
      1. Navigation bar  (Prev / counter / Next / filename)
      2. Rule context    (rule name + WorkflowStateGraphWidget + Übernehmen)
      3. MetadataEditor  (all metadata tabs, no workflow controls bar)

    Right panel — PDF viewer at full height.
    """

    transition_done = pyqtSignal()

    def __init__(self, pipeline=None, db_manager=None, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.db_manager = db_manager
        self._docs: List[Any] = []
        self._current_index: int = 0
        self._rule_id: Optional[str] = None
        self._init_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        from gui.metadata_editor import MetadataEditorWidget
        from gui.pdf_viewer import PdfViewerWidget

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.splitterMoved.connect(self._save_splitter)

        # ── LEFT panel ────────────────────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Section 1 — Navigation bar
        nav_bar = QWidget()
        nav_bar.setFixedHeight(38)
        nav_bar.setStyleSheet(
            "background: #f0f4f8; border-bottom: 2px solid #dce1e8;"
        )
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(10, 0, 10, 0)
        nav_layout.setSpacing(8)

        self._btn_prev = QPushButton("◀ " + self.tr("Prev"))
        self._btn_prev.setFixedHeight(28)
        self._btn_prev.clicked.connect(self._prev)
        nav_layout.addWidget(self._btn_prev)

        self._lbl_nav = QLabel("0 / 0")
        self._lbl_nav.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_nav.setStyleSheet("font-weight: bold; min-width: 60px;")
        nav_layout.addWidget(self._lbl_nav)

        self._btn_next = QPushButton(self.tr("Next") + " ▶")
        self._btn_next.setFixedHeight(28)
        self._btn_next.clicked.connect(self._next)
        nav_layout.addWidget(self._btn_next)

        nav_layout.addStretch()

        self._lbl_title = QLabel()
        self._lbl_title.setStyleSheet("color: #555; font-size: 12px;")
        nav_layout.addWidget(self._lbl_title)

        left_layout.addWidget(nav_bar)

        # Section 2 — Rule context: full WorkflowGraphWidget in run mode
        rule_ctx = QFrame()
        rule_ctx.setStyleSheet("border-bottom: 2px solid #dce1e8;")
        rule_ctx.setMinimumHeight(220)
        rule_ctx_layout = QVBoxLayout(rule_ctx)
        rule_ctx_layout.setContentsMargins(0, 0, 0, 0)
        rule_ctx_layout.setSpacing(0)

        self._state_graph = WorkflowGraphWidget(mode="run")
        self._state_graph.transition_triggered.connect(self._on_transition_triggered)
        rule_ctx_layout.addWidget(self._state_graph)

        left_layout.addWidget(rule_ctx)

        # Section 3 — MetadataEditor (no workflow UI)
        self._metadata_editor = MetadataEditorWidget(
            db_manager=self.db_manager, pipeline=self.pipeline
        )
        self._metadata_editor.set_workflow_ui_visible(False)
        self._metadata_editor.metadata_saved.connect(self.transition_done)
        left_layout.addWidget(self._metadata_editor, 1)

        self._splitter.addWidget(left)

        # ── RIGHT panel — PDF viewer full height ──────────────────────────────
        self._pdf_viewer = PdfViewerWidget(pipeline=self.pipeline)
        self._pdf_viewer.set_toolbar_policy("audit")
        self._splitter.addWidget(self._pdf_viewer)

        # Restore splitter
        saved = QSettings().value("workflow_processing/splitter_state")
        if saved:
            self._splitter.restoreState(saved)
        else:
            self._splitter.setSizes([420, 580])

        outer.addWidget(self._splitter, 1)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_documents(self, docs: List[Any], rule_id: str, label: str) -> None:
        """Load *docs* for processing under *rule_id*."""
        self._docs = docs
        self._rule_id = rule_id
        self._current_index = 0
        self._show_current()

    def set_db_manager(self, db_manager) -> None:
        self.db_manager = db_manager
        if hasattr(self, "_metadata_editor"):
            self._metadata_editor.db_manager = db_manager

    # ── Navigation ────────────────────────────────────────────────────────────

    def _prev(self) -> None:
        if self._current_index > 0:
            self._current_index -= 1
            self._show_current()

    def _next(self) -> None:
        if self._current_index < len(self._docs) - 1:
            self._current_index += 1
            self._show_current()

    # ── Display ───────────────────────────────────────────────────────────────

    def _show_current(self) -> None:
        total = len(self._docs)
        if not total:
            self._lbl_nav.setText("0 / 0")
            self._lbl_title.setText("")
            self._btn_prev.setEnabled(False)
            self._btn_next.setEnabled(False)
            self._state_graph.load(None)
            self._metadata_editor.clear()
            return

        idx = self._current_index
        self._lbl_nav.setText(f"{idx + 1} / {total}")
        self._btn_prev.setEnabled(idx > 0)
        self._btn_next.setEnabled(idx < total - 1)

        doc = self._docs[idx]
        self._lbl_title.setText(
            getattr(doc, "original_filename", None) or str(doc.uuid)
        )

        self._pdf_viewer.load_document(doc)
        self._metadata_editor.display_documents([doc])

        # Feed the workflow graph with actual semantic data for condition evaluation.
        # Build a flat dict using the VirtualDocument properties so that transition
        # required_fields (e.g. "iban", "total_gross") resolve correctly.
        registry = WorkflowRuleRegistry()
        rule = registry.get_rule(self._rule_id) if self._rule_id else None
        sd = getattr(doc, "semantic_data", None)
        wi = (sd.workflows.get(self._rule_id)
              if (sd and self._rule_id) else None)
        from datetime import datetime as _dt  # noqa: PLC0415
        now = _dt.now()
        doc_data: dict = {
            "total_gross": getattr(doc, "total_amount", None),
            "iban":        getattr(doc, "iban", None),
            "sender_name": getattr(doc, "sender_name", None),
            "doc_date":    getattr(doc, "doc_date", None),
            "doc_number":  getattr(doc, "doc_number", None),
            "AGE_DAYS":    0,
            "DAYS_IN_STATE": 0,
            "DAYS_UNTIL_DUE": 999,
        }
        try:
            if getattr(doc, "created_at", None):
                doc_data["AGE_DAYS"] = (now - _dt.fromisoformat(doc.created_at)).days
        except Exception as exc:
            logger.debug(f"AGE_DAYS skipped: {exc}")
        if wi and wi.history:
            try:
                last_ts = wi.history[-1].timestamp
                doc_data["DAYS_IN_STATE"] = (now - _dt.fromisoformat(last_ts)).days
            except Exception as exc:
                logger.debug(f"DAYS_IN_STATE skipped: {exc}")
        self._state_graph.load(rule, wi, doc_data)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_transition_triggered(
        self, rule_id: str, action: str, target: str, is_auto: bool
    ) -> None:
        """Apply the clicked transition immediately to the current document."""
        if not self._docs or not self.db_manager:
            return
        doc = self._docs[self._current_index]
        sd = getattr(doc, "semantic_data", None)
        try:
            if sd and self._rule_id and self._rule_id in sd.workflows:
                sd.workflows[self._rule_id].apply_transition(action, target, user="USER")
                self.db_manager.update_document_metadata(doc.uuid, {"semantic_data": sd})
        except Exception as e:
            logger.error(f"Workflow transition failed: {e}")
            QMessageBox.warning(
                self, self.tr("Transition Failed"),
                self.tr("Could not apply workflow transition: %1").replace("%1", str(e))
            )
            return
        self._show_current()
        self.transition_done.emit()

    def _save_splitter(self) -> None:
        QSettings().setValue(
            "workflow_processing/splitter_state", self._splitter.saveState()
        )
