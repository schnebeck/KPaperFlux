"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/workflow_graph.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Visual state-machine widget for workflow rules.
                Supports two modes:
                  "run"  — read-only graph with highlighted current state and
                           clickable available transitions.
                  "edit" — interactive editor: drag nodes, add/remove states
                           and transitions, inline property panel.
------------------------------------------------------------------------------
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath,
    QPainterPathStroker, QPen, QPolygonF, QCursor,
)
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QGraphicsItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from core.logger import get_logger
from core.workflow import (
    WorkflowEngine, WorkflowRule, WorkflowState, WorkflowTransition,
    StateType, make_state_id, make_action_id,
)

logger = get_logger("gui.widgets.workflow_graph")

# ── Layout geometry ───────────────────────────────────────────────────────────
NODE_W: int = 160
NODE_H: int = 48
H_GAP: int = 90        # horizontal gap between layers
V_GAP: int = 44        # vertical gap between nodes in same layer
ARROW: int = 9         # arrowhead size
BORDER_R: int = 10     # corner radius
BACK_DROP: int = 70    # how far back-edges arc below the nodes
MULTI_OFF: int = 16    # y-offset between parallel edges

ANCHOR_NAMES: List[str] = [
    "right", "left", "top", "bottom",
    "top-right", "top-left", "bottom-right", "bottom-left",
]
CTRL_DIST_MIN: float = 60.0  # minimum Bezier control-point distance
ANCHOR_SNAP: float = 34.0    # max distance to snap to an anchor


def _anchor_point(center: QPointF, anchor: str) -> QPointF:
    """Scene point for a named anchor on a node centred at *center*."""
    hw, hh = NODE_W / 2.0, NODE_H / 2.0
    x, y = center.x(), center.y()
    return {
        "right":        QPointF(x + hw, y),
        "left":         QPointF(x - hw, y),
        "top":          QPointF(x,       y - hh),
        "bottom":       QPointF(x,       y + hh),
        "top-right":    QPointF(x + hw,  y - hh),
        "top-left":     QPointF(x - hw,  y - hh),
        "bottom-right": QPointF(x + hw,  y + hh),
        "bottom-left":  QPointF(x - hw,  y + hh),
    }.get(anchor, QPointF(x + hw, y))


def _anchor_tangent(anchor: str) -> QPointF:
    """Outward unit tangent vector for an anchor."""
    s = 0.7071
    return {
        "right":        QPointF( 1,  0),
        "left":         QPointF(-1,  0),
        "top":          QPointF( 0, -1),
        "bottom":       QPointF( 0,  1),
        "top-right":    QPointF( s, -s),
        "top-left":     QPointF(-s, -s),
        "bottom-right": QPointF( s,  s),
        "bottom-left":  QPointF(-s,  s),
    }.get(anchor, QPointF(1, 0))

# ── Colours ───────────────────────────────────────────────────────────────────
C_CURRENT  = QColor("#0d47a1")
C_VISITED  = QColor("#607d8b")
C_DEFAULT  = QColor("#37474f")
C_FINAL_OK = QColor("#1b5e20")
C_FINAL_NG = QColor("#b71c1c")
C_AVAIL    = QColor("#0d47a1")
C_BLOCKED  = QColor("#90a4ae")
C_AUTO     = QColor("#bf360c")
C_BG_CUR   = QColor("#dbeafe")
C_BG_TGT   = QColor("#e8f0fe")   # available-target highlight (run mode)
C_BG_VIS   = QColor("#e8ecef")
C_BG_DEF   = QColor("#f8fafd")
C_PENDING  = QColor("#00796b")   # teal — active selection border
C_BG_PEND  = QColor("#e0f2f1")   # teal-light — active selection fill
C_SCENE_BG = QColor("#e4e9ef")


# ── Layout algorithm ──────────────────────────────────────────────────────────

def _compute_layout(rule: WorkflowRule) -> Dict[str, QPointF]:
    """
    Layered left-to-right layout via BFS from 'NEW' (or first state).
    If rule.node_positions contains an entry for a state the stored position
    is used instead of the computed one (user override).
    Back-edges (target layer <= source layer) are detected and drawn as arcs.
    Returns a dict mapping state_id → scene position (centre of node).
    """
    state_ids = list(rule.states.keys())
    if not state_ids:
        return {}

    # Build forward adjacency
    adj: Dict[str, List[str]] = {s: [] for s in state_ids}
    for sid, sdef in rule.states.items():
        for t in sdef.transitions:
            if t.target in adj:
                adj[sid].append(t.target)

    # BFS layer assignment
    start = "NEW" if "NEW" in rule.states else state_ids[0]
    layers: Dict[str, int] = {start: 0}
    queue: deque[str] = deque([start])
    while queue:
        sid = queue.popleft()
        for nid in adj[sid]:
            if nid not in layers:
                layers[nid] = layers[sid] + 1
                queue.append(nid)

    # Unreachable states → extra column
    max_l = max(layers.values()) if layers else 0
    for sid in state_ids:
        if sid not in layers:
            max_l += 1
            layers[sid] = max_l

    # Group by layer, finals last within each layer
    by_layer: Dict[int, List[str]] = {}
    for sid, layer in layers.items():
        by_layer.setdefault(layer, []).append(sid)
    for layer in by_layer:
        by_layer[layer].sort(key=lambda s: (rule.states[s].is_terminal, s))

    # Assign positions centred vertically, but prefer stored positions
    positions: Dict[str, QPointF] = {}
    for layer_idx, sids in by_layer.items():
        total_h = len(sids) * NODE_H + (len(sids) - 1) * V_GAP
        top_y = -(total_h - NODE_H) / 2
        for rank, sid in enumerate(sids):
            if sid in rule.node_positions:
                xy = rule.node_positions[sid]
                positions[sid] = QPointF(xy[0], xy[1])
            else:
                x = layer_idx * (NODE_W + H_GAP) + NODE_W / 2
                y = top_y + rank * (NODE_H + V_GAP)
                positions[sid] = QPointF(x, y)

    return positions


# ── StateNode ─────────────────────────────────────────────────────────────────

