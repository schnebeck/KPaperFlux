"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/dashboard.py
Version:        2.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Gemini 3pro
Description:    Interactive dashboard for document statistics and quick filters.
------------------------------------------------------------------------------
"""

import json
import os
import shutil
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFrame, 
                             QHBoxLayout, QScrollArea, QSizePolicy, QMenu, QInputDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QPropertyAnimation, QEasingCurve, pyqtProperty, QTimer
from PyQt6.QtGui import QAction, QCursor, QPalette, QPainter, QColor, QFont, QPen, QBrush, QLinearGradient, QPainterPath
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QPropertyAnimation, QEasingCurve, pyqtProperty, QTimer, QRect

from gui.dialogs.dashboard_entry_dialog import DashboardEntryDialog
from core.config import AppConfig

CELL_WIDTH = 280
CELL_HEIGHT = 180
SPACING = 25
MARGIN = 30

class SparklineWidget(QWidget):
    """Small, minimalist line chart for StatCards."""
    def __init__(self, color_hex, parent=None):
        super().__init__(parent)
        self.data = []
        self.color = QColor(color_hex)
        self.setFixedHeight(45)

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, event):
        if len(self.data) < 2: return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        m_b = 5 # bottom margin for labels/axis
        draw_h = h - m_b - 5
        
        # We always want 0 as the baseline for activity
        max_v = max(self.data) if self.data else 1
        min_v = 0 # Force zero baseline as requested
        v_range = (max_v - min_v) if max_v != min_v else 1
        
        points = []
        x_step = w / (len(self.data) - 1)
        for i, val in enumerate(self.data):
            px = i * x_step
            py = h - m_b - ((val - min_v) / v_range) * draw_h
            points.append(QPoint(int(px), int(py)))
            
        # Draw subtle Axes
        painter.setPen(QPen(QColor("#e5e7eb"), 1))
        painter.drawLine(0, h - m_b, w, h - m_b) # X-Axis (Zero Line)
        painter.drawLine(0, 0, 0, h - m_b)      # Y-Axis
        
        # Draw Gradient Area
        path = QPainterPath()
        path.moveTo(0, h - m_b)
        for p in points: path.lineTo(p.x(), p.y())
        path.lineTo(w, h - m_b)
        path.closeSubpath()
        
        grad = QLinearGradient(0, 0, 0, h)
        c_fill = QColor(self.color)
        c_fill.setAlpha(30)
        grad.setColorAt(0, c_fill)
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        painter.fillPath(path, grad)
        
        # Draw Line
        painter.setPen(QPen(self.color, 2))
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i+1])

class StatCard(QFrame):
    clicked = pyqtSignal(dict) # Emits the filter query
    edit_requested = pyqtSignal()
    rename_requested = pyqtSignal()
    delete_requested = pyqtSignal()

    def __init__(self, title, value, color_hex, filter_query, aggregation="count", sparkdata=None, parent=None):
        super().__init__(parent)
        self.filter_query = filter_query
        self.color_hex = color_hex
        self.aggregation = aggregation
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setObjectName("StatCard")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        self.setFixedSize(CELL_WIDTH, CELL_HEIGHT)
        
        # Animations
        self._pos_anim = QPropertyAnimation(self, b"pos")
        self._pos_anim.setDuration(350)
        self._pos_anim.setEasingCurve(QEasingCurve.Type.OutQuint)
        
        # Styles
        self.setStyleSheet(f"""
            QFrame#StatCard {{
                background-color: white;
                border: 1px solid #e5e7eb;
                border-radius: 16px;
            }}
            QFrame#StatCard:hover {{
                border: 1.5px solid {color_hex};
                background-color: #ffffff;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 12)
        layout.setSpacing(4)
        
        # Icon mapping
        icons = {
            "Inbox": "📥", "Total Documents": "📄", "Total Invoiced": "💰", 
            "Processed": "✅", "Trash": "🗑️", "Taxes": "🏛️"
        }
        icon = icons.get(title, "📊")
        
        # Title row
        title_row = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size: 16pt; background: {color_hex}15; padding: 5px; border-radius: 8px;")
        title_row.addWidget(icon_lbl)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #64748b; font-weight: 600; font-size: 10pt;")
        title_row.addWidget(lbl_title, 1)
        
        self.lbl_agg = QLabel(aggregation.upper())
        self.lbl_agg.setStyleSheet(f"color: {color_hex}; background-color: {color_hex}15; padding: 2px 6px; border-radius: 6px; font-size: 7pt; font-weight: bold;")
        title_row.addWidget(self.lbl_agg, 0, Qt.AlignmentFlag.AlignTop)
        
        layout.addLayout(title_row)
        
        # Value
        display_val = ""
        if aggregation == "sum":
            display_val = f"{float(value):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            display_val = str(value)
            
        self.lbl_count = QLabel(display_val)
        self.lbl_count.setStyleSheet(f"color: #1e293b; font-weight: 800; font-size: 24pt;")
        layout.addWidget(self.lbl_count)
        
        # Sparkline (The "Living" part)
        self.sparkline = SparklineWidget(color_hex)
        if sparkdata:
            self.sparkline.set_data(sparkdata)
        else:
            self.sparkline.set_data([0.0] * 31) # Flat zero line
             
        layout.addWidget(self.sparkline)

    def move_animated(self, new_pos):
        if self.pos() == new_pos:
            return
        self._pos_anim.stop()
        self._pos_anim.setEndValue(new_pos)
        self._pos_anim.start()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        rename_action = menu.addAction(self.tr("Rename..."))
        edit_action = menu.addAction(self.tr("Edit Configuration..."))
        menu.addSeparator()
        delete_action = menu.addAction(self.tr("Remove from Dashboard"))
        
        action = menu.exec(self.mapToGlobal(pos))
        if action == rename_action:
            self.rename_requested.emit()
        elif action == edit_action:
            self.edit_requested.emit()
        elif action == delete_action:
            self.delete_requested.emit()

