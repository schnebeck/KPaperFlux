import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QFrame, QScrollArea, QComboBox, QSizePolicy,
                             QMenu)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QSize, QCoreApplication
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QAction, QBrush

from core.reporting import ReportGenerator, ReportRegistry
from core.models.reporting import ReportDefinition
from gui.report_editor import ReportEditorWidget

from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush
import math

class ChartWidget(QWidget):
    """Base class for interactive charts."""
    segment_clicked = pyqtSignal(str) # Emits the label of the clicked segment/bar

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels = []
        self.series = []
        self.colors = [QColor("#3498db"), QColor("#e67e22"), QColor("#2ecc71"), QColor("#9b59b6"), 
                       QColor("#f1c40f"), QColor("#e74c3c"), QColor("#1abc9c"), QColor("#d35400")]
        self.setMinimumHeight(500)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, labels: List[str], series: List[Dict[str, Any]]):
        self.labels = labels
        self.series = series
        self.update()
        
    def format_axis_val(self, val, series_name=""):
        suffix = ""
        # Improved heuristic for currency
        sn = series_name.lower()
        if any(term in sn for term in ["amount", "tax", "price", "sum", "avg"]) and "count" not in sn:
            suffix = " €"
            
        if abs(val) >= 1000000:
            return f"{val/1000000:.1f}M{suffix}"
        if abs(val) >= 1000:
            return f"{val/1000:.1f}k{suffix}"
        
        if val == int(val):
            return f"{int(val)}{suffix}"
        return f"{val:.1f}{suffix}"

