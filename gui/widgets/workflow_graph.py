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
from core.semantic_translator import SemanticTranslator
from core.workflow import WorkflowEngine, WorkflowRule, WorkflowState, WorkflowTransition

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
C_BG_VIS   = QColor("#e8ecef")
C_BG_DEF   = QColor("#f8fafd")
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
        by_layer[layer].sort(key=lambda s: (rule.states[s].final, s))

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
    ) -> None:
        super().__init__()
        self.state_id = state_id
        self.state_def = state_def
        self.mode = mode
        self.is_current = is_current
        self.is_visited = is_visited
        self._on_moved = on_moved
        self._hovered = False
        self._connected_edges: List["TransitionEdge"] = []

        st = SemanticTranslator.instance()
        self.display_label = st.translate(state_def.label) if state_def.label else state_id

        self.setAcceptHoverEvents(True)
        if mode == "edit":
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

    # ── QGraphicsItem interface ───────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        return QRectF(-NODE_W / 2, -NODE_H / 2, NODE_W, NODE_H)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        r = self.boundingRect()

        # Background
        if self.is_current:
            bg = C_BG_CUR
        elif self.is_visited:
            bg = C_BG_VIS
        else:
            bg = C_BG_DEF

        # Border colour
        if self.is_current:
            border_c = C_CURRENT
            bw = 2.5
        elif self.state_def.final:
            border_c = C_FINAL_NG if self._is_error_final() else C_FINAL_OK
            bw = 2.0
        elif self.is_visited:
            border_c = C_VISITED
            bw = 1.5
        else:
            border_c = C_DEFAULT
            bw = 1.5

        if self._hovered and self.mode == "edit":
            bw += 0.8

        # Selection highlight (edit mode)
        if self.isSelected() and self.mode == "edit":
            painter.setPen(QPen(QColor("#2196f3"), 2.0, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(r.adjusted(-4, -4, 4, 4), BORDER_R + 4, BORDER_R + 4)

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border_c, bw))
        painter.drawRoundedRect(r, BORDER_R, BORDER_R)

        # Double border for final states (UML convention)
        if self.state_def.final:
            c = border_c
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(c, 1.0))
            painter.drawRoundedRect(r.adjusted(4, 4, -4, -4), BORDER_R - 3, BORDER_R - 3)

        # Label
        font = QFont()
        font.setPointSize(9)
        font.setBold(self.is_current)
        painter.setFont(font)
        painter.setPen(QPen(border_c))
        painter.drawText(r.adjusted(6, 3, -6, -3),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                         self.display_label)

        # Current-state dot (top-right corner)
        if self.is_current:
            painter.setBrush(QBrush(C_CURRENT))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(r.right() - 10, r.top() + 10), 4, 4)

    # ── Hover & drag ─────────────────────────────────────────────────────────

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self._connected_edges:
                edge.prepareGeometryChange()
                edge.update()
            if self._on_moved:
                self._on_moved(self.state_id, value)
        return super().itemChange(change, value)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_error_final(self) -> bool:
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

        st = SemanticTranslator.instance()
        raw = transition.action.replace("_", " ").capitalize()
        self._label = st.translate(raw)
        if transition.auto:
            self._label = f"⚡ {self._label}"

        self.setZValue(-1)
        self.setAcceptHoverEvents(True)
        if is_available and click_callback and not transition.auto:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    # ── Path computation ──────────────────────────────────────────────────────

    def _y_offset(self) -> float:
        """Perpendicular offset for parallel edges between the same pair."""
        return (self.edge_index - (self.total_edges - 1) / 2.0) * MULTI_OFF

    def _path_and_label(self) -> Tuple[QPainterPath, QPointF]:
        sp = self.src.pos()
        tp = self.tgt.pos()
        off = self._y_offset()

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

        # Anchor-based tangent Bezier for all other edges
        src_pt = _anchor_point(sp, self.src_anchor)
        tgt_pt = _anchor_point(tp, self.tgt_anchor)

        # Perpendicular offset for parallel edges
        if off:
            dx = tgt_pt.x() - src_pt.x()
            dy = tgt_pt.y() - src_pt.y()
            length = math.sqrt(dx * dx + dy * dy) or 1.0
            px, py = -dy / length * off, dx / length * off
            src_pt = QPointF(src_pt.x() + px, src_pt.y() + py)
            tgt_pt = QPointF(tgt_pt.x() + px, tgt_pt.y() + py)

        src_tang = _anchor_tangent(self.src_anchor)
        tgt_tang = _anchor_tangent(self.tgt_anchor)

        dx = tgt_pt.x() - src_pt.x()
        dy = tgt_pt.y() - src_pt.y()
        dist = max(math.sqrt(dx * dx + dy * dy), 1.0)
        ctrl_d = max(CTRL_DIST_MIN, dist * 0.42)

        ctrl1 = QPointF(src_pt.x() + src_tang.x() * ctrl_d,
                        src_pt.y() + src_tang.y() * ctrl_d)
        ctrl2 = QPointF(tgt_pt.x() + tgt_tang.x() * ctrl_d,
                        tgt_pt.y() + tgt_tang.y() * ctrl_d)

        path = QPainterPath(src_pt)
        path.cubicTo(ctrl1, ctrl2, tgt_pt)

        mid = path.pointAtPercent(0.5)
        return path, QPointF(mid.x(), mid.y() - 13)

    # ── QGraphicsItem interface ───────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        path, _ = self._path_and_label()
        return path.boundingRect().adjusted(-20, -20, 20, 20)

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

        # Selection highlight
        if self.isSelected():
            painter.setPen(QPen(QColor("#2196f3"), pw + 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        painter.setPen(QPen(col, pw, style))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Arrowhead
        end = path.pointAtPercent(1.0)
        pre = path.pointAtPercent(0.97)
        ang = math.atan2(end.y() - pre.y(), end.x() - pre.x())
        p1 = QPointF(end.x() - ARROW * math.cos(ang - math.pi / 6),
                     end.y() - ARROW * math.sin(ang - math.pi / 6))
        p2 = QPointF(end.x() - ARROW * math.cos(ang + math.pi / 6),
                     end.y() - ARROW * math.sin(ang + math.pi / 6))
        painter.setBrush(QBrush(col))
        painter.setPen(QPen(col, 1))
        painter.drawPolygon(QPolygonF([end, p1, p2]))

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

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and self.is_available
                and self._click_cb
                and not self.transition.auto):
            self._click_cb(self)
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

        st = SemanticTranslator.instance()
        # Build display entries: "Label (ID)" stored with ID as UserData
        self._state_ids: List[str] = list(states.keys())
        display_items: List[Tuple[str, str]] = []
        for sid, sdef in states.items():
            label = st.translate(sdef.label) if sdef.label else sid
            display_items.append((f"{label}  ({sid})", sid))

        layout = QFormLayout(self)
        layout.setSpacing(10)

        self._src = QComboBox()
        for display, sid in display_items:
            self._src.addItem(display, sid)
        layout.addRow(self.tr("From State:"), self._src)

        self._action = QLineEdit()
        self._action.setPlaceholderText(self.tr("e.g. verify, approve, reject"))
        layout.addRow(self.tr("Action:"), self._action)

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
        req = [f.strip() for f in self._req.text().split(",") if f.strip()]
        return (
            self._src.currentData(),   # ID, not display text
            self._action.text().strip().lower(),
            self._tgt.currentData(),   # ID, not display text
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


# ── WorkflowGraphWidget ───────────────────────────────────────────────────────

class WorkflowGraphWidget(QWidget):
    """
    Visual state-machine widget for a single WorkflowRule.

    mode="run"  — read-only, clickable available transitions.
    mode="edit" — drag nodes, add/remove states/transitions, inline detail panel.
    """

    transition_triggered = pyqtSignal(str, str, str, bool)  # rule_id, action, target, is_auto
    rule_changed = pyqtSignal()  # edit mode: underlying rule was modified

    def __init__(self, mode: str = "run", parent=None) -> None:
        super().__init__(parent)
        assert mode in ("run", "edit")
        self.mode = mode
        self._rule: Optional[WorkflowRule] = None
        self._wf_info: Optional[Any] = None
        self._doc_data: Dict[str, Any] = {}
        self._nodes: Dict[str, StateNode] = {}
        self._edges: List[TransitionEdge] = []
        self._handles: List[EndpointHandle] = []
        self._init_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        self._header = QFrame()
        self._header.setFixedHeight(32)
        self._header.setStyleSheet(
            "background:#f1f5f9; border-bottom:1px solid #e2e8f0;"
        )
        hdr = QHBoxLayout(self._header)
        hdr.setContentsMargins(10, 0, 10, 0)
        hdr.setSpacing(8)
        self._hdr_layout = hdr

        self._rule_lbl = QLabel()
        self._rule_lbl.setStyleSheet("font-weight:bold; color:#334155;")
        hdr.addWidget(self._rule_lbl)

        self._badge = QLabel()
        self._badge.setStyleSheet(
            "font-size:10px; padding:2px 8px; border-radius:8px;"
            " background:#607d8b; color:white; font-weight:bold;"
        )
        hdr.addWidget(self._badge)
        hdr.addStretch()

        if self.mode == "edit":
            self._build_edit_toolbar(hdr)

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
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )
        self._view.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag
            if self.mode == "run"
            else QGraphicsView.DragMode.RubberBandDrag
        )
        self._view.setFrameShape(QFrame.Shape.NoFrame)
        self._view.setBackgroundBrush(QBrush(C_SCENE_BG))
        self._view.setMinimumHeight(180)
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        vbox.addWidget(self._view, 1)

        if self.mode == "edit":
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
            if self.mode == "edit":
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
        rule: WorkflowRule,
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

    def _rebuild(self) -> None:
        if not self._rule:
            return

        self._handles.clear()  # scene.clear() removes them from scene
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()

        rule = self._rule
        wi = self._wf_info
        st = SemanticTranslator.instance()

        current_step = wi.current_step if wi else "NEW"
        visited_states = self._extract_visited(wi)

        positions = _compute_layout(rule)
        engine = WorkflowEngine(rule) if self.mode == "run" else None

        # Create nodes
        for sid, sdef in rule.states.items():
            is_cur = (sid == current_step) and self.mode == "run"
            is_vis = sid in visited_states and not is_cur and self.mode == "run"
            node = StateNode(
                sid, sdef, self.mode, is_cur, is_vis,
                on_moved=self._on_node_moved if self.mode == "edit" else None,
            )
            node.setPos(positions.get(sid, QPointF(0, 0)))
            self._scene.addItem(node)
            self._nodes[sid] = node

        # Count parallel edges per (src, tgt) pair
        pair_count: Dict[Tuple[str, str], int] = {}
        for sid, sdef in rule.states.items():
            for t in sdef.transitions:
                key = (sid, t.target)
                pair_count[key] = pair_count.get(key, 0) + 1

        pair_seen: Dict[Tuple[str, str], int] = {}

        # Create edges
        for sid, sdef in rule.states.items():
            src_node = self._nodes.get(sid)
            if not src_node:
                continue
            for trans in sdef.transitions:
                tgt_node = self._nodes.get(trans.target)
                if not tgt_node:
                    continue

                # Available = from current state AND condition met
                is_avail = False
                if engine and sid == current_step:
                    if trans.auto:
                        is_avail = engine.evaluate_transition(trans, self._doc_data)
                    else:
                        is_avail = engine.can_transition(current_step, trans.action, self._doc_data)

                # Back-edge if target x-pos ≤ source x-pos (and not self-loop)
                src_x = positions.get(sid, QPointF()).x()
                tgt_x = positions.get(trans.target, QPointF()).x()
                is_back = tgt_x <= src_x and sid != trans.target
                is_self = sid == trans.target

                # Determine anchor points (stored > defaults)
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
                total = pair_count[key]

                def _make_cb(rule_id: str, t: WorkflowTransition):
                    def cb(edge: TransitionEdge) -> None:
                        self.transition_triggered.emit(rule_id, t.action, t.target, False)
                    return cb

                edge = TransitionEdge(
                    trans, src_node, tgt_node,
                    is_available=is_avail,
                    is_back_edge=is_back,
                    click_callback=_make_cb(rule.id, trans) if self.mode == "run" else None,
                    edge_index=idx,
                    total_edges=total,
                    src_anchor=src_a,
                    tgt_anchor=tgt_a,
                )
                if self.mode == "edit":
                    edge.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                self._scene.addItem(edge)
                self._edges.append(edge)

            # Link edges to nodes for geometry-change propagation
            src_node._connected_edges = [
                e for e in self._edges if e.src is src_node or e.tgt is src_node
            ]

        # Header badge
        sdef_cur = rule.states.get(current_step)
        badge_text = st.translate(sdef_cur.label) if sdef_cur and sdef_cur.label else current_step
        badge_col = self._state_color(current_step, sdef_cur)
        self._rule_lbl.setText(st.translate(rule.name or rule.id))
        self._badge.setText(badge_text)
        self._badge.setStyleSheet(
            f"font-size:10px; padding:2px 8px; border-radius:8px;"
            f" background:{badge_col}; color:white; font-weight:bold;"
        )

        QTimer.singleShot(50, self._fit_view)

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
        if sdef and sdef.final:
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
        r = self._scene.itemsBoundingRect()
        if r.isNull() or self._view.width() < 10:
            return
        padded = r.adjusted(-24, -24, 24, 24)
        # Constrain scene rect to actual content so the background does not
        # bleed into empty areas left/right of the fitted items.
        self._scene.setSceneRect(padded)
        self._view.fitInView(padded, Qt.AspectRatioMode.KeepAspectRatio)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_view)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(10, self._fit_view)

    # ── Edit mode — commands ──────────────────────────────────────────────────

    def _cmd_add_state(self) -> None:
        if not self._rule:
            return
        sid, ok = QInputDialog.getText(self, self.tr("Add State"),
                                       self.tr("State ID (uppercase, e.g. PROCESSING):"))
        if not ok or not sid.strip():
            return
        sid = sid.strip().upper()
        if sid in self._rule.states:
            return
        label, ok2 = QInputDialog.getText(self, self.tr("Add State"),
                                          self.tr("Display label for '%s':") % sid)
        if not ok2:
            return
        self._rule.states[sid] = WorkflowState(label=label.strip())
        self._rebuild()
        self.rule_changed.emit()

    def _cmd_add_transition(self) -> None:
        if not self._rule or len(self._rule.states) < 2:
            return
        dlg = AddTransitionDialog(self._rule.states, self)
        if dlg.exec():
            src, action, tgt, auto, req = dlg.get_values()
            if not action:
                return
            if src in self._rule.states and tgt in self._rule.states:
                self._rule.states[src].transitions.append(
                    WorkflowTransition(action=action, target=tgt, auto=auto, required_fields=req)
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
        # Clear old form widgets
        while self._detail_form_layout.rowCount():
            self._detail_form_layout.removeRow(0)

        if not selected:
            self._detail_hint.show()
            self._detail_form.hide()
            return

        item = selected[0]
        self._detail_hint.hide()
        self._detail_form.show()

        if isinstance(item, StateNode):
            self._populate_state_detail(item)
        elif isinstance(item, TransitionEdge):
            self._populate_transition_detail(item)
            # Show draggable endpoint handles for anchor repositioning
            h_src = EndpointHandle(item, True,  self._on_anchor_committed)
            h_tgt = EndpointHandle(item, False, self._on_anchor_committed)
            self._scene.addItem(h_src)
            self._scene.addItem(h_tgt)
            self._handles = [h_src, h_tgt]

    def _populate_state_detail(self, node: StateNode) -> None:
        fl = self._detail_form_layout
        fl.addRow(self.tr("ID:"), QLabel(node.state_id))

        lbl_edit = QLineEdit(node.state_def.label)
        fl.addRow(self.tr("Label:"), lbl_edit)

        final_chk = QCheckBox()
        final_chk.setChecked(node.state_def.final)
        fl.addRow(self.tr("Final state:"), final_chk)

        def _apply():
            if not self._rule:
                return
            node.state_def.label = lbl_edit.text().strip()
            node.display_label = SemanticTranslator.instance().translate(node.state_def.label) or node.state_id
            node.state_def.final = final_chk.isChecked()
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

        action_edit = QLineEdit(t.action)
        fl.addRow(self.tr("Action:"), action_edit)

        auto_chk = QCheckBox()
        auto_chk.setChecked(t.auto)
        fl.addRow(self.tr("Auto:"), auto_chk)

        req_edit = QLineEdit(", ".join(t.required_fields))
        req_edit.setPlaceholderText("iban, total_gross, …")
        fl.addRow(self.tr("Required Fields:"), req_edit)

        def _apply():
            new_action = action_edit.text().strip().lower()
            if not new_action:
                return
            t.action = new_action
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
