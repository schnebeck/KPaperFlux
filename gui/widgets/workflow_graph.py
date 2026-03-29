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

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QCursor
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGraphicsItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
    QFormLayout,
)

from core.logger import get_logger
from core.workflow import (
    WorkflowEngine, WorkflowRule, WorkflowState, WorkflowTransition,
    StateType, make_state_id, make_action_id,
)

from gui.widgets.workflow_graph_items import (
    StateNode, AnchorDot, TransitionEdge, AddTransitionDialog,
    EndpointHandle, CtrlHandle,
    NODE_W, NODE_H, H_GAP, V_GAP, ARROW, BORDER_R, BACK_DROP, MULTI_OFF,
    ANCHOR_NAMES, CTRL_DIST_MIN, ANCHOR_SNAP,
    C_CURRENT, C_VISITED, C_DEFAULT, C_FINAL_OK, C_FINAL_NG,
    C_AVAIL, C_BLOCKED, C_AUTO, C_BG_CUR, C_BG_TGT, C_BG_VIS, C_BG_DEF,
    C_PENDING, C_BG_PEND, C_SCENE_BG,
    _anchor_point, _anchor_tangent, _compute_layout,
)

logger = get_logger("gui.widgets.workflow_graph")

# Re-export item classes so that existing imports like:
#   from gui.widgets.workflow_graph import WorkflowGraphWidget, StateNode, TransitionEdge
# continue to work without modification.
__all__ = [
    "WorkflowGraphWidget",
    "WorkflowGraphsPanel",
    "StateNode",
    "AnchorDot",
    "TransitionEdge",
    "AddTransitionDialog",
    "EndpointHandle",
    "CtrlHandle",
]


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