class BarChartWidget(ChartWidget):
    """Interactive Bar Chart with drill-down support."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bar_rects = [] # Store rects for hit testing

    def paintEvent(self, event):
        if not self.series or not self.labels: return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        self.bar_rects = []
        w, h = self.width(), self.height()
        m_l, m_r, m_t, m_b = 60, 20, 20, 80
        c_w, c_h = w - m_l - m_r, h - m_t - m_b

        all_vals = []
        for s in self.series: all_vals.extend(s["data"])
        max_v = max(all_vals) if all_vals else 1
        axis_max = max_v * 1.1

        b_count = len(self.labels)
        s_count = len(self.series)
        g_spacing = 15
        g_width = (c_w - (b_count - 1) * g_spacing) / b_count
        b_width = g_width / s_count

        # X/Y Axis
        painter.setPen(QPen(QColor("#bdc3c7"), 1))
        painter.drawLine(m_l, h-m_b, w-m_r, h-m_b)
        painter.drawLine(m_l, m_t, m_l, h-m_b)

        # Y-Axis Labels & Ticks
        painter.setPen(QColor("#7f8c8d"))
        painter.setFont(QFont("Sans Serif", 8))
        s_name = self.series[0]["name"] if self.series else ""
        for i in range(5):
            val_y = axis_max * (i / 4)
            py = h - m_b - (val_y / axis_max) * c_h
            lbl = self.format_axis_val(val_y, s_name)
            painter.drawText(0, int(py)-10, m_l-8, 20, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, lbl)
            painter.drawLine(m_l - 4, int(py), m_l, int(py))

        for i, label in enumerate(self.labels):
            g_x = m_l + i * (g_width + g_spacing)
            
            # Sub-bar calculation with capping for better proportions
            actual_b_width = g_width / s_count
            display_b_width = min(actual_b_width, 80) if s_count == 1 else actual_b_width
            b_center_offset = (actual_b_width - display_b_width) / 2

            for s_idx, s in enumerate(self.series):
                val = s["data"][i]
                b_h = (val / axis_max) * c_h
                bx = g_x + s_idx * actual_b_width + b_center_offset
                by = h - m_b - b_h
                rect = QRect(int(bx), int(by), int(display_b_width), int(b_h))
                self.bar_rects.append((rect, label))
                
                painter.setBrush(self.colors[s_idx % len(self.colors)])
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(rect)
            
            # Label (Rotated 45 degrees) - Centered under the group
            lx = g_x + g_width / 2
            ly = h - m_b + 5
            painter.save()
            painter.translate(lx, ly)
            painter.rotate(-45)
            painter.setPen(QColor("#2c3e50"))
            painter.setFont(QFont("Sans Serif", 7))
            painter.drawText(QRect(-100, 0, 100, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
            painter.restore()

    def mousePressEvent(self, event):
        for rect, label in self.bar_rects:
            if rect.contains(event.pos()):
                self.segment_clicked.emit(label)
                break

class PieChartWidget(ChartWidget):
    """Interactive Pie Chart for 100% distribution view."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.slice_paths = []

    def paintEvent(self, event):
        if not self.labels or not self.series: return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. Expanded Color & Pattern Palette
        base_colors = [
            QColor("#2980b9"), QColor("#e67e22"), QColor("#27ae60"), QColor("#8e44ad"), 
            QColor("#f1c40f"), QColor("#e74c3c"), QColor("#1abc9c"), QColor("#d35400"),
            QColor("#3498db"), QColor("#c0392b"), QColor("#16a085"), QColor("#2ecc71"),
            QColor("#9b59b6"), QColor("#f39c12"), QColor("#7f8c8d"), QColor("#1f3a93"),
            QColor("#6741d9"), QColor("#087f5b"), QColor("#b91c1c"), QColor("#4338ca")
        ]
        
        # 2. Prepare & Sort Data
        raw_data = self.series[0]["data"]
        total = sum(raw_data)
        if total == 0: return

        items = []
        for i in range(len(raw_data)):
            # Assign color and optional pattern
            color = base_colors[i % len(base_colors)]
            brush = QBrush(color)
            if i >= len(base_colors):
                # Add pattern for overflow colors
                brush.setStyle(Qt.BrushStyle.Dense6Pattern)
            
            items.append({
                "label": self.labels[i], 
                "val": raw_data[i], 
                "brush": brush,
                "color": color
            })
        
        items.sort(key=lambda x: x["val"], reverse=True)

        # Group "Others": Top 12 stay, rest goes to Others
        max_legend = 12
        final_items = items[:max_legend]
        others_val = sum(item["val"] for item in items[max_legend:])
        
        if others_val > 0:
            final_items.append({
                "label": self.tr("Others"), 
                "val": others_val, 
                "brush": QBrush(QColor("#95a5a6")),
                "color": QColor("#95a5a6")
            })

        # 3. Layout Constants
        w, h = self.width(), self.height()
        legend_w = 250
        chart_w = w - legend_w
        cx, cy = chart_w // 2 + 30, h // 2
        radius = min(chart_w // 2, h // 2) - 70
        rect = QRect(cx - radius, cy - radius, radius * 2, radius * 2)

        self.slice_paths = []
        start_angle = 90 * 16
        metrics = painter.fontMetrics()
        
        # 4. Draw Slices
        for i, item in enumerate(final_items):
            span_angle = int((item["val"] / total) * 360 * 16)
            painter.setBrush(item["brush"])
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            painter.drawPie(rect, start_angle, span_angle)
            
            # Label only for significant slices (> 8%)
            if item["val"] / total > 0.08:
                mid_angle = math.radians((start_angle + span_angle / 2) / 16.0)
                lx = cx + (radius + 15) * math.cos(mid_angle)
                ly = cy - (radius + 15) * math.sin(mid_angle)
                
                # Use elided text for chart labels too if needed
                perc_text = f"({item['val']/total*100:.1f}%)"
                painter.setPen(QColor("#2c3e50"))
                painter.setFont(QFont("Sans Serif", 7, QFont.Weight.Bold))
                
                h_align = Qt.AlignmentFlag.AlignCenter
                cos_a = math.cos(mid_angle)
                if cos_a > 0.3: h_align = Qt.AlignmentFlag.AlignLeft
                elif cos_a < -0.3: h_align = Qt.AlignmentFlag.AlignRight
                
                painter.drawText(int(lx)-60, int(ly)-10, 120, 20, h_align, perc_text)
            
            self.slice_paths.append((start_angle, span_angle, item["label"]))
            start_angle += span_angle

        # 5. Draw Legend (Right Side)
        legend_x = chart_w + 15
        legend_y = max(40, cy - (len(final_items) * 22) // 2)
        painter.setFont(QFont("Sans Serif", 8))
        
        for i, item in enumerate(final_items):
            # Color Box
            painter.setBrush(item["brush"])
            painter.setPen(QPen(QColor("#cbd5e1"), 1))
            painter.drawRect(legend_x, legend_y, 14, 14)
            
            # Label with proper elision (clip only at the end)
            painter.setPen(QColor("#334155"))
            perc = (item["val"] / total) * 100
            perc_str = f"({perc:.1f}%)"
            
            # Calculate space for label
            avail_w = legend_w - 70 
            elided_label = metrics.elidedText(item["label"], Qt.TextElideMode.ElideRight, avail_w)
            
            painter.drawText(legend_x + 22, legend_y + 12, avail_w, 20, Qt.AlignmentFlag.AlignLeft, elided_label)
            # Draw percentage separately on the right of the label area for alignment
            painter.drawText(legend_x + 22 + avail_w, legend_y + 12, 45, 20, Qt.AlignmentFlag.AlignRight, perc_str)
            
            legend_y += 22

    def mousePressEvent(self, event):
        w = self.width()
        legend_w = 250
        chart_w = w - legend_w
        cx, cy = chart_w // 2 + 30, self.height() // 2
        
        dx, dy = event.pos().x() - cx, cy - event.pos().y()
        dist = math.sqrt(dx*dx + dy*dy)
        radius = min(chart_w // 2, self.height() // 2) - 70
        
        if dist <= radius:
            angle = math.degrees(math.atan2(dy, dx))
            if angle < 0: angle += 360
            
            for start, span, label in self.slice_paths:
                s = (start // 16) % 360
                sp = span // 16
                a = angle
                if (s <= a < s + sp) or (s <= a + 360 < s + sp):
                     self.segment_clicked.emit(label)
                     break

class LineChartWidget(ChartWidget):
    """Line Chart for trend and delta analysis."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.point_rects = []

    def paintEvent(self, event):
        if not self.labels or not self.series: return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        self.point_rects = []
        w, h = self.width(), self.height()
        m_l, m_r, m_t, m_b = 60, 20, 20, 80
        c_w, c_h = w - m_l - m_r, h - m_t - m_b

        all_vals = []
        for s in self.series: all_vals.extend(s["data"])
        max_v = max(all_vals) if all_vals else 1
        min_v = min(all_vals) if all_vals else 0
        v_range = (max_v - min_v) if max_v != min_v else 1
        axis_max = max_v + v_range * 0.1
        axis_min = min_v - v_range * 0.1

        x_spacing = c_w / (len(self.labels) - 1) if len(self.labels) > 1 else c_w

        # Grid and Axis
        painter.setPen(QPen(QColor("#ecf0f1"), 1))
        s_name = self.series[0]["name"] if self.series else ""
        
        for i in range(5):
            y = m_t + (4 - i) * (c_h / 4)
            painter.drawLine(m_l, int(y), w-m_r, int(y))
            
            # Y Labels
            val_y = axis_min + (i / 4) * (axis_max - axis_min)
            painter.setPen(QColor("#7f8c8d"))
            painter.setFont(QFont("Sans Serif", 8))
            lbl = self.format_axis_val(val_y, s_name)
            painter.drawText(0, int(y)-10, m_l-8, 20, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, lbl)
            painter.setPen(QPen(QColor("#ecf0f1"), 1))

        for s_idx, s in enumerate(self.series):
            color = self.colors[s_idx % len(self.colors)]
            painter.setPen(QPen(color, 2))
            
            points = []
            for i, val in enumerate(s["data"]):
                px = m_l + i * x_spacing
                py = h - m_b - ((val - axis_min) / (axis_max - axis_min)) * c_h
                points.append((px, py, val, self.labels[i]))
            
            # Draw lines
            for i in range(len(points) - 1):
                painter.drawLine(int(points[i][0]), int(points[i][1]), int(points[i+1][0]), int(points[i+1][1]))
            
            # Draw points
            for px, py, val, label in points:
                painter.setBrush(color)
                painter.drawEllipse(int(px)-4, int(py)-4, 8, 8)
                self.point_rects.append((QRect(int(px)-10, int(py)-10, 20, 20), label))

        # Labels (Rotated 45 degrees)
        painter.setFont(QFont("Sans Serif", 7))
        for i, label in enumerate(self.labels):
            lx = m_l + i * x_spacing
            ly = h - m_b + 5
            
            painter.save()
            painter.translate(lx, ly)
            painter.rotate(-45)
            painter.setPen(QColor("#2c3e50"))
            painter.drawText(QRect(-100, 0, 100, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
            painter.restore()

    def mousePressEvent(self, event):
        for rect, label in self.point_rects:
            if rect.contains(event.pos()):
                self.segment_clicked.emit(label)
                break

class ReportingWidget(QWidget):
    """Deep-dive reporting tab with interactive report builder."""
    filter_requested = pyqtSignal(dict) # Signals to MainWindow to focus list and filter
    
    def __init__(self, db_manager, filter_tree=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.filter_tree = filter_tree
        self.repo_gen = ReportGenerator()
        self.registry = ReportRegistry()
        self.report_dir = "resources/reports"
        self.current_definition = None
        self.zoom_level = 1.0
        self.active_charts = []
        self.init_ui()
        self.load_available_reports()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel(self.tr("Select Report:")))
        
        self.combo_reports = QComboBox()
        self.combo_reports.setMinimumWidth(250)
        self.combo_reports.currentIndexChanged.connect(self.refresh_data)
        toolbar.addWidget(self.combo_reports)
        
        self.btn_edit = QPushButton("⚙️ " + self.tr("Edit Definition"))
        self.btn_edit.clicked.connect(self.open_editor)
        toolbar.addWidget(self.btn_edit)
        
        self.btn_new = QPushButton("✚ " + self.tr("New Report"))
        self.btn_new.clicked.connect(self.create_new_report)
        toolbar.addWidget(self.btn_new)

        toolbar.addStretch()

        # Global Zoom Controls
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setFixedSize(30, 30)
        self.btn_zoom_out.clicked.connect(lambda: self.set_global_zoom(self.zoom_level - 0.2))
        
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setFixedWidth(40)
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setFixedSize(30, 30)
        self.btn_zoom_in.clicked.connect(lambda: self.set_global_zoom(self.zoom_level + 0.2))

        self.btn_fit = QPushButton(self.tr("Fit"))
        self.btn_fit.setFixedSize(50, 30)
        self.btn_fit.clicked.connect(lambda: self.set_global_zoom(1.0))

        toolbar.addWidget(self.btn_zoom_out)
        toolbar.addWidget(self.lbl_zoom)
        toolbar.addWidget(self.btn_zoom_in)
        toolbar.addWidget(self.btn_fit)
        
        toolbar.addSpacing(10)
        
        self.btn_export = QPushButton("📤 " + self.tr("Export Data"))
        self.btn_export.setStyleSheet("background-color: #1b5e20; color: white; font-weight: bold; padding: 4px 12px;")
        
        # Add Export Menu
        export_menu = QMenu(self)
        
        act_csv = QAction("📊 " + self.tr("Export as CSV (Data)"), self)
        act_csv.triggered.connect(lambda: self.export_as("csv"))
        
        act_pdf = QAction("📄 " + self.tr("Export as PDF (Report)"), self)
        act_pdf.triggered.connect(lambda: self.export_as("pdf"))
        
        act_zip = QAction("📦 " + self.tr("Export as ZIP (Documents)"), self)
        act_zip.triggered.connect(lambda: self.export_as("zip"))
        
        export_menu.addAction(act_csv)
        export_menu.addAction(act_pdf)
        export_menu.addSeparator()
        export_menu.addAction(act_zip)
        
        self.btn_export.setMenu(export_menu)
        toolbar.addWidget(self.btn_export)
        
        self.main_layout.addLayout(toolbar)

        # Main Content area (Scrollable)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.scroll.setWidget(self.content_widget)
        self.main_layout.addWidget(self.scroll)

        # Result Placeholder
        self.clear_results()

    def load_available_reports(self):
        self._lock_refreshes = True
        self.registry.load_from_directory(self.report_dir)
        self.combo_reports.clear()
        self.combo_reports.addItem("--- Select a Report ---", None)
        
        for r in self.registry.list_reports():
            self.combo_reports.addItem(self.tr(r.name), r.id)
        
        self._lock_refreshes = False

    def clear_results(self):
        self.active_charts = []
        for i in reversed(range(self.content_layout.count())): 
            item = self.content_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
                # Recursively clear layouts (like charts_row)
                self._clear_layout(item.layout())
        
        placeholder = QLabel(self.tr("Please select a report to display data."))
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #999; font-size: 14pt; margin-top: 100px;")
        self.content_layout.addWidget(placeholder)
        self.set_global_zoom(1.0)

    def _clear_layout(self, layout):
        if not layout: return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
                self._clear_layout(item.layout())

    def refresh_data(self):
        if getattr(self, "_lock_refreshes", False): return
        
        report_id = self.combo_reports.currentData()
        if not report_id:
            self.clear_results()
            return
            
        definition = self.registry.get_report(report_id)
        if not definition: return
        self.current_definition = definition
        
        # Execute report via engine
        results = self.repo_gen.run_custom_report(self.db_manager, definition)
        self.render_report(results, definition)

    def render_report(self, results, definition: ReportDefinition):
        # Clear previous
        for i in reversed(range(self.content_layout.count())): 
            widget = self.content_layout.itemAt(i).widget()
            if widget: widget.setParent(None)
            
        # Title & Info
        title_lbl = QLabel(self.tr(results["title"]))
        title_lbl.setStyleSheet("font-size: 18pt; font-weight: bold; color: #2c3e50;")
        self.content_layout.addWidget(title_lbl)
        
        if definition.description:
            desc_lbl = QLabel(self.tr(definition.description))
            desc_lbl.setStyleSheet("color: #7f8c8d; font-style: italic;")
            self.content_layout.addWidget(desc_lbl)

        # Charts Section
        charts_row = QHBoxLayout()
        self.active_charts = []
        
        report_name = QCoreApplication.translate("ReportingWidget", results["title"])
        
        if "bar_chart" in definition.visualizations:
            chart = BarChartWidget()
            chart.set_data(results["labels"], results["series"])
            chart.segment_clicked.connect(self._on_chart_drill_down)
            self.active_charts.append(chart)
            charts_row.addWidget(self._wrap_chart(chart, report_name))

        if "pie_chart" in definition.visualizations:
            chart = PieChartWidget()
            chart.set_data(results["labels"], results["series"])
            chart.segment_clicked.connect(self._on_chart_drill_down)
            self.active_charts.append(chart)
            charts_row.addWidget(self._wrap_chart(chart, report_name))

        if "line_chart" in definition.visualizations or "trend_chart" in definition.visualizations:
            chart = LineChartWidget()
            chart.set_data(results["labels"], results["series"])
            chart.segment_clicked.connect(self._on_chart_drill_down)
            self.active_charts.append(chart)
            charts_row.addWidget(self._wrap_chart(chart, report_name))

        if charts_row.count() > 0:
            self.content_layout.addLayout(charts_row)
        
        self.apply_zoom_visuals()

        # Table Section
        if "table" in definition.visualizations:
            self.content_layout.addWidget(QLabel("<b>Detailed Data:</b>"))
            table = QTableWidget()
            if results["table_rows"]:
                headers = list(results["table_rows"][0].keys())
                table.setColumnCount(len(headers))
                table.setHorizontalHeaderLabels(headers)
                table.setRowCount(len(results["table_rows"]))
                
                for r_idx, row in enumerate(results["table_rows"]):
                    for c_idx, col in enumerate(headers):
                        val = row[col]
                        txt = f"{val:,.2f}" if isinstance(val, (float, int)) and "count" not in col.lower() else str(val)
                        table.setItem(r_idx, c_idx, QTableWidgetItem(txt))
                
                table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                table.setMinimumHeight(300)
                table.setStyleSheet("background: white; border: 1px solid #ddd; border-radius: 4px;")
                self.content_layout.addWidget(table)
            else:
                self.content_layout.addWidget(QLabel(self.tr("No data for this criteria.")))

        self.content_layout.addStretch()

    def _wrap_chart(self, chart, title):
        frame = QFrame()
        frame.setObjectName("ChartCard")
        frame.setStyleSheet("""
            QFrame#ChartCard { 
                background: white; border: 1px solid #e2e8f0; border-radius: 12px; 
            }
        """)
        ly = QVBoxLayout(frame)
        ly.setContentsMargins(15, 12, 15, 12)
        ly.addWidget(QLabel(f"<span style='color: #475569; font-weight: bold;'>{title}</span>"))
        ly.addWidget(chart)
        return frame

    def set_global_zoom(self, level):
        self.zoom_level = max(0.5, min(3.0, level))
        self.lbl_zoom.setText(f"{self.zoom_level:.0%}")
        self.apply_zoom_visuals()

    def apply_zoom_visuals(self):
        """Scales the content area and charts."""
        # Scale chart heights
        chart_h = int(500 * self.zoom_level)
        for chart in self.active_charts:
            chart.setFixedHeight(chart_h)
            
        # Scaling the width for all zoom levels
        base_w = self.scroll.viewport().width() - 40
        if base_w < 100: base_w = 800
        
        target_w = int(base_w * self.zoom_level)
        
        if self.zoom_level > 1.0:
            # For zooming in: force expansion to enable horizontal scrolling
            self.content_widget.setMinimumWidth(target_w)
            self.content_widget.setMaximumWidth(target_w) 
        else:
            # For zooming out: force shrinking and center it
            self.content_widget.setFixedWidth(target_w)
            self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
        self.content_widget.update()

    def _on_chart_drill_down(self, label):
        """Builds a filter based on the clicked chart element and sends it to MainWindow."""
        if not self.current_definition: return
        
        # Base filter from report
        query = self.current_definition.filter_query or {"operator": "AND", "conditions": []}
        
        drill_cond = None
        group_field = self.current_definition.group_by
        
        if group_field:
            if group_field == "doc_date:month":
                # label is YYYY-MM
                drill_cond = {"field": "doc_date", "op": "between", "value": f"{label}-01,{label}-31"}
            elif group_field == "doc_date:year":
                drill_cond = {"field": "doc_date", "op": "between", "value": f"{label}-01-01,{label}-12-31"}
            elif group_field == "sender":
                drill_cond = {"field": "sender", "op": "equals", "value": label}
            elif group_field == "type":
                drill_cond = {"field": "classification", "op": "equals", "value": label}
            elif group_field.startswith("amount:"):
                # label is "min - max"
                try:
                    p = label.split(" - ")
                    drill_cond = {"field": "amount", "op": "between", "value": f"{p[0]},{p[1]}"}
                except: pass
            else:
                drill_cond = {"field": group_field, "op": "equals", "value": label}

        if drill_cond:
            # Add to current query
            new_query = {"operator": "AND", "conditions": [query, drill_cond]}
            self.filter_requested.emit(new_query)

    def open_editor(self):
        report_id = self.combo_reports.currentData()
        if not report_id: return
        
        definition = self.registry.get_report(report_id)
        if not definition: return
        
        from PyQt6.QtWidgets import QDialog
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Edit Report Definition"))
        dlg.setMinimumSize(800, 700)
        ly = QVBoxLayout(dlg)
        
        editor = ReportEditorWidget(db_manager=self.db_manager, filter_tree=self.filter_tree)
        editor.load_report(definition)
        ly.addWidget(editor)
        
        editor.btn_save.clicked.connect(lambda: [dlg.accept(), self.load_available_reports(), self.refresh_data()])
        dlg.exec()

    def create_new_report(self):
        from PyQt6.QtWidgets import QDialog, QInputDialog
        name, ok = QInputDialog.getText(self, self.tr("New Report"), self.tr("Enter report name:"))
        if ok and name:
            import time
            report_id = f"custom_{int(time.time())}"
            new_def = ReportDefinition(id=report_id, name=name, visualizations=["table", "bar_chart"])
            
            # Show editor
            dlg = QDialog(self)
            dlg.setWindowTitle(self.tr("Create Report Definition"))
            dlg.setMinimumSize(800, 700)
            ly = QVBoxLayout(dlg)
            editor = ReportEditorWidget(db_manager=self.db_manager, filter_tree=self.filter_tree)
            editor.load_report(new_def)
            ly.addWidget(editor)
            
            editor.btn_save.clicked.connect(lambda: [dlg.accept(), self.load_available_reports()])
            dlg.exec()

    def export_as(self, fmt):
        report_id = self.combo_reports.currentData()
        if not report_id: return
        
        definition = self.registry.get_report(report_id)
        if not definition: return
        
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        
        # Get actual documents matching the report filter
        docs = self.db_manager.search_documents_advanced(definition.filter_query)
        if not docs:
            QMessageBox.information(self, self.tr("Export"), self.tr("No documents found for this report."))
            return

        if fmt == "csv":
            csv_data = self.repo_gen.export_to_csv(docs)
            path, _ = QFileDialog.getSaveFileName(self, self.tr("Export CSV"), f"{definition.name}_Export.csv", "CSV Files (*.csv)")
            if path:
                with open(path, "wb") as f: f.write(csv_data)
                
        elif fmt == "pdf":
            # This would normally use a PDF generator like ReportLab or a Headless Browser
            QMessageBox.information(self, self.tr("Export PDF"), self.tr("PDF Report Generation is being initialized. This will export the charts and tables into a finished layout."))
            
        elif fmt == "zip":
            path, _ = QFileDialog.getSaveFileName(self, self.tr("Export ZIP"), f"{definition.name}_Documents.zip", "ZIP Files (*.zip)")
            if path:
                import zipfile
                try:
                    with zipfile.ZipFile(path, 'w') as zip_f:
                        for doc in docs:
                            if os.path.exists(doc.path):
                                # Add file to zip, using its display name
                                arcname = os.path.basename(doc.path)
                                zip_f.write(doc.path, arcname)
                    QMessageBox.information(self, self.tr("Export ZIP"), self.tr("Successfully created ZIP archive with %d documents.") % len(docs))
                except Exception as e:
                    QMessageBox.critical(self, self.tr("Error"), f"Failed to create ZIP: {str(e)}")