class DashboardWidget(QWidget):
    navigation_requested = pyqtSignal(dict) # Emits filter query to MainWindow

    def __init__(self, db_manager, filter_tree=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.filter_tree = filter_tree
        
        self.app_config = AppConfig()
        self.config_path = self.app_config.get_config_dir() / "dashboard_config.json"
        
        # Migration: Check if old config exists in CWD and move it if target doesn't exist
        old_config = Path("dashboard_config.json")
        if old_config.exists() and not self.config_path.exists():
            try:
                shutil.move(str(old_config), str(self.config_path))
                print(f"[Info] Migrated dashboard config to {self.config_path}")
            except Exception as e:
                print(f"[Error] Failed to migrate dashboard config: {e}")
        
        self.cards_config = []
        self.card_widgets = []
        self.locked = True # Default for safety
        
        # Drag state
        self.dragging_widget = None
        self.drag_start_mouse_pos = QPoint()
        self.drag_original_widget_pos = QPoint()
        self.drag_has_moved = False
        
        self.load_config()
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False) # We manage size
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background-color: #f3f4f6;")
        
        self.content_widget = QWidget()
        self.content_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.content_widget.customContextMenuRequested.connect(self._show_dashboard_menu)
        
        self.scroll.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll)
        
        self.refresh_stats()

    def load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list): # Migration from old format
                        self.cards_config = data
                        self.locked = True
                    else:
                        self.cards_config = data.get("cards", [])
                        self.locked = data.get("locked", True)
            except:
                self.cards_config = []
        
        if not self.cards_config:
            self.cards_config = [
                {"title": self.tr("Inbox"), "preset_id": "NEW", "color": "#3b82f6", "row": 0, "col": 0},
                {"title": self.tr("Total Documents"), "preset_id": "ALL", "color": "#10b981", "row": 0, "col": 1},
                {"title": self.tr("Total Invoiced"), "preset_id": "INVOICES", "color": "#f59e0b", "aggregation": "sum", "row": 0, "col": 2},
                {"title": self.tr("Processed"), "preset_id": "PROCESSED", "color": "#6b7280", "row": 0, "col": 3}
            ]

    def save_config(self):
        try:
            with open(self.config_path, "w") as f:
                data = {
                    "cards": self.cards_config,
                    "locked": self.locked
                }
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Error] Failed to save dashboard config: {e}")

    def get_pos_from_cell(self, row, col):
        x = MARGIN + col * (CELL_WIDTH + SPACING)
        y = MARGIN + row * (CELL_HEIGHT + SPACING)
        return QPoint(x, y)

    def get_cell_from_pos(self, pos: QPoint):
        col = (pos.x() - MARGIN + (CELL_WIDTH + SPACING) // 2) // (CELL_WIDTH + SPACING)
        row = (pos.y() - MARGIN + (CELL_HEIGHT + SPACING) // 2) // (CELL_HEIGHT + SPACING)
        return max(0, int(row)), max(0, int(col))

    def refresh_stats(self):
        # Clear existing
        for w in self.card_widgets:
            w.deleteLater()
        self.card_widgets = []
            
        max_row = 3 # Minimum 4 rows
        max_col = 3 # Minimum 4 columns
        
        for index, config in enumerate(self.cards_config):
            row, col = config.get("row", 0), config.get("col", 0)
            max_row = max(max_row, row)
            max_col = max(max_col, col)
            
            # Resolve count and query
            query = None
            count = 0
            agg_type = config.get("aggregation", "count")
            
            title = config.get("title", "Untitled")
            if "preset_id" in config:
                pid = config["preset_id"]
                
                # Dynamic Translation for Presets
                if pid == "NEW":
                    title = self.tr("Inbox")
                elif pid == "PROCESSED":
                    title = self.tr("Processed")
                elif pid == "ALL":
                    title = self.tr("Total Documents")
                elif pid == "INVOICES":
                    title = self.tr("Total Invoiced")

                if self.db_manager:
                    if pid == "NEW":
                        query = {"field": "status", "op": "equals", "value": "NEW"}
                    elif pid == "PROCESSED":
                        query = {"field": "status", "op": "equals", "value": "PROCESSED"}
                    elif pid == "INVOICES":
                        query = {"operator": "AND", "conditions": [{"field": "type_tags", "op": "contains", "value": ["INVOICE"]}]}
                    else:
                        query = {}
                    
                    if agg_type == "sum":
                        count = self.db_manager.sum_documents_advanced(query)
                    else:
                        count = self.db_manager.count_documents_advanced(query)
                else:
                    count = 0
                    query = {}

            elif "filter_id" in config and self.filter_tree:
                node = self.filter_tree.find_node_by_id(config["filter_id"])
                if node:
                    query = node.data
                    if self.db_manager:
                        if agg_type == "sum":
                            count = self.db_manager.sum_documents_advanced(query)
                        else:
                            count = self.db_manager.count_documents_advanced(query)
                    else:
                        count = 0
                else:
                    count = "ERR"
                    query = {}
            
            # Resolve Sparkline Data
            spark_data = []
            if self.db_manager and query is not None:
                # Use days=None for automatic range scaling
                # Counts are typically cumulative growth, sums are activity trends
                is_cumulative = (agg_type == "count")
                spark_data = self.db_manager.get_trend_data_advanced(query, days=None, aggregation=agg_type, cumulative=is_cumulative)

            card = StatCard(
                title, 
                count, 
                config.get("color", "#3b82f6"), 
                query,
                aggregation=agg_type,
                sparkdata=spark_data,
                parent=self.content_widget
            )
            card.filter_id = config.get("filter_id")
            card.preset_id = config.get("preset_id")
            card.edit_requested.connect(lambda idx=index: self._edit_card(idx))
            card.rename_requested.connect(lambda idx=index: self._rename_card(idx))
            card.delete_requested.connect(lambda idx=index: self._delete_card(idx))
            
            # Position
            card.move(self.get_pos_from_cell(row, col))
            card.show()
            self.card_widgets.append(card)

        # Update board size (Minimum 4x4)
        self.content_widget.setFixedSize(
            MARGIN * 2 + (max_col + 1) * (CELL_WIDTH + SPACING),
            MARGIN * 2 + (max_row + 1) * (CELL_HEIGHT + SPACING)
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            actual_card = None
            if isinstance(child, StatCard): actual_card = child
            elif child and isinstance(child.parent(), StatCard): actual_card = child.parent()
                
            if actual_card:
                if self.locked:
                    # In locked mode, click-only navigation
                    payload = {
                        "query": actual_card.filter_query,
                        "filter_id": getattr(actual_card, "filter_id", None),
                        "preset_id": getattr(actual_card, "preset_id", None)
                    }
                    self.navigation_requested.emit(payload)
                    return
                else:
                    # In unlocked mode, start drag
                    self.dragging_widget = actual_card
                    self.drag_start_mouse_pos = event.position().toPoint()
                    self.drag_original_widget_pos = self.dragging_widget.pos()
                    self.drag_has_moved = False
                    self.dragging_widget.raise_()
                    self.dragging_widget.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging_widget:
            delta = event.position().toPoint() - self.drag_start_mouse_pos
            if not self.drag_has_moved and delta.manhattanLength() > 5:
                self.drag_has_moved = True
            
            if self.drag_has_moved:
                new_pos = self.drag_original_widget_pos + delta
                self.dragging_widget.move(new_pos)
                
                # Dynamic Reordering (Preview)
                target_row, target_col = self.get_cell_from_pos(new_pos)
                
                # Check for collision
                self._handle_reorder_preview(target_row, target_col)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.dragging_widget:
            self.dragging_widget.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            if not self.drag_has_moved:
                # It was a click
                self.navigation_requested.emit(self.dragging_widget.filter_query)
            else:
                # Snap to grid
                target_row, target_col = self.get_cell_from_pos(self.dragging_widget.pos())
                
                # Double Check: If we are still overlapping or target is weird, we should have swapped in preview.
                # If for some reason preview missed it, we snap back to the current 'logical' spot.
                logical_config = self.cards_config[self.card_widgets.index(self.dragging_widget)]
                target_row = logical_config["row"]
                target_col = logical_config["col"]
                
                self.dragging_widget.move_animated(self.get_pos_from_cell(target_row, target_col))
                self.save_config()
            
            self.dragging_widget = None
            return
        super().mouseReleaseEvent(event)

    def _handle_reorder_preview(self, target_row, target_col):
        """If someone is at target, move them temporarily to free spot or swap."""
        drag_idx = self.card_widgets.index(self.dragging_widget)
        
        # Current logical state of dragged card
        orig_row = self.cards_config[drag_idx]["row"]
        orig_col = self.cards_config[drag_idx]["col"]

        if orig_row == target_row and orig_col == target_col:
            return

        # Check against ALL other cards for collision
        target_widget_idx = -1
        for i, config in enumerate(self.cards_config):
            if i != drag_idx and config["row"] == target_row and config["col"] == target_col:
                target_widget_idx = i
                break
        
        if target_widget_idx != -1:
            # Collision! Swap the target card to my old spot
            self.cards_config[target_widget_idx]["row"] = orig_row
            self.cards_config[target_widget_idx]["col"] = orig_col
            self.card_widgets[target_widget_idx].move_animated(self.get_pos_from_cell(orig_row, orig_col))
            
        # Update dragged card logical data to target spot
        self.cards_config[drag_idx]["row"] = target_row
        self.cards_config[drag_idx]["col"] = target_col
        
        # Update board size if we moved to a new edge
        max_row = max(3, max(c["row"] for c in self.cards_config))
        max_col = max(3, max(c["col"] for c in self.cards_config))
        self.content_widget.setFixedSize(
            MARGIN * 2 + (max_col + 1) * (CELL_WIDTH + SPACING),
            MARGIN * 2 + (max_row + 1) * (CELL_HEIGHT + SPACING)
        )


    def _show_dashboard_menu(self, pos):
        menu = QMenu(self)
        
        lock_text = self.tr("Unlock Layout (Enable Dragging)") if self.locked else self.tr("Lock Layout (Prevent Dragging)")
        lock_action = menu.addAction(lock_text)
        lock_action.triggered.connect(self._toggle_lock)
        
        menu.addSeparator()
        
        add_action = menu.addAction(self.tr("Add New Filter View..."))
        add_action.triggered.connect(self._add_new_card)
        menu.exec(self.content_widget.mapToGlobal(pos))

    def _toggle_lock(self):
        self.locked = not self.locked
        self.save_config()

    def _add_new_card(self):
        if not self.filter_tree: return
        dlg = DashboardEntryDialog(self.filter_tree, self)
        if dlg.exec():
            data = dlg.get_data()
            # Find next free spot? Or just append at end.
            self.cards_config.append(data)
            self.save_config()
            self.refresh_stats()

    def _edit_card(self, index):
        if index >= len(self.cards_config): return
        dlg = DashboardEntryDialog(self.filter_tree, self, self.cards_config[index])
        if dlg.exec():
            self.cards_config[index] = dlg.get_data()
            self.save_config()
            self.refresh_stats()

    def _delete_card(self, index):
        if index >= len(self.cards_config): return
        self.cards_config.pop(index)
        self.save_config()
        self.refresh_stats()

    def _rename_card(self, index):
        if index >= len(self.cards_config): return
        old_title = self.cards_config[index].get("title", "")
        new_title, ok = QInputDialog.getText(self, self.tr("Rename View"), self.tr("New Title:"), text=old_title)
        if ok and new_title:
            self.cards_config[index]["title"] = new_title
            self.save_config()
            self.refresh_stats()
