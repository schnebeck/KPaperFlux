"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/workflow_state_graph.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Mini workflow state graph widget.  Shows the current state
                (green border) with all outgoing transitions as clickable
                arrows leading to their target states.  Clicking a transition
                row selects a pending action; "Übernehmen" then commits it.
                A final state is shown with a red border and no transitions.
------------------------------------------------------------------------------
"""
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygon,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

from core.workflow import WorkflowRule


class WorkflowStateGraphWidget(QWidget):
    """Compact directed graph: current state + clickable outgoing transitions.

    Visual layout (for two transitions):

        ┌──────────────┐         ┌──────────────┐
        │ CURRENT      │─action1─▶│ TARGET1      │
        │ (green/red)  │         └──────────────┘
        │              │         ┌──────────────┐
        └──────────────┘─action2─▶│ TARGET2      │
                                  └──────────────┘

    Clicking anywhere in an arrow+target row selects that transition
    (highlights the row in blue).  The parent widget reads
    ``pending_action`` / ``pending_target`` and calls ``clear_selection()``
    after the transition has been applied.
    """

    transition_clicked = pyqtSignal(str, str)  # (action, target_step)

    _BOX_W = 140
    _BOX_H = 38
    _ARROW_LEN = 100
    _ROW_GAP = 10
    _PAD_H = 20
    _PAD_V = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rule: Optional[WorkflowRule] = None
        self._current_step: str = ""
        self._transitions: List[Tuple[str, str, str]] = []  # [(action_id, display_label, target)]
        self._pending_action: Optional[str] = None
        self._pending_target: Optional[str] = None
        self._hit_areas: List[Tuple[QRect, str, str]] = []
        self._hovered_idx: Optional[int] = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._recalc_height()

    # ── Public API ────────────────────────────────────────────────────────────

    def update_state(self, rule: Optional[WorkflowRule], current_step: str) -> None:
        """Rebuild the graph from *current_step* in *rule*.

        If *current_step* is not found in the rule's states (e.g. a stale "NEW"
        from before ``get_initial_state`` was used), fall back to the rule's
        computed initial state so the graph is never empty.
        """
        self._rule = rule
        self._current_step = current_step
        self._pending_action = None
        self._pending_target = None
        self._hovered_idx = None
        self._transitions = []
        if rule:
            if current_step not in rule.states:
                from core.workflow import get_initial_state
                self._current_step = get_initial_state(rule) or current_step
            state_def = rule.states.get(self._current_step)
            if state_def and not state_def.final:
                for t in state_def.transitions:
                    display = t.label if t.label else t.action
                    self._transitions.append((t.action, display, t.target))
        self._recalc_height()
        self.update()

    @property
    def pending_action(self) -> Optional[str]:
        return self._pending_action

    @property
    def pending_target(self) -> Optional[str]:
        return self._pending_target

    def has_selection(self) -> bool:
        return self._pending_action is not None

    def clear_selection(self) -> None:
        self._pending_action = None
        self._pending_target = None
        self.update()

    # ── Size ──────────────────────────────────────────────────────────────────

    def _recalc_height(self) -> None:
        n = max(1, len(self._transitions))
        h = self._PAD_V * 2 + n * self._BOX_H + (n - 1) * self._ROW_GAP
        self.setFixedHeight(h)

    def sizeHint(self) -> QSize:
        w = self._PAD_H * 2 + self._BOX_W + self._ARROW_LEN + self._BOX_W
        n = max(1, len(self._transitions))
        h = self._PAD_V * 2 + n * self._BOX_H + (n - 1) * self._ROW_GAP
        return QSize(w, h)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._hit_areas.clear()

        total_h = self.height()
        n = len(self._transitions)
        rows_h = max(1, n) * self._BOX_H + max(0, n - 1) * self._ROW_GAP

        # Current state box — vertically centered relative to all target rows
        cur_x = self._PAD_H
        cur_y = (total_h - self._BOX_H) // 2
        cur_rect = QRect(cur_x, cur_y, self._BOX_W, self._BOX_H)
        is_final = self._is_final(self._current_step)
        self._draw_box(p, cur_rect, self._state_label(self._current_step),
                       is_current=True, is_final=is_final, highlighted=False)

        if not self._transitions:
            p.end()
            return

        src_x = cur_x + self._BOX_W
        src_y = cur_y + self._BOX_H // 2
        target_x = src_x + self._ARROW_LEN
        rows_top = (total_h - rows_h) // 2

        for i, (action_id, display_label, target) in enumerate(self._transitions):
            row_y = rows_top + i * (self._BOX_H + self._ROW_GAP)
            dst_y = row_y + self._BOX_H // 2
            target_rect = QRect(target_x, row_y, self._BOX_W, self._BOX_H)

            selected = (action_id == self._pending_action and target == self._pending_target)
            hovered = (i == self._hovered_idx)
            active = selected or hovered

            self._draw_arrow(p, QPoint(src_x, src_y), QPoint(target_x, dst_y),
                             display_label, active, selected)

            target_final = self._is_final(target)
            self._draw_box(p, target_rect, self._state_label(target),
                           is_current=False, is_final=target_final,
                           highlighted=active)

            hit = QRect(src_x, row_y, self._ARROW_LEN + self._BOX_W, self._BOX_H)
            self._hit_areas.append((hit, action_id, target))

        p.end()

    # ── Drawing helpers ───────────────────────────────────────────────────────

    def _is_final(self, step: str) -> bool:
        if not self._rule:
            return False
        sd = self._rule.states.get(step)
        return sd is not None and sd.final

    def _state_label(self, step: str) -> str:
        """Return the locale-resolved display label for *step*."""
        if self._rule:
            return self._rule.get_state_label(step)
        return step

    def _draw_box(self, p: QPainter, rect: QRect, label: str,
                  is_current: bool, is_final: bool, highlighted: bool) -> None:
        if is_current and is_final:
            bg = QColor("#fce4ec")
            border = QColor("#c62828")
            border_w = 2.5
            fg = QColor("#b71c1c")
        elif is_current:
            bg = QColor("#e8f5e9")
            border = QColor("#2e7d32")
            border_w = 2.5
            fg = QColor("#1b5e20")
        elif highlighted:
            bg = QColor("#e3f2fd")
            border = QColor("#1565c0")
            border_w = 2.0
            fg = QColor("#0d47a1")
        else:
            bg = QColor("#f5f5f5")
            border = QColor("#bdbdbd")
            border_w = 1.0
            fg = QColor("#424242")

        p.setBrush(QBrush(bg))
        p.setPen(QPen(border, border_w))
        path = QPainterPath()
        path.addRoundedRect(float(rect.x()), float(rect.y()),
                            float(rect.width()), float(rect.height()), 8.0, 8.0)
        p.drawPath(path)

        p.setPen(QPen(fg))
        font = QFont()
        font.setPointSize(10)
        font.setBold(is_current)
        p.setFont(font)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_arrow(self, p: QPainter, src: QPoint, dst: QPoint,
                    label: str, active: bool, selected: bool) -> None:
        color = (QColor("#1565c0") if selected
                 else QColor("#1976d2") if active
                 else QColor("#90a4ae"))
        pen_w = 2.0 if selected else 1.5
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(color, pen_w))

        # Elbow: horizontal third, then straight to target
        elbow_x = src.x() + self._ARROW_LEN // 3
        p.drawLine(src, QPoint(elbow_x, src.y()))
        p.drawLine(QPoint(elbow_x, src.y()), QPoint(dst.x() - 10, dst.y()))

        # Arrowhead
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))
        p.drawPolygon(QPolygon([
            QPoint(dst.x() - 10, dst.y() - 4),
            QPoint(dst.x(), dst.y()),
            QPoint(dst.x() - 10, dst.y() + 4),
        ]))

        # Action label at midpoint of the diagonal segment
        mid_x = (elbow_x + dst.x() - 10) // 2
        mid_y = (src.y() + dst.y()) // 2
        p.setPen(QPen(color))
        font = QFont()
        font.setPointSize(9)
        font.setItalic(True)
        p.setFont(font)
        lbl_rect = QRect(mid_x - 40, mid_y - 11, 80, 18)
        p.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, label)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.pos()
        idx = next(
            (i for i, (r, _, _) in enumerate(self._hit_areas) if r.contains(pos)),
            None,
        )
        if idx != self._hovered_idx:
            self._hovered_idx = idx
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if idx is not None
                else Qt.CursorShape.ArrowCursor
            )
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hovered_idx is not None:
            self._hovered_idx = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        for rect, action, target in self._hit_areas:
            if rect.contains(event.pos()):
                self._pending_action = action
                self._pending_target = target
                self.update()
                self.transition_clicked.emit(action, target)
                return