class StateNode(QGraphicsItem):
    """Rounded-rect node representing one workflow state."""

    def __init__(
        self,
        state_id: str,
        state_def: WorkflowState,
        mode: str,
        is_current: bool = False,
        is_visited: bool = False,
        on_moved: Optional[Callable[[str, QPointF], None]] = None,
        display_label: Optional[str] = None,
        click_callback: Optional[Callable[[], None]] = None,
        is_pending: bool = False,
        is_target: bool = False,
    ) -> None:
        super().__init__()
        self.state_id = state_id
        self.state_def = state_def
        self.mode = mode
        self.is_current = is_current
        self.is_visited = is_visited
        self.is_pending = is_pending
        self.is_target = is_target
        self._on_moved = on_moved
        self._click_cb = click_callback
        self._hovered = False
        self._connected_edges: List["TransitionEdge"] = []

        # Use the pre-resolved locale label if provided, otherwise fall back
        self.display_label = (
            display_label if display_label is not None
            else (state_def.label if state_def.label else state_id)
        )

        self.setAcceptHoverEvents(True)
        if mode == "edit":
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            # Required so itemChange() receives ItemPositionChange (pre-move)
            # and ItemPositionHasChanged (post-move) — both needed for edge repaint.
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        elif click_callback:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

    # ── QGraphicsItem interface ───────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        # All painting is relative to the node visual rect (base).
        # Largest outward extent: hover ring at base.adjusted(-7,-7,7,7) with
        # 2px pen → 7 + 1 = 8px beyond base. +2px safety → 10px margin each side.
        # Margin is permanent (not hover-conditional) to avoid geometry changes.
        return QRectF(-NODE_W / 2, -NODE_H / 2, NODE_W, NODE_H).adjusted(-10, -10, 10, 10)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        # IMPORTANT: use the node visual rect as the drawing base — NOT boundingRect().
        # boundingRect() is larger (adds clip margin); using it as base would push
        # the selection ring outside boundingRect() on every call, causing drag artifacts.
        r = QRectF(-NODE_W / 2, -NODE_H / 2, NODE_W, NODE_H)

        # Background — pending (orange selection) takes highest priority,
        # including when the current state IS the pending state (initial / deselected).
        if self.is_pending:
            bg = C_BG_PEND   # teal-light — active selection (incl. current state)
        elif self.is_target:
            bg = C_BG_TGT    # light cornflower-blue — available/clickable target
        elif self.is_current:
            bg = C_BG_CUR
        elif self.is_visited:
            bg = C_BG_VIS
        else:
            bg = C_BG_DEF

        # Border colour — is_target (clickable) beats state_def.final so that
        # available final states show a blue "clickable" border, not the green
        # UML final-state decoration (which confused all states into looking green).
        if self.is_pending:
            border_c = C_PENDING   # teal — active selection
            bw = 2.5
        elif self.is_current:
            border_c = C_CURRENT
            bw = 2.5
        elif self.is_target:
            border_c = C_AVAIL     # blue border — signals clickability
            bw = 1.5
        elif self.state_def.is_terminal:
            border_c = C_FINAL_NG if self._is_error_final() else C_FINAL_OK
            bw = 2.0
        elif self.is_visited:
            border_c = C_VISITED
            bw = 1.5
        else:
            border_c = C_DEFAULT
            bw = 1.5

        if self._hovered and (self.mode == "edit" or self._click_cb):
            bw += 0.5

        # Selection highlight (edit mode)
        if self.isSelected() and self.mode == "edit":
            painter.setPen(QPen(QColor("#2196f3"), 2.0, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(r.adjusted(-4, -4, 4, 4), BORDER_R + 4, BORDER_R + 4)

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border_c, bw))
        painter.drawRoundedRect(r, BORDER_R, BORDER_R)

        # Hover ring: dashed outer border to give clear click-affordance feedback
        if self._hovered and self._click_cb:
            hover_pen = QPen(border_c, 1.5, Qt.PenStyle.DashLine)
            hover_pen.setDashPattern([4.0, 3.0])
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(hover_pen)
            painter.drawRoundedRect(r.adjusted(-7, -7, 7, 7), BORDER_R + 6, BORDER_R + 6)

        # Double border: terminal states (UML convention) AND active pending selection
        if self.state_def.is_terminal or self.is_pending:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(border_c, 1.0))
            painter.drawRoundedRect(r.adjusted(4, 4, -4, -4), BORDER_R - 3, BORDER_R - 3)

        # Label — bold only on the current workflow state
        font = QFont()
        font.setPointSize(9)
        font.setBold(self.is_current)
        painter.setFont(font)
        painter.setPen(QPen(border_c))
        painter.drawText(r.adjusted(6, 3, -6, -3),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                         self.display_label)

        # Initial-state indicator: small right-pointing triangle on left edge (UML entry arrow)
        if self.state_def.initial:
            tx = r.left() + 9
            ty = r.center().y()
            tri = QPolygonF([
                QPointF(tx - 5, ty - 5),
                QPointF(tx + 5, ty),
                QPointF(tx - 5, ty + 5),
            ])
            painter.setBrush(QBrush(QColor("#1565c0")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(tri)

        # Current-state dot (top-right corner, blue)
        if self.is_current:
            painter.setBrush(QBrush(C_CURRENT))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(r.right() - 10, r.top() + 10), 4, 4)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._click_cb:
            event.accept()
            # _click_cb may be a plain callable (no args) or have a ._node_cb attr
            node_cb = getattr(self._click_cb, "_node_cb", None)
            if node_cb is not None:
                node_cb()
            else:
                self._click_cb()
            return  # scene may be rebuilt inside callback — do NOT touch self after this
        super().mousePressEvent(event)

    # ── Hover & drag ─────────────────────────────────────────────────────────

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        tip = self.toolTip()
        if tip:
            from PyQt6.QtWidgets import QToolTip  # noqa: PLC0415
            QToolTip.showText(event.screenPos(), tip)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        from PyQt6.QtWidgets import QToolTip  # noqa: PLC0415
        QToolTip.hideText()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # Pre-move: tell Qt the edges' old bounding rects are dirty BEFORE
            # the node position (and therefore their path/boundingRect) changes.
            for edge in self._connected_edges:
                edge.prepareGeometryChange()
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Post-move: trigger a visual refresh and persist the new position.
            for edge in self._connected_edges:
                edge.update()
            if self._on_moved:
                self._on_moved(self.state_id, value)
        return super().itemChange(change, value)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_error_final(self) -> bool:
        if self.state_def.state_type == StateType.END_NOK:
            return True
        if self.state_def.state_type in (StateType.END_OK, StateType.END_NEUTRAL):
            return False
        # Fallback heuristic for legacy states without state_type
        return any(k in self.state_id.upper() for k in ("REJECT", "ERROR", "FAIL", "SPAM", "CANCEL"))


# ── AnchorDot ─────────────────────────────────────────────────────────────────

class AnchorDot(QGraphicsItem):
    """Snap-target shown on a node while an EndpointHandle is dragged."""
    R = 7.0

    def __init__(self, node: "StateNode", anchor: str) -> None:
        super().__init__()
        self.node = node
        self.anchor = anchor
        self.active = False
        self.setZValue(10)

    def boundingRect(self) -> QRectF:
        r = self.R + 2
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        col = QColor("#cddc39") if self.active else QColor("#8bc34a")
        painter.setBrush(QBrush(col))
        painter.setPen(QPen(QColor("#33691e"), 1.5))
        painter.drawEllipse(QRectF(-self.R, -self.R, self.R * 2, self.R * 2))


# ── TransitionEdge ────────────────────────────────────────────────────────────

class TransitionEdge(QGraphicsItem):
    """Directed arrow representing a workflow transition."""

    def __init__(
        self,
        transition: WorkflowTransition,
        source_node: StateNode,
        target_node: StateNode,
        is_available: bool,
        is_back_edge: bool,
        click_callback: Optional[Callable[["TransitionEdge"], None]] = None,
        edge_index: int = 0,
        total_edges: int = 1,
        src_anchor: str = "right",
        tgt_anchor: str = "left",
    ) -> None:
        super().__init__()
        self.transition = transition
        self.src_anchor = src_anchor
        self.tgt_anchor = tgt_anchor
        self.src = source_node
        self.tgt = target_node
        self.is_available = is_available
        self.is_back_edge = is_back_edge
        self._click_cb = click_callback
        self.edge_index = edge_index
        self.total_edges = total_edges
        self._hovered = False
        self.is_pending: bool = False
        self.ctrl1_offset: QPointF = QPointF(0.0, 0.0)  # source-side ctrl point displacement
        self.ctrl2_offset: QPointF = QPointF(0.0, 0.0)  # target-side ctrl point displacement
        self.src_spread: float = 0.0  # perpendicular fanout offset at source anchor
        self.tgt_spread: float = 0.0  # perpendicular fanout offset at target anchor

        display = (transition.label or transition.action).replace("_", " ").capitalize()
        self._label = f"⚡ {display}" if transition.auto else display

        self.setZValue(-1)
        self.setAcceptHoverEvents(True)
        if click_callback and not transition.auto:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    # ── Path computation ──────────────────────────────────────────────────────

    def _y_offset(self) -> float:
        """Perpendicular offset for parallel edges between the same pair."""
        return (self.edge_index - (self.total_edges - 1) / 2.0) * MULTI_OFF

    def _ctrl_points(self) -> Optional[Tuple[QPointF, QPointF, QPointF, QPointF]]:
        """Return (src_pt, ctrl1, ctrl2, tgt_pt) for the Bezier, or None for self-loops."""
        if self.src is self.tgt:
            return None
        sp = self.src.pos()
        tp = self.tgt.pos()
        off = self._y_offset()

        src_pt = _anchor_point(sp, self.src_anchor)
        tgt_pt = _anchor_point(tp, self.tgt_anchor)

        if off:
            dx = tgt_pt.x() - src_pt.x()
            dy = tgt_pt.y() - src_pt.y()
            length = math.sqrt(dx * dx + dy * dy) or 1.0
            px, py = -dy / length * off, dx / length * off
            src_pt = QPointF(src_pt.x() + px, src_pt.y() + py)
            tgt_pt = QPointF(tgt_pt.x() + px, tgt_pt.y() + py)

        src_tang = _anchor_tangent(self.src_anchor)
        tgt_tang = _anchor_tangent(self.tgt_anchor)

        # Fanout spread: shift departure/arrival points perpendicular to their
        # anchor tangent when multiple edges share the same anchor on a node.
        if self.src_spread:
            src_pt = QPointF(src_pt.x() - src_tang.y() * self.src_spread,
                             src_pt.y() + src_tang.x() * self.src_spread)
        if self.tgt_spread:
            tgt_pt = QPointF(tgt_pt.x() - tgt_tang.y() * self.tgt_spread,
                             tgt_pt.y() + tgt_tang.x() * self.tgt_spread)

        dx = tgt_pt.x() - src_pt.x()
        dy = tgt_pt.y() - src_pt.y()
        dist = max(math.sqrt(dx * dx + dy * dy), 1.0)
        ctrl_d = max(CTRL_DIST_MIN, dist * 0.42)

        ctrl1 = QPointF(
            src_pt.x() + src_tang.x() * ctrl_d + self.ctrl1_offset.x(),
            src_pt.y() + src_tang.y() * ctrl_d + self.ctrl1_offset.y(),
        )
        ctrl2 = QPointF(
            tgt_pt.x() + tgt_tang.x() * ctrl_d + self.ctrl2_offset.x(),
            tgt_pt.y() + tgt_tang.y() * ctrl_d + self.ctrl2_offset.y(),
        )
        return src_pt, ctrl1, ctrl2, tgt_pt

    def _path_and_label(self) -> Tuple[QPainterPath, QPointF]:
        sp = self.src.pos()

        # Self-loop — fixed shape, anchors not used for path
        if self.src is self.tgt:
            rx = sp.x() + NODE_W / 2
            ry = sp.y()
            path = QPainterPath(QPointF(rx, ry - 8))
            path.cubicTo(
                QPointF(rx + 55, ry - 50),
                QPointF(rx + 55, ry + 20),
                QPointF(rx, ry + 8),
            )
            return path, QPointF(rx + 50, ry - 20)

        pts = self._ctrl_points()
        assert pts is not None
        src_pt, ctrl1, ctrl2, tgt_pt = pts
        path = QPainterPath(src_pt)
        path.cubicTo(ctrl1, ctrl2, tgt_pt)

        mid = path.pointAtPercent(0.5)
        return path, QPointF(mid.x(), mid.y() - 13)

    # ── QGraphicsItem interface ───────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        path, label_pos = self._path_and_label()
        r = path.boundingRect().adjusted(-20, -20, 20, 20)
        # Label background rect is drawn up to ~104 px either side of label_pos and
        # ~12 px above/below it.  Omitting it from boundingRect() caused ghost labels
        # when connected nodes were moved (old area never invalidated by Qt).
        label_r = QRectF(label_pos.x() - 104, label_pos.y() - 12, 208, 24)
        return r.united(label_r)

    def shape(self) -> QPainterPath:
        path, _ = self._path_and_label()
        stroker = QPainterPathStroker()
        stroker.setWidth(14)
        return stroker.createStroke(path)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        path, label_pos = self._path_and_label()

        # Pen style
        if self.transition.auto:
            col, style, pw = C_AUTO, Qt.PenStyle.DotLine, 1.8
        elif self.is_available:
            col = C_CURRENT if self._hovered else C_AVAIL
            style, pw = Qt.PenStyle.SolidLine, 2.0 if not self._hovered else 2.5
        else:
            col, style, pw = C_BLOCKED, Qt.PenStyle.DashLine, 1.2

        if self.is_pending:
            col, style, pw = C_PENDING, Qt.PenStyle.SolidLine, 2.5

        # Selection highlight
        if self.isSelected():
            painter.setPen(QPen(QColor("#2196f3"), pw + 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        painter.setPen(QPen(col, pw, style))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Arrowhead — always perpendicular to node surface at anchor point
        end = path.pointAtPercent(1.0)
        if self.src is not self.tgt:
            tgt_t = _anchor_tangent(self.tgt_anchor)
            # tgt_t points outward from the node; negate for incoming direction
            ang = math.atan2(-tgt_t.y(), -tgt_t.x())
        else:
            pre = path.pointAtPercent(0.97)
            ang = math.atan2(end.y() - pre.y(), end.x() - pre.x())
        p1 = QPointF(end.x() - ARROW * math.cos(ang - math.pi / 6),
                     end.y() - ARROW * math.sin(ang - math.pi / 6))
        p2 = QPointF(end.x() - ARROW * math.cos(ang + math.pi / 6),
                     end.y() - ARROW * math.sin(ang + math.pi / 6))
        painter.setBrush(QBrush(col))
        painter.setPen(QPen(col, 1))
        painter.drawPolygon(QPolygonF([end, p1, p2]))

        # Control-point arms (edit mode: shown when selected)
        if self.isSelected() and self.src is not self.tgt:
            pts = self._ctrl_points()
            if pts:
                s, c1, c2, t = pts
                arm_pen = QPen(QColor(255, 152, 0, 140), 1.0, Qt.PenStyle.DashLine)
                painter.setPen(arm_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawLine(s, c1)
                painter.drawLine(t, c2)

        # Label with semi-transparent background
        font = QFont()
        font.setPointSize(8)
        font.setItalic(self.transition.auto)
        font.setBold(self._hovered and self.is_available)
        painter.setFont(font)
        fm = painter.fontMetrics()
        lr = fm.boundingRect(self._label)
        bg_r = QRectF(
            label_pos.x() - lr.width() / 2 - 4,
            label_pos.y() - lr.height() / 2 - 2,
            lr.width() + 8,
            lr.height() + 4,
        )
        painter.setBrush(QBrush(QColor(255, 255, 255, 210)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bg_r, 3, 3)

        painter.setPen(QPen(col))
        painter.drawText(bg_r, Qt.AlignmentFlag.AlignCenter, self._label)

    # ── Interaction ───────────────────────────────────────────────────────────

    def hoverEnterEvent(self, event) -> None:
        if self.is_available:
            self._hovered = True
            self.update()
        tip = self.toolTip()
        if tip:
            from PyQt6.QtWidgets import QToolTip  # noqa: PLC0415
            QToolTip.showText(event.screenPos(), tip)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        from PyQt6.QtWidgets import QToolTip  # noqa: PLC0415
        QToolTip.hideText()

    def mousePressEvent(self, event) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and self.is_available
                and self._click_cb
                and not self.transition.auto):
            event.accept()
            self._click_cb(self)
            return  # scene may be rebuilt inside callback — do NOT touch self after this
        super().mousePressEvent(event)


# ── AddTransitionDialog ───────────────────────────────────────────────────────

class AddTransitionDialog(QDialog):
    """Small dialog for adding a transition in edit mode."""

    def __init__(self, states: Dict[str, "WorkflowState"], parent=None) -> None:
        """
        states: mapping of state_id → WorkflowState (to show labels alongside IDs).
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("Add Transition"))
        self.setMinimumWidth(360)

        # Show only the label — IDs are internal and not shown to the user
        self._state_ids: List[str] = list(states.keys())
        display_items: List[Tuple[str, str]] = []
        for sid, sdef in states.items():
            display_items.append((sdef.label if sdef.label else sid, sid))

        layout = QFormLayout(self)
        layout.setSpacing(10)

        self._src = QComboBox()
        for display, sid in display_items:
            self._src.addItem(display, sid)
        layout.addRow(self.tr("From State:"), self._src)

        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText(self.tr("e.g. Verify, Approve, Reject"))
        layout.addRow(self.tr("Label:"), self._label_edit)

        self._tgt = QComboBox()
        for display, sid in display_items:
            self._tgt.addItem(display, sid)
        layout.addRow(self.tr("To State:"), self._tgt)

        self._auto = QCheckBox(self.tr("Auto-transition (no user interaction)"))
        layout.addRow("", self._auto)

        self._req = QLineEdit()
        self._req.setPlaceholderText(self.tr("iban, total_gross, …  (comma-separated)"))
        layout.addRow(self.tr("Required Fields:"), self._req)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_values(self) -> Tuple[str, str, str, bool, List[str]]:
        """Return (src_id, label, tgt_id, auto, required_fields).

        The caller is responsible for generating a stable action_id via
        make_action_id() and constructing the WorkflowTransition.
        """
        req = [f.strip() for f in self._req.text().split(",") if f.strip()]
        return (
            self._src.currentData(),
            self._label_edit.text().strip(),
            self._tgt.currentData(),
            self._auto.isChecked(),
            req,
        )


# ── EndpointHandle ────────────────────────────────────────────────────────────

class EndpointHandle(QGraphicsItem):
    """Draggable handle at a TransitionEdge anchor point (edit mode only).

    Drag to another anchor on the same node to reroute the edge.
    If the target anchor is already occupied by another edge on the same node,
    the two edges swap their anchors (untangle mode).
    """
    R = 6.0

    def __init__(
        self,
        edge: "TransitionEdge",
        is_source: bool,
        on_committed: Callable[["TransitionEdge", bool, str], None],
    ) -> None:
        super().__init__()
        self._edge = edge
        self._is_source = is_source
        self._on_committed = on_committed
        self._dragging = False
        self._drag_pos = QPointF()
        self._orig_src: str = ""
        self._orig_tgt: str = ""
        self._overlay: List[AnchorDot] = []
        self.setZValue(9)
        self.setAcceptHoverEvents(True)
        self._snap_to_edge()

    # ── Geometry ──────────────────────────────────────────────────────────────

    def _node(self) -> "StateNode":
        return self._edge.src if self._is_source else self._edge.tgt

    def _snap_to_edge(self) -> None:
        anchor = self._edge.src_anchor if self._is_source else self._edge.tgt_anchor
        self.setPos(_anchor_point(self._node().pos(), anchor))

    def boundingRect(self) -> QRectF:
        r = self.R + 3
        return QRectF(-r, -r, r * 2, r * 2)

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addEllipse(QRectF(-(self.R + 5), -(self.R + 5), (self.R + 5) * 2, (self.R + 5) * 2))
        return p

    def paint(self, painter: QPainter, option, widget=None) -> None:
        col = QColor("#ef5350") if self._dragging else QColor("#1565c0")
        painter.setBrush(QBrush(col))
        painter.setPen(QPen(QColor("white"), 1.5))
        painter.drawEllipse(QRectF(-self.R, -self.R, self.R * 2, self.R * 2))

    # ── Anchor overlay helpers ─────────────────────────────────────────────────

    def _show_overlay(self) -> None:
        sc = self.scene()
        if sc is None:
            return
        for name in ANCHOR_NAMES:
            dot = AnchorDot(self._node(), name)
            dot.setPos(_anchor_point(self._node().pos(), name))
            sc.addItem(dot)
            self._overlay.append(dot)

    def _hide_overlay(self) -> None:
        sc = self.scene()
        for dot in self._overlay:
            if sc:
                sc.removeItem(dot)
        self._overlay.clear()

    def _nearest(self, scene_pos: QPointF) -> Tuple[str, float]:
        best_name, best_dist = ANCHOR_NAMES[0], float("inf")
        node = self._node()
        for name in ANCHOR_NAMES:
            ap = _anchor_point(node.pos(), name)
            d = scene_pos - ap
            dist = math.sqrt(d.x() ** 2 + d.y() ** 2)
            if dist < best_dist:
                best_dist = dist
                best_name = name
        return best_name, best_dist

    # ── Mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.scenePos()
            self._orig_src = self._edge.src_anchor
            self._orig_tgt = self._edge.tgt_anchor
            self._show_overlay()
            self.update()
        event.accept()  # consume — do not propagate to scene selection

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        self._drag_pos = event.scenePos()
        self.setPos(self._drag_pos)

        best_name, _ = self._nearest(self._drag_pos)
        for dot in self._overlay:
            dot.active = dot.anchor == best_name
            dot.update()

        # Live preview: temporarily reroute edge through nearest anchor
        if self._is_source:
            self._edge.src_anchor = best_name
        else:
            self._edge.tgt_anchor = best_name
        self._edge.prepareGeometryChange()
        self._edge.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._hide_overlay()

        best_name, best_dist = self._nearest(self._drag_pos)
        if best_dist <= ANCHOR_SNAP:
            self._on_committed(self._edge, self._is_source, best_name)
        else:
            # Revert preview
            self._edge.src_anchor = self._orig_src
            self._edge.tgt_anchor = self._orig_tgt
            self._edge.prepareGeometryChange()
            self._edge.update()

        self._snap_to_edge()
        self.update()
        event.accept()

    def hoverEnterEvent(self, event) -> None:
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))

    def hoverLeaveEvent(self, event) -> None:
        self.unsetCursor()


# ── CtrlHandle ────────────────────────────────────────────────────────────────

class CtrlHandle(QGraphicsItem):
    """Draggable diamond at a Bezier control point of a TransitionEdge (edit mode).

    Two instances are created per selected edge — one for ctrl1 (source side,
    orange) and one for ctrl2 (target side, teal).  Drag to reshape the curve;
    double-click to reset both control-point offsets to zero.
    """

    R = 6.0

    # colours per side
    _IDLE_COL  = {"ctrl1": QColor("#ff9800"), "ctrl2": QColor("#26a69a")}
    _DRAG_COL  = {"ctrl1": QColor("#e65100"), "ctrl2": QColor("#00695c")}
    _ZERO_COL  = {"ctrl1": QColor("#ffe082"), "ctrl2": QColor("#b2dfdb")}

    def __init__(
        self,
        edge: "TransitionEdge",
        which: str,
        on_committed: "Callable[[TransitionEdge], None]",
    ) -> None:
        assert which in ("ctrl1", "ctrl2")
        super().__init__()
        self._edge = edge
        self._which = which
        self._on_committed = on_committed
        self._dragging = False
        self._drag_start_scene = QPointF()
        self._drag_start_offset = QPointF()
        self.setZValue(9)
        self.setAcceptHoverEvents(True)
        self._snap_to_edge()

    # ── Geometry ──────────────────────────────────────────────────────────────

    def _current_offset(self) -> QPointF:
        return (self._edge.ctrl1_offset if self._which == "ctrl1"
                else self._edge.ctrl2_offset)

    def _set_offset(self, v: QPointF) -> None:
        if self._which == "ctrl1":
            self._edge.ctrl1_offset = v
        else:
            self._edge.ctrl2_offset = v

    def _snap_to_edge(self) -> None:
        """Protocol with EndpointHandle — reposition after edge geometry changes."""
        pts = self._edge._ctrl_points()
        if pts is None:
            return
        _, ctrl1, ctrl2, _ = pts
        self.setPos(ctrl1 if self._which == "ctrl1" else ctrl2)

    def boundingRect(self) -> QRectF:
        r = self.R + 4
        return QRectF(-r, -r, r * 2, r * 2)

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addRect(self.boundingRect())
        return p

    # ── Painting ──────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None) -> None:
        off = self._current_offset()
        has_offset = off.x() != 0.0 or off.y() != 0.0
        if self._dragging:
            col = self._DRAG_COL[self._which]
        elif has_offset:
            col = self._IDLE_COL[self._which]
        else:
            col = self._ZERO_COL[self._which]
        painter.setBrush(QBrush(col))
        painter.setPen(QPen(QColor("white"), 1.5))
        painter.drawPolygon(QPolygonF([
            QPointF(0,       -self.R),
            QPointF(self.R,  0),
            QPointF(0,       self.R),
            QPointF(-self.R, 0),
        ]))

    # ── Mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_scene = event.scenePos()
            self._drag_start_offset = QPointF(self._current_offset())
            self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        delta = event.scenePos() - self._drag_start_scene
        self._set_offset(QPointF(
            self._drag_start_offset.x() + delta.x(),
            self._drag_start_offset.y() + delta.y(),
        ))
        self._edge.prepareGeometryChange()
        self._edge.update()
        self._snap_to_edge()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._on_committed(self._edge)
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        """Reset both control-point offsets to zero (restore auto-computed path)."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._edge.ctrl1_offset = QPointF(0.0, 0.0)
            self._edge.ctrl2_offset = QPointF(0.0, 0.0)
            self._edge.prepareGeometryChange()
            self._edge.update()
            self._snap_to_edge()
            self._on_committed(self._edge)
        event.accept()

    def hoverEnterEvent(self, event) -> None:
        side = "source" if self._which == "ctrl1" else "target"
        self.setToolTip(f"Drag to reshape curve ({side} side) · Double-click to reset")
        self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))

    def hoverLeaveEvent(self, event) -> None:
        self.unsetCursor()


# ── WorkflowGraphWidget ───────────────────────────────────────────────────────

class WorkflowGraphWidget(QWidget):
    """
    Visual state-machine widget for a single WorkflowRule.

    mode="run"  — read-only, clickable available transitions.
    mode="edit" — drag nodes, add/remove states/transitions, inline detail panel.
    """

    transition_triggered = pyqtSignal(str, str, str, bool)  # rule_id, action, target, is_auto
    rule_changed = pyqtSignal()  # edit mode: underlying rule was modified
    item_selected = pyqtSignal(object)   # emitted in non-inline mode on selection change

    def __init__(self, mode: str = "run", parent=None, inline_detail: bool = True) -> None:
        super().__init__(parent)
        assert mode in ("run", "edit")
        self.mode = mode
        self._rule: Optional[WorkflowRule] = None
        self._wf_info: Optional[Any] = None
        self._doc_data: Dict[str, Any] = {}
        self._nodes: Dict[str, StateNode] = {}
        self._edges: List[TransitionEdge] = []
        self._handles: List[EndpointHandle] = []
        self.inline_detail = inline_detail
        self._user_zoomed = False
        self._pending_action: Optional[str] = None
        self._pending_target: Optional[str] = None
        self._pending_rule_id: Optional[str] = None
        self._current_step: str = ""
        self._btn_apply: Optional[Any] = None
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(120)   # ms after last resize event
        self._fit_timer.timeout.connect(self._fit_view)
        self._init_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        self._header = QFrame()
        self._header.setFixedHeight(32)
        from gui.theme import (
            CLR_SURFACE_ROW, CLR_BORDER, CLR_TEXT, CLR_TEXT_SECONDARY,
            CLR_TEXT_ON_COLOR, FONT_BASE, RADIUS_SM,
        )
        self._header.setStyleSheet(
            f"background:{CLR_SURFACE_ROW}; border-bottom:1px solid {CLR_BORDER};"
        )
        hdr = QHBoxLayout(self._header)
        hdr.setContentsMargins(10, 0, 10, 0)
        hdr.setSpacing(8)
        self._hdr_layout = hdr

        self._rule_lbl = QLabel()
        self._rule_lbl.setStyleSheet(f"font-weight:bold; color:{CLR_TEXT}; font-size:{FONT_BASE}px;")
        hdr.addWidget(self._rule_lbl)

        self._badge = QLabel()
        self._badge.setStyleSheet(
            f"font-size:{FONT_BASE}px; padding:2px 8px; border-radius:{RADIUS_SM}px;"
            f" background:{CLR_TEXT_SECONDARY}; color:{CLR_TEXT_ON_COLOR}; font-weight:bold;"
        )
        hdr.addWidget(self._badge)
        hdr.addStretch()

        if self.mode == "edit":
            self._build_edit_toolbar(hdr)

        if self.mode == "run":
            from PyQt6.QtWidgets import QToolButton as _TB  # noqa: PLC0415
            self._btn_apply = _TB()
            self._btn_apply.setText(self.tr("✓ Apply"))
            self._btn_apply.setFixedHeight(26)
            self._btn_apply.setEnabled(False)
            self._btn_apply.setStyleSheet(
                "padding:0 12px; font-weight:bold;"
            )
            self._btn_apply.clicked.connect(self._on_apply)
            hdr.addWidget(self._btn_apply)

        # Zoom buttons (both modes)
        for _txt, _slot in (("−", self._zoom_out), ("+", self._zoom_in)):
            _b = QToolButton()
            _b.setText(_txt)
            _b.setFixedSize(26, 26)
            hdr.addWidget(_b)
            _b.clicked.connect(_slot)

        # Zoom-fit button (both modes)
        btn_fit = QToolButton()
        btn_fit.setText("⊞")
        btn_fit.setToolTip(self.tr("Fit view"))
        btn_fit.setFixedSize(26, 26)
        btn_fit.clicked.connect(self._fit_view)
        hdr.addWidget(btn_fit)

        vbox.addWidget(self._header)

        # ── Graphics view ─────────────────────────────────────────────────────
        self._scene = QGraphicsScene(self)
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self._view.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.SmartViewportUpdate
        )
        self._view.setDragMode(
            QGraphicsView.DragMode.NoDrag
            if self.mode == "run"
            else QGraphicsView.DragMode.RubberBandDrag
        )
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setFrameShape(QFrame.Shape.NoFrame)
        self._view.setBackgroundBrush(QBrush(C_SCENE_BG))
        self._view.setMinimumHeight(180)
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        vbox.addWidget(self._view, 1)

        if self.mode == "edit":
            if self.inline_detail:
                self._build_detail_panel(vbox)
            self._scene.selectionChanged.connect(self._on_selection_changed)

    def _build_edit_toolbar(self, hdr: QHBoxLayout) -> None:
        self._toolbar_buttons: List[Tuple[QPushButton, str, str]] = []
        for text_key, tip_key, slot in (
            ("✚ %s",  "Add new state",                  self._cmd_add_state),
            ("✚ %s",  "Add transition between states",  self._cmd_add_transition),
            ("✕ %s",  "Delete selected item",           self._cmd_delete_selected),
        ):
            b = QPushButton()
            b.setFixedHeight(26)
            b.setStyleSheet("padding:0 8px;")
            b.clicked.connect(slot)
            hdr.addWidget(b)
            self._toolbar_buttons.append((b, text_key, tip_key))
        self._retranslate_toolbar()

    def _build_detail_panel(self, vbox: QVBoxLayout) -> None:
        self._detail = QFrame()
        self._detail.setFixedHeight(120)
        self._detail.setStyleSheet(
            "background:white; border-top:1px solid #e2e8f0;"
        )
        dl = QVBoxLayout(self._detail)
        dl.setContentsMargins(12, 6, 12, 6)

        self._detail_hint = QLabel(self.tr("Select a state or transition to edit its properties."))
        self._detail_hint.setStyleSheet("color:#94a3b8; font-style:italic;")
        dl.addWidget(self._detail_hint)

        self._detail_form = QFrame()
        self._detail_form_layout = QFormLayout(self._detail_form)
        self._detail_form_layout.setContentsMargins(0, 0, 0, 0)
        self._detail_form_layout.setSpacing(6)
        self._detail_form.hide()
        dl.addWidget(self._detail_form)

        vbox.addWidget(self._detail)

    # ── L10n ──────────────────────────────────────────────────────────────────

    def changeEvent(self, event) -> None:
        from PyQt6.QtCore import QEvent
        if event and event.type() == QEvent.Type.LanguageChange:
            self._retranslate_toolbar()
            if self.mode == "edit" and self.inline_detail:
                self._detail_hint.setText(
                    self.tr("Select a state or transition to edit its properties.")
                )
        super().changeEvent(event)

    def _retranslate_toolbar(self) -> None:
        if not hasattr(self, "_toolbar_buttons"):
            return
        labels = [
            self.tr("State"),
            self.tr("Transition"),
            self.tr("Delete"),
        ]
        tips = [
            self.tr("Add new state"),
            self.tr("Add transition between states"),
            self.tr("Delete selected item"),
        ]
        for (btn, fmt, _), label, tip in zip(self._toolbar_buttons, labels, tips):
            btn.setText(fmt % label)
            btn.setToolTip(tip)

    # ── Public API ────────────────────────────────────────────────────────────

    def load(
        self,
        rule: Optional[WorkflowRule],
        workflow_info: Optional[Any] = None,
        doc_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Populate the widget with a rule. workflow_info/doc_data only used in run mode."""
        self._rule = rule
        self._wf_info = workflow_info
        self._doc_data = doc_data or {}
        self._rebuild()

    def get_rule(self) -> Optional[WorkflowRule]:
        """Returns the (possibly edited) current rule. Used in edit mode."""
        return self._rule

    # ── Scene construction ────────────────────────────────────────────────────

    @staticmethod
    def _resolve_step(rule: WorkflowRule, step: str) -> str:
        """Return *step* if it is a valid state ID in *rule*, otherwise the
        rule's initial state.  Handles the default WorkflowInfo.current_step
        value of ``"NEW"`` for rules whose initial state has a different key.
        """
        if step in rule.states:
            return step
        from core.workflow import get_initial_state  # noqa: PLC0415
        return get_initial_state(rule) or step

    def _rebuild(self) -> None:
        self._handles.clear()
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()

        if not self._rule:
            # Show neutral placeholder when no rule is loaded
            font = QFont()
            font.setPointSize(11)
            font.setItalic(True)
            from PyQt6.QtWidgets import QGraphicsTextItem  # noqa: PLC0415
            item = QGraphicsTextItem()
            item.setFont(font)
            item.setDefaultTextColor(QColor("#9e9e9e"))
            item.setPlainText(self.tr("Select a workflow rule to view or edit it."))
            self._scene.addItem(item)
            self._scene.setSceneRect(item.boundingRect().adjusted(-40, -40, 40, 40))
            self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            return
        self._nodes.clear()
        self._edges.clear()

        rule = self._rule
        wi = self._wf_info

        if self.mode == "run":
            self._clear_pending()
            self._rebuild_run_full(rule, wi)
        else:
            self._rebuild_edit_full(rule)

        self._rule_lbl.setText(rule.get_display_name())
        self._badge.setVisible(False)

        QTimer.singleShot(50, self._fit_view)

    # ── Scene construction helpers ────────────────────────────────────────────

    def _rebuild_run_full(self, rule: WorkflowRule, wi: Optional[Any]) -> None:
        """Run mode: full workflow graph with non-relevant items dimmed.

        Shows the complete graph (identical layout to edit mode) but dims all
        states and transitions that are not reachable from the current step.
        Relevant available transitions are clickable and set a pending selection;
        the Apply button commits the transition.
        """
        current_step = self._resolve_step(rule, wi.current_step if wi else "")
        self._current_step = current_step
        visited = self._extract_visited(wi)
        engine = WorkflowEngine(rule)
        positions = _compute_layout(rule)

        # ── Pre-compute relevance and availability for edges and nodes ──────────
        cur_sdef = rule.states.get(current_step)
        relevant_transitions = {t.action for t in cur_sdef.transitions} if cur_sdef else set()
        relevant_targets = {t.target for t in cur_sdef.transitions} if cur_sdef else set()

        def _missing_tip(trans: WorkflowTransition) -> str:
            parts: List[str] = []
            missing_fields = [
                f for f in trans.required_fields
                if f not in self._doc_data or self._doc_data.get(f) is None
            ]
            if missing_fields:
                parts.append(self.tr("Missing fields: %s") % ", ".join(missing_fields))
            unmet_conds = [
                f"{c.field} {c.op} {c.value}"
                for c in trans.conditions
                if self._doc_data.get(c.field) is None
                or not engine.evaluate_transition(
                    WorkflowTransition(
                        action=trans.action, target=trans.target,
                        conditions=[c],
                    ),
                    self._doc_data,
                )
            ]
            if unmet_conds:
                parts.append(self.tr("Unmet conditions: %s") % ", ".join(unmet_conds))
            return "\n".join(parts)

        # Per-node display properties — computed before any addItem call so that
        # the first paint already shows the correct opacity (no two-phase flicker).
        _node_opacity: Dict[str, float] = {}
        _node_is_target: Dict[str, bool] = {}
        _node_cb: Dict[str, Optional[Callable]] = {}
        _node_tip: Dict[str, str] = {}

        for sid in rule.states:
            if sid == current_step:
                _node_opacity[sid] = 1.0
                _node_cb[sid] = self._clear_pending
            elif sid in relevant_targets:
                avail_trans = next(
                    (t for t in (cur_sdef.transitions if cur_sdef else [])
                     if t.target == sid and not t.auto
                     and engine.can_transition(current_step, t.action, self._doc_data)),
                    None,
                )
                if avail_trans:
                    _node_opacity[sid] = 1.0
                    _node_is_target[sid] = True
                    _node_cb[sid] = self._make_set_pending_cb(
                        rule.id, avail_trans.action, avail_trans.target
                    )
                else:
                    _node_opacity[sid] = 0.5
                    tips = [
                        _missing_tip(t)
                        for t in (cur_sdef.transitions if cur_sdef else [])
                        if t.target == sid and not t.auto and _missing_tip(t)
                    ]
                    if tips:
                        _node_tip[sid] = "\n".join(tips)
            else:
                _node_opacity[sid] = 0.1

        # ── Build all state nodes with correct opacity from the first paint ────
        for sid, sdef in rule.states.items():
            node = StateNode(
                sid, sdef, "run",
                is_current=(sid == current_step),
                is_visited=(sid in visited),
                is_target=_node_is_target.get(sid, False),
                display_label=rule.get_state_label(sid),
                click_callback=_node_cb.get(sid),
            )
            node.setPos(positions.get(sid, QPointF(0, 0)))
            opacity = _node_opacity.get(sid, 0.1)
            if opacity < 1.0:
                node.setOpacity(opacity)
            if _node_cb.get(sid):
                node.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            if _node_tip.get(sid):
                node.setToolTip(_node_tip[sid])
            self._scene.addItem(node)
            self._nodes[sid] = node

        # ── Build all transition edges (same anchor/bend logic as edit mode) ──
        pair_count: Dict[Tuple[str, str], int] = {}
        for sid, sdef in rule.states.items():
            for t in sdef.transitions:
                key = (sid, t.target)
                pair_count[key] = pair_count.get(key, 0) + 1

        pair_seen: Dict[Tuple[str, str], int] = {}
        for sid, sdef in rule.states.items():
            src_node = self._nodes.get(sid)
            if not src_node:
                continue
            for trans in sdef.transitions:
                tgt_node = self._nodes.get(trans.target)
                if not tgt_node:
                    continue

                src_x = positions.get(sid, QPointF()).x()
                tgt_x = positions.get(trans.target, QPointF()).x()
                is_back = tgt_x <= src_x and sid != trans.target
                is_self = sid == trans.target

                ak = f"{sid}:{trans.action}"
                stored = rule.transition_anchors.get(ak)
                if stored and len(stored) == 2:
                    src_a, tgt_a = stored[0], stored[1]
                elif is_self:
                    src_a, tgt_a = "right", "right"
                elif is_back:
                    src_a, tgt_a = "bottom", "bottom"
                else:
                    src_a, tgt_a = "right", "left"

                key = (sid, trans.target)
                idx = pair_seen.get(key, 0)
                pair_seen[key] = idx + 1

                is_relevant = (sid == current_step and trans.action in relevant_transitions)
                if is_relevant and not trans.auto:
                    is_avail = engine.can_transition(current_step, trans.action, self._doc_data)
                else:
                    is_avail = False

                edge = TransitionEdge(
                    trans, src_node, tgt_node,
                    is_available=is_avail,
                    is_back_edge=is_back,
                    click_callback=(
                        self._make_set_pending_cb(rule.id, trans.action, trans.target)
                        if is_relevant and is_avail and not trans.auto
                        else None
                    ),
                    edge_index=idx,
                    total_edges=pair_count[key],
                    src_anchor=src_a,
                    tgt_anchor=tgt_a,
                )
                bd = rule.transition_bends.get(ak)
                if bd and len(bd) == 4:
                    edge.ctrl1_offset = QPointF(bd[0], bd[1])
                    edge.ctrl2_offset = QPointF(bd[2], bd[3])
                elif bd and len(bd) == 2:
                    bf = 4.0 / 3.0
                    edge.ctrl1_offset = QPointF(bd[0] * bf, bd[1] * bf)
                    edge.ctrl2_offset = QPointF(bd[0] * bf, bd[1] * bf)

                tip = _missing_tip(trans) if is_relevant and not is_avail else ""
                if tip:
                    edge.setToolTip(tip)

                if not is_relevant:
                    edge.setOpacity(0.1)

                self._scene.addItem(edge)
                self._edges.append(edge)

        # Build connected-edge lists for ALL nodes (source AND target) after all
        # edges are added.  Doing this inside the loop only updated src_node, so
        # pure-target nodes (e.g. final states) never got any entries and their
        # arrows were not redrawn when those nodes were moved.
        for _node in self._nodes.values():
            _node._connected_edges = [
                e for e in self._edges if e.src is _node or e.tgt is _node
            ]

        # ── Fanout spread (same as before) ────────────────────────────────────
        _FANOUT = 12.0
        from collections import defaultdict as _dd  # noqa: PLC0415
        src_groups: Dict[Tuple[str, str], List[TransitionEdge]] = _dd(list)
        for _e in self._edges:
            src_groups[(_e.src.state_id, _e.src_anchor)].append(_e)
        for _group in src_groups.values():
            if len(_group) <= 1:
                continue
            _tgts = [_e.tgt.state_id for _e in _group]
            if len(set(_tgts)) < len(_tgts):
                continue
            _group.sort(key=lambda _e: _e.tgt.pos().y())
            for _i, _e in enumerate(_group):
                _e.src_spread = (_i - (len(_group) - 1) / 2.0) * _FANOUT

        # Current state starts as the active selection (teal).
        # Clicking an available target shifts selection to that target;
        # clicking the current-state node again clears back to current-state selected.
        cur_node = self._nodes.get(current_step)
        if cur_node:
            cur_node.is_pending = True
            cur_node.update()

    def _make_set_pending_cb(self, rule_id: str, action: str, target: str) -> Callable:
        """Return a callback that sets (rule_id, action, target) as the pending transition."""
        def _edge_cb(edge: TransitionEdge) -> None:  # noqa: ARG001
            self._set_pending(rule_id, action, target)
        # Also usable as node callback (no-arg)
        _edge_cb._node_cb = lambda: self._set_pending(rule_id, action, target)  # type: ignore[attr-defined]
        return _edge_cb

    def _set_pending(self, rule_id: str, action: str, target: str) -> None:
        """Visually mark (action → target) as the pending transition and enable Apply."""
        # Clear previous pending visual
        for _e in self._edges:
            if _e.is_pending:
                _e.is_pending = False
                _e.update()
        for _n in self._nodes.values():
            if _n.is_pending:
                _n.is_pending = False
                _n.update()

        self._pending_action = action
        self._pending_target = target
        self._pending_rule_id = rule_id

        # Mark the relevant edge(s) and target node
        for _e in self._edges:
            if _e.src.state_id != target and _e.transition.action == action:
                _e.is_pending = True
                _e.update()
        tgt_node = self._nodes.get(target)
        if tgt_node:
            tgt_node.is_pending = True
            tgt_node.update()

        if self._btn_apply:
            from gui.theme import CLR_PRIMARY  # noqa: PLC0415
            self._btn_apply.setEnabled(True)
            self._btn_apply.setStyleSheet(
                f"padding:0 12px; font-weight:bold;"
                f" background:{CLR_PRIMARY}; color:white; border-radius:4px;"
            )

    def _clear_pending(self) -> None:
        """Clear any pending transition selection and re-select the current state."""
        self._pending_action = None
        self._pending_target = None
        self._pending_rule_id = None
        for _e in self._edges:
            if _e.is_pending:
                _e.is_pending = False
                _e.update()
        for _n in self._nodes.values():
            if _n.is_pending:
                _n.is_pending = False
                _n.update()
        # Return visual selection focus to the current state
        cur_node = next((_n for _n in self._nodes.values() if _n.is_current), None)
        if cur_node:
            cur_node.is_pending = True
            cur_node.update()
        if self._btn_apply:
            self._btn_apply.setEnabled(False)
            self._btn_apply.setStyleSheet("padding:0 12px; font-weight:bold;")

    def _on_apply(self) -> None:
        """Commit the pending transition."""
        if self._pending_action and self._pending_target and self._pending_rule_id:
            rule_id = self._pending_rule_id
            action = self._pending_action
            target = self._pending_target
            self._clear_pending()
            self.transition_triggered.emit(rule_id, action, target, False)

    def _rebuild_edit_full(self, rule: WorkflowRule) -> None:
        """Edit mode: render the complete workflow graph with all states and transitions."""
        positions = _compute_layout(rule)

        for sid, sdef in rule.states.items():
            node = StateNode(
                sid, sdef, "edit",
                on_moved=self._on_node_moved,
                display_label=rule.get_state_label(sid),
            )
            node.setPos(positions.get(sid, QPointF(0, 0)))
            self._scene.addItem(node)
            self._nodes[sid] = node

        pair_count: Dict[Tuple[str, str], int] = {}
        for sid, sdef in rule.states.items():
            for t in sdef.transitions:
                key = (sid, t.target)
                pair_count[key] = pair_count.get(key, 0) + 1

        pair_seen: Dict[Tuple[str, str], int] = {}

        for sid, sdef in rule.states.items():
            src_node = self._nodes.get(sid)
            if not src_node:
                continue
            for trans in sdef.transitions:
                tgt_node = self._nodes.get(trans.target)
                if not tgt_node:
                    continue

                src_x = positions.get(sid, QPointF()).x()
                tgt_x = positions.get(trans.target, QPointF()).x()
                is_back = tgt_x <= src_x and sid != trans.target
                is_self = sid == trans.target

                ak = f"{sid}:{trans.action}"
                stored = rule.transition_anchors.get(ak)
                if stored and len(stored) == 2:
                    src_a, tgt_a = stored[0], stored[1]
                elif is_self:
                    src_a, tgt_a = "right", "right"
                elif is_back:
                    src_a, tgt_a = "bottom", "bottom"
                else:
                    src_a, tgt_a = "right", "left"

                key = (sid, trans.target)
                idx = pair_seen.get(key, 0)
                pair_seen[key] = idx + 1

                edge = TransitionEdge(
                    trans, src_node, tgt_node,
                    is_available=False,
                    is_back_edge=is_back,
                    click_callback=None,
                    edge_index=idx,
                    total_edges=pair_count[key],
                    src_anchor=src_a,
                    tgt_anchor=tgt_a,
                )
                bd = rule.transition_bends.get(ak)
                if bd and len(bd) == 4:
                    edge.ctrl1_offset = QPointF(bd[0], bd[1])
                    edge.ctrl2_offset = QPointF(bd[2], bd[3])
                elif bd and len(bd) == 2:
                    bf = 4.0 / 3.0
                    edge.ctrl1_offset = QPointF(bd[0] * bf, bd[1] * bf)
                    edge.ctrl2_offset = QPointF(bd[0] * bf, bd[1] * bf)
                edge.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                self._scene.addItem(edge)
                self._edges.append(edge)

        # Build connected-edge lists for ALL nodes after all edges are added.
        # Pure-target nodes (final states) were never assigned entries by the
        # old in-loop src_node update, so their arrows were not redrawn on drag.
        for _node in self._nodes.values():
            _node._connected_edges = [
                e for e in self._edges if e.src is _node or e.tgt is _node
            ]

        # Fanout spread
        _FANOUT = 12.0
        from collections import defaultdict as _dd
        src_groups: Dict[Tuple[str, str], List[TransitionEdge]] = _dd(list)
        tgt_groups: Dict[Tuple[str, str], List[TransitionEdge]] = _dd(list)
        for _e in self._edges:
            src_groups[(_e.src.state_id, _e.src_anchor)].append(_e)
            tgt_groups[(_e.tgt.state_id, _e.tgt_anchor)].append(_e)
        for _group in src_groups.values():
            if len(_group) <= 1:
                continue
            _tgts = [_e.tgt.state_id for _e in _group]
            if len(set(_tgts)) < len(_tgts):
                continue
            _group.sort(key=lambda _e: _e.tgt.pos().y())
            for _i, _e in enumerate(_group):
                _e.src_spread = (_i - (len(_group) - 1) / 2.0) * _FANOUT
        for _group in tgt_groups.values():
            if len(_group) <= 1:
                continue
            _srcs = [_e.src.state_id for _e in _group]
            if len(set(_srcs)) < len(_srcs):
                continue
            _group.sort(key=lambda _e: _e.src.pos().y())
            for _i, _e in enumerate(_group):
                _e.tgt_spread = (_i - (len(_group) - 1) / 2.0) * _FANOUT

    @staticmethod
    def _extract_visited(wi: Optional[Any]) -> Set[str]:
        visited: Set[str] = set()
        if not wi:
            return visited
        for entry in wi.history:
            act = entry.action
            if "->" in act and "(" in act:
                inner = act.split("(", 1)[1].split(")")[0]
                parts = inner.split("->")
                if len(parts) == 2:
                    visited.add(parts[0].strip())
                    visited.add(parts[1].strip())
        return visited

    @staticmethod
    def _state_color(step: str, sdef: Optional[WorkflowState]) -> str:
        if sdef:
            type_colors = {
                StateType.START: "#1565c0",
                StateType.END_OK: "#2e7d32",
                StateType.END_NOK: "#c62828",
                StateType.END_NEUTRAL: "#607d8b",
            }
            if sdef.state_type in type_colors:
                return type_colors[sdef.state_type]
            if sdef.final:
                return ("#c62828"
                        if any(k in step.upper() for k in ("REJECT", "ERROR", "FAIL", "SPAM", "CANCEL"))
                        else "#2e7d32")
        sl = step.lower()
        if "new" in sl:     return "#1565c0"
        if "pending" in sl or "wait" in sl: return "#f57c00"
        if "urgent" in sl or "error" in sl: return "#c62828"
        if "review" in sl or "check" in sl or "verif" in sl: return "#7b1fa2"
        return "#607d8b"

    # ── View helpers ──────────────────────────────────────────────────────────

    def _fit_view(self) -> None:
        if self.mode == "run" and self._nodes:
            # Only fit to items that are actually visible (opacity > 0.15).
            # Dimmed non-relevant nodes/edges (opacity 0.1) must not affect the rect.
            r = QRectF()
            for item in self._scene.items():
                if item.opacity() > 0.15:
                    mapped = item.mapToScene(item.boundingRect())
                    r = r.united(mapped.boundingRect())
        else:
            r = self._scene.itemsBoundingRect()
        if r.isNull() or self._view.width() < 10:
            return
        padded = r.adjusted(-24, -24, 24, 24)
        # Generous sceneRect gives room to pan when zoomed in
        self._scene.setSceneRect(r.adjusted(-300, -300, 300, 300))
        self._view.fitInView(padded, Qt.AspectRatioMode.KeepAspectRatio)

        # Cap maximum zoom: if fitInView produced a scale > 1.0 (content smaller
        # than viewport), reset to 1:1 and centre instead — avoids oversized nodes
        # when only a few states are visible in run mode.
        t = self._view.transform()
        if t.m11() > 1.0:
            self._view.resetTransform()
            self._view.centerOn(r.center())

        self._user_zoomed = False

    def _zoom_in(self) -> None:
        self._view.scale(1.25, 1.25)
        self._user_zoomed = True

    def _zoom_out(self) -> None:
        self._view.scale(0.8, 0.8)
        self._user_zoomed = True

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_view)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._user_zoomed:
            self._fit_timer.start()   # restarts the 120 ms countdown on every resize

    # ── Edit mode — commands ──────────────────────────────────────────────────

    def _cmd_add_state(self) -> None:
        if not self._rule:
            return
        label, ok = QInputDialog.getText(self, self.tr("Add State"),
                                         self.tr("Label for the new state:"))
        if not ok or not label.strip():
            return
        sid = make_state_id()
        self._rule.states[sid] = WorkflowState(label=label.strip())
        self._rebuild()
        self.rule_changed.emit()

    def _cmd_add_transition(self) -> None:
        if not self._rule or len(self._rule.states) < 2:
            return
        dlg = AddTransitionDialog(self._rule.states, self)
        if dlg.exec():
            src, label, tgt, auto, req = dlg.get_values()
            if src in self._rule.states and tgt in self._rule.states:
                self._rule.states[src].transitions.append(
                    WorkflowTransition(
                        action=make_action_id(), label=label,
                        target=tgt, auto=auto, required_fields=req,
                    )
                )
                self._rebuild()
                self.rule_changed.emit()

    def _cmd_delete_selected(self) -> None:
        if not self._rule:
            return
        for item in self._scene.selectedItems():
            if isinstance(item, StateNode):
                sid = item.state_id
                if len(self._rule.states) <= 1:
                    continue
                del self._rule.states[sid]
                for sdef in self._rule.states.values():
                    sdef.transitions = [t for t in sdef.transitions if t.target != sid]
            elif isinstance(item, TransitionEdge):
                # Remove matching transition
                for sid, sdef in self._rule.states.items():
                    sdef.transitions = [
                        t for t in sdef.transitions
                        if not (t.action == item.transition.action
                                and t.target == item.transition.target
                                and sid == item.src.state_id)
                    ]
        self._rebuild()
        self.rule_changed.emit()

    # ── Edit mode — detail panel ──────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        # Remove stale endpoint handles
        for h in self._handles:
            self._scene.removeItem(h)
        self._handles.clear()

        selected = self._scene.selectedItems()
        item = selected[0] if selected else None

        # Endpoint handles + two ctrl-point handles for selected edge
        if isinstance(item, TransitionEdge):
            h_src   = EndpointHandle(item, True,  self._on_anchor_committed)
            h_tgt   = EndpointHandle(item, False, self._on_anchor_committed)
            h_ctrl1 = CtrlHandle(item, "ctrl1", self._on_ctrl_committed)
            h_ctrl2 = CtrlHandle(item, "ctrl2", self._on_ctrl_committed)
            # Skip ctrl handles for self-loops (no _ctrl_points)
            self._scene.addItem(h_src)
            self._scene.addItem(h_tgt)
            handles = [h_src, h_tgt]
            if item.src is not item.tgt:
                self._scene.addItem(h_ctrl1)
                self._scene.addItem(h_ctrl2)
                handles += [h_ctrl1, h_ctrl2]
            self._handles = handles

        if not self.inline_detail:
            self.item_selected.emit(item)
            return

        # Inline detail panel
        while self._detail_form_layout.rowCount():
            self._detail_form_layout.removeRow(0)

        if not selected:
            self._detail_hint.show()
            self._detail_form.hide()
            return

        self._detail_hint.hide()
        self._detail_form.show()

        if isinstance(item, StateNode):
            self._populate_state_detail(item)
        elif isinstance(item, TransitionEdge):
            self._populate_transition_detail(item)

    def _populate_state_detail(self, node: StateNode) -> None:
        fl = self._detail_form_layout

        lbl_edit = QLineEdit(node.state_def.label)
        fl.addRow(self.tr("Label:"), lbl_edit)

        type_combo = QComboBox()
        _type_labels = {
            StateType.START: self.tr("START — Entry point"),
            StateType.NORMAL: self.tr("NORMAL — Intermediate"),
            StateType.END_OK: self.tr("END OK — Positive terminal"),
            StateType.END_NOK: self.tr("END NOK — Negative terminal"),
            StateType.END_NEUTRAL: self.tr("END NEUTRAL — Neutral terminal"),
        }
        for st, label in _type_labels.items():
            type_combo.addItem(label, userData=st)
        current_type = node.state_def.state_type
        idx = list(_type_labels.keys()).index(current_type) if current_type in _type_labels else 1
        type_combo.setCurrentIndex(idx)
        fl.addRow(self.tr("Type:"), type_combo)

        def _apply():
            if not self._rule:
                return
            node.state_def.label = lbl_edit.text().strip()
            node.display_label = node.state_def.label or node.state_id
            chosen_type: StateType = type_combo.currentData()
            node.state_def.state_type = chosen_type
            node.state_def.final = chosen_type in (StateType.END_OK, StateType.END_NOK, StateType.END_NEUTRAL)
            node.state_def.initial = chosen_type == StateType.START
            node.update()
            self._rebuild()
            self.rule_changed.emit()

        apply_btn = QPushButton(self.tr("Apply"))
        apply_btn.setFixedHeight(26)
        apply_btn.clicked.connect(_apply)
        fl.addRow("", apply_btn)

    def _populate_transition_detail(self, edge: TransitionEdge) -> None:
        fl = self._detail_form_layout
        t = edge.transition

        label_edit = QLineEdit(t.label or t.action)
        fl.addRow(self.tr("Label:"), label_edit)

        auto_chk = QCheckBox()
        auto_chk.setChecked(t.auto)
        fl.addRow(self.tr("Auto:"), auto_chk)

        req_edit = QLineEdit(", ".join(t.required_fields))
        req_edit.setPlaceholderText("iban, total_gross, …")
        fl.addRow(self.tr("Required Fields:"), req_edit)

        def _apply():
            t.label = label_edit.text().strip()
            t.auto = auto_chk.isChecked()
            t.required_fields = [f.strip() for f in req_edit.text().split(",") if f.strip()]
            self._rebuild()
            self.rule_changed.emit()

        apply_btn = QPushButton(self.tr("Apply"))
        apply_btn.setFixedHeight(26)
        apply_btn.clicked.connect(_apply)
        fl.addRow("", apply_btn)

    # ── Edit mode — node-moved callback ──────────────────────────────────────

    def _on_node_moved(self, state_id: str, new_pos: QPointF) -> None:
        if self._rule is not None:
            self._rule.node_positions[state_id] = [new_pos.x(), new_pos.y()]
            self.rule_changed.emit()
        # Snap endpoint and ctrl-point handles to the updated edge geometry.
        # Without this, orange ctrl diamonds stay at their old positions while
        # the underlying Bezier curve moves, leaving visual artifacts.
        for h in self._handles:
            h._snap_to_edge()

    # ── Edit mode — anchor-committed callback ─────────────────────────────────

    def _on_anchor_committed(
        self, edge: TransitionEdge, is_source: bool, new_anchor: str
    ) -> None:
        """Persist a new anchor for *edge*; swap if another edge already uses it."""
        if not self._rule:
            return
        node = edge.src if is_source else edge.tgt
        old_anchor = edge.src_anchor if is_source else edge.tgt_anchor

        # Swap: if another edge already occupies new_anchor on the same node/side
        for other in self._edges:
            if other is edge:
                continue
            if is_source and other.src is node and other.src_anchor == new_anchor:
                other.src_anchor = old_anchor
                ak = f"{other.src.state_id}:{other.transition.action}"
                self._rule.transition_anchors[ak] = [other.src_anchor, other.tgt_anchor]
                other.prepareGeometryChange()
                other.update()
            elif not is_source and other.tgt is node and other.tgt_anchor == new_anchor:
                other.tgt_anchor = old_anchor
                ak = f"{other.src.state_id}:{other.transition.action}"
                self._rule.transition_anchors[ak] = [other.src_anchor, other.tgt_anchor]
                other.prepareGeometryChange()
                other.update()

        # Apply to this edge (may already be set by live preview)
        if is_source:
            edge.src_anchor = new_anchor
        else:
            edge.tgt_anchor = new_anchor
        ak = f"{edge.src.state_id}:{edge.transition.action}"
        self._rule.transition_anchors[ak] = [edge.src_anchor, edge.tgt_anchor]
        edge.prepareGeometryChange()
        edge.update()

        # Snap handles to updated positions
        for h in self._handles:
            h._snap_to_edge()

        self.rule_changed.emit()

    def _on_ctrl_committed(self, edge: "TransitionEdge") -> None:
        """Persist both ctrl-point offsets for *edge* into the rule."""
        if not self._rule:
            return
        ak = f"{edge.src.state_id}:{edge.transition.action}"
        c1, c2 = edge.ctrl1_offset, edge.ctrl2_offset
        if c1.x() == 0 and c1.y() == 0 and c2.x() == 0 and c2.y() == 0:
            self._rule.transition_bends.pop(ak, None)
        else:
            self._rule.transition_bends[ak] = [c1.x(), c1.y(), c2.x(), c2.y()]
        self.rule_changed.emit()


# ── Container for multiple graphs in run mode ─────────────────────────────────

class WorkflowGraphsPanel(QWidget):
    """
    Scroll area containing one WorkflowGraphWidget per active workflow.
    Used in the MetadataEditor 'Workflows' tab.
    """

    transition_triggered = pyqtSignal(str, str, str, bool)
    rule_changed = pyqtSignal(str)  # new_rule_id (for assignment change)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._graphs: Dict[str, WorkflowGraphWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(8, 8, 8, 8)
        self._inner_layout.setSpacing(8)
        self._inner_layout.addStretch()
        self._scroll.setWidget(self._inner)
        layout.addWidget(self._scroll)

    def update_workflows(
        self,
        workflows: Dict[str, Any],
        rule_registry: Any,
        doc_data: Dict[str, Any],
    ) -> None:
        """
        Rebuild/update graph widgets to match the given workflows dict.
        workflows: {rule_id: WorkflowInfo}
        """
        existing = set(self._graphs.keys())
        current = set(workflows.keys())

        # Remove stale
        for rid in existing - current:
            w = self._graphs.pop(rid)
            self._inner_layout.removeWidget(w)
            w.setParent(None)

        # Add / refresh
        for rid, wf_info in workflows.items():
            rule = rule_registry.get_rule(rid)
            if not rule:
                continue
            if rid not in self._graphs:
                g = WorkflowGraphWidget(mode="run")
                g.setMinimumHeight(220)
                g.transition_triggered.connect(self.transition_triggered.emit)
                self._graphs[rid] = g
                # Insert before the trailing stretch
                self._inner_layout.insertWidget(self._inner_layout.count() - 1, g)
            self._graphs[rid].load(rule, wf_info, doc_data)

    def clear(self) -> None:
        for rid in list(self._graphs.keys()):
            w = self._graphs.pop(rid)
            self._inner_layout.removeWidget(w)
            w.setParent(None)
