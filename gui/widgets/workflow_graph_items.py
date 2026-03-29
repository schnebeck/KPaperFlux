"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/workflow_graph_items.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Graphics-item classes and layout helpers for the workflow
                graph editor. Contains StateNode, AnchorDot, TransitionEdge,
                AddTransitionDialog, EndpointHandle, CtrlHandle, all
                module-level constants, and the layout/anchor helper functions.
------------------------------------------------------------------------------
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath,
    QPainterPathStroker, QPen, QPolygonF, QCursor,
)
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGraphicsItem,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout,
)

from core.logger import get_logger
from core.workflow import (
    WorkflowRule, WorkflowState, WorkflowTransition,
    StateType,
)

logger = get_logger("gui.widgets.workflow_graph_items")

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
