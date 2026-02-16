from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QFrame, QScrollArea, QComboBox, QSizePolicy,
                             QMenu, QTextEdit, QToolButton, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QSize, QCoreApplication, QTimer, QThread
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QAction, QBrush, QIcon

from core.reporting import ReportGenerator, ReportRegistry
from core.models.reporting import ReportDefinition, ReportComponent
from core.exporters.pdf_report import PdfReportGenerator
from gui.report_editor import ReportEditorWidget

from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush
import math
import os

class ReportWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, repo_gen, db_manager, definition):
        super().__init__()
        self.repo_gen = repo_gen
        self.db_manager = db_manager
        self.definition = definition

    def run(self):
        try:
            results = self.repo_gen.run_custom_report(self.db_manager, self.definition)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

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
        line_height = 22
        # Vertically center the entire legend block
        legend_y = max(40, cy - (len(final_items) * line_height) // 2)
        painter.setFont(QFont("Sans Serif", 8))
        
        for i, item in enumerate(final_items):
            # Color Box (14x14) - vertically centered in line_height
            box_y = legend_y + (line_height - 14) // 2
            painter.setBrush(item["brush"])
            painter.setPen(QPen(QColor("#cbd5e1"), 1))
            painter.drawRect(legend_x, box_y, 14, 14)
            
            # Label with proper elision and vertical centering
            painter.setPen(QColor("#334155"))
            perc = (item["val"] / total) * 100
            perc_str = f"({perc:.1f}%)"
            
            # Calculate space for label
            avail_w = legend_w - 85 # More space for percentages
            elided_label = metrics.elidedText(item["label"], Qt.TextElideMode.ElideRight, avail_w)
            
            # Text alignment: use a rect covering full line height for perfect vertical centering
            text_rect = QRect(legend_x + 22, legend_y, avail_w, line_height)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_label)
            
            # Draw percentage separately on the right with same vertical centering
            perc_rect = QRect(legend_x + 22 + avail_w, legend_y, 55, line_height)
            painter.drawText(perc_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, perc_str)
            
            legend_y += line_height

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
        self.active_definitions = []
        self.pending_workers = [] # Keep references to threads
        self.setAcceptDrops(True)
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

        self.btn_comment = QPushButton("💬 " + self.tr("Add Comment"))
        self.btn_comment.setToolTip(self.tr("Add a text block to the current report"))
        self.btn_comment.clicked.connect(self.add_text_block)
        toolbar.addWidget(self.btn_comment)
        
        self.btn_new = QPushButton("✚ " + self.tr("New Report"))
        self.btn_new.setToolTip(self.tr("Create a new report"))
        self.btn_new.clicked.connect(self.create_new_report)
        toolbar.addWidget(self.btn_new)

        self.btn_import = QPushButton("📥 " + self.tr("Import from PDF"))
        self.btn_import.setToolTip(self.tr("Import report style from an exported PDF file"))
        self.btn_import.clicked.connect(self.import_report_from_file)
        toolbar.addWidget(self.btn_import)

        self.btn_clear = QPushButton("🗑️ " + self.tr("Clear"))
        self.btn_clear.clicked.connect(self.clear_results)
        toolbar.addWidget(self.btn_clear)

        toolbar.addSpacing(20)

        self.btn_save_layout = QPushButton("💾 " + self.tr("Save Layout"))
        self.btn_save_layout.setToolTip(self.tr("Save the current canvas arrangement"))
        self.btn_save_layout.clicked.connect(self.save_layout)
        toolbar.addWidget(self.btn_save_layout)

        self.btn_load_layout = QPushButton("📂 " + self.tr("Load Layout"))
        self.btn_load_layout.setToolTip(self.tr("Load a saved canvas arrangement"))
        self.btn_load_layout.clicked.connect(self.load_layout)
        toolbar.addWidget(self.btn_load_layout)

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
        
        self.btn_add_text = QPushButton("📝 " + self.tr("Add Comment"))
        self.btn_add_text.clicked.connect(self.add_text_block)
        toolbar.addWidget(self.btn_add_text)
        
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

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        from core.exchange import ExchangeService
        urls = event.mimeData().urls()
        if not urls:
            return

        imported_reports = 0
        layouts_loaded = 0

        for url in urls:
            path = url.toLocalFile()
            if not os.path.exists(path):
                continue

            payload = ExchangeService.load_from_file(path)
            if not payload:
                continue

            if payload.type == "report_definition":
                # For a fresh drop, common expectation is to see ONLY this report
                self.clear_results()
                
                # 1. Import to library
                if self._save_report_definition(payload.payload):
                    imported_reports += 1
                
                # 2. ALSO run/show it immediately
                try:
                    from core.reporting import ReportDefinition
                    definition = ReportDefinition(**payload.payload)
                    
                    # Ensure it's in the combo box so Export works
                    idx = self.combo_reports.findData(definition.id)
                    if idx >= 0:
                        self.combo_reports.setCurrentIndex(idx)
                    else:
                        self.load_available_reports()
                        idx = self.combo_reports.findData(definition.id)
                        if idx >= 0:
                            self.combo_reports.setCurrentIndex(idx)

                    self._generate_report_for_definition(definition)
                    # Scroll to top to ensure it's visible
                    self.scroll.verticalScrollBar().setValue(0)
                except Exception as e:
                    print(f"Failed to auto-run dropped report: {e}")

            elif payload.type == "layout":
                self.clear_results()
                reports = payload.payload.get("reports", [])
                from core.reporting import ReportDefinition
                for r_data in reports:
                    try:
                        definition = ReportDefinition(**r_data)
                        self._generate_report_for_definition(definition)
                    except Exception as e:
                        print(f"Failed to load report from dropped layout: {e}")
                layouts_loaded += 1
                self.scroll.verticalScrollBar().setValue(0)

        if imported_reports > 0 or layouts_loaded > 0:
            self.load_available_reports()
            from gui.utils import show_notification
            msg = []
            if imported_reports > 0:
                msg.append(self.tr("Report style imported and displayed."))
            if layouts_loaded > 0:
                msg.append(self.tr("Layout loaded."))
            
            show_notification(self, self.tr("Import Successful"), " ".join(msg))

    def import_report_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Import Report Style"), "", "PDF Files (*.pdf)")
        if path:
            if self._import_from_pdf(path):
                self.load_available_reports()
                show_selectable_message_box(
                    self, 
                    self.tr("Import Successful"), 
                    self.tr("The report style was successfully imported and added to your library."),
                    icon=QMessageBox.Icon.Information
                )
            else:
                from gui.utils import show_selectable_message_box
                from PyQt6.QtWidgets import QMessageBox
                show_selectable_message_box(
                    self, 
                    self.tr("Import Failed"), 
                    self.tr("Could not find an embedded report configuration in this PDF."),
                    icon=QMessageBox.Icon.Warning
                )

    def _import_from_pdf(self, path) -> bool:
        """Extracts report definition from PDF via ExchangeService."""
        from core.exchange import ExchangeService
        payload = ExchangeService.extract_from_pdf(path)
        if payload and payload.type == "report_definition":
            return self._save_report_definition(payload.payload)
        return False

    def _save_report_definition(self, config: Dict[str, Any]) -> bool:
        """Saves a report definition dictionary to the local report directory."""
        import json
        # Ensure custom ID to avoid overwriting defaults
        rid = config.get("id", "imported")
        if rid.startswith("default_"):
            rid = rid.replace("default_", "custom_")
            config["id"] = rid
                        
        out_path = os.path.join(self.report_dir, f"{rid}.json")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(config, indent=2))
            return True
        except Exception as e:
            print(f"Failed to save report definition: {e}")
            return False

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
        self.active_definitions = []
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
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
            return
            
        definition = self.registry.get_report(report_id)
        if not definition: return
        self.current_definition = definition # Track the last selected for Editor
        
        self._generate_report_for_definition(definition)

    def _generate_report_for_definition(self, definition: ReportDefinition):
        """Asynchronously triggers report generation for a given definition."""
        # UI Feedback
        self.setCursor(Qt.CursorShape.WaitCursor)
        self.combo_reports.setEnabled(False)

        # Execute report via background worker
        if definition not in self.active_definitions:
            self.active_definitions.append(definition)
            
        worker = ReportWorker(self.repo_gen, self.db_manager, definition)
        worker.finished.connect(lambda res, d=definition, w=worker: self._on_report_finished(res, d, w))
        worker.error.connect(lambda err, w=worker: self._on_report_error(err, w))
        self.pending_workers.append(worker)
        worker.start()

    def _on_report_finished(self, results, definition, worker):
        if worker in self.pending_workers:
            self.pending_workers.remove(worker)
        
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.combo_reports.setEnabled(True)
        # Remove placeholder if it's there
        if self.content_layout.count() > 0:
            item = self.content_layout.itemAt(0)
            if item.widget() and isinstance(item.widget(), QLabel) and item.widget().text().startswith(self.tr("Please select")):
                item.widget().setParent(None)
                
        self.render_report(results, definition)

    def _on_report_error(self, error_msg, worker):
        if worker in self.pending_workers:
            self.pending_workers.remove(worker)
        
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.combo_reports.setEnabled(True)
        from gui.utils import show_selectable_message_box
        from PyQt6.QtWidgets import QMessageBox
        show_selectable_message_box(self, self.tr("Report Error"), f"{self.tr('Failed to generate report')}:\n{error_msg}", icon=QMessageBox.Icon.Critical)

    def render_report(self, results, definition: ReportDefinition, clear_active_charts=False):
        # 0. Strip the bottom stretch if exists
        self.strip_bottom_stretch()
        
        if clear_active_charts:
            self.active_charts = []
        
        # 1. Migration/Preparation: Ensure components list exists
        if not definition.components:
            # Migrate legacy visualizations to components
            for vis in definition.visualizations:
                definition.components.append(ReportComponent(type=vis))
            # Clear legacy list to prefer components
            definition.visualizations = []

        # Phase 113: Artifact Prevention
        # If a report has no components (e.g. all deleted), we don't render its title/sep.
        if not definition.components:
            if definition in self.active_definitions:
                self.active_definitions.remove(definition)
            
            # If nothing else is visible, restore placeholder
            if not self.active_definitions and self.content_layout.count() == 0:
                self.clear_results()
            return

        # Separator for multiple reports
        if self.content_layout.count() > 0:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFrameShadow(QFrame.Shadow.Sunken)
            sep.setStyleSheet("color: #e2e8f0; margin: 20px 0;")
            self.content_layout.addWidget(sep)

        # Title & Info
        title_lbl = QLabel(self.tr(results["title"]))
        title_lbl.setStyleSheet("font-size: 18pt; font-weight: bold; color: #2c3e50; margin-top: 10px;")
        self.content_layout.addWidget(title_lbl)
        
        if definition.description:
            desc_lbl = QLabel(self.tr(definition.description))
            desc_lbl.setStyleSheet("color: #7f8c8d; font-style: italic; margin-bottom: 20px;")
            self.content_layout.addWidget(desc_lbl)

        # Render each component in order
        for idx, comp in enumerate(definition.components):
            widget = None
            if comp.type == "bar_chart":
                chart = BarChartWidget()
                chart.definition = definition # Store for drill-down
                chart.set_data(results["labels"], results["series"])
                chart.segment_clicked.connect(self._on_chart_drill_down)
                self.active_charts.append(chart)
                widget = self._wrap_component(chart, self.tr("Bar Chart"), idx, definition)
            
            elif comp.type == "pie_chart":
                chart = PieChartWidget()
                chart.definition = definition
                chart.set_data(results["labels"], results["series"])
                chart.segment_clicked.connect(self._on_chart_drill_down)
                self.active_charts.append(chart)
                widget = self._wrap_component(chart, self.tr("Vendor Distribution"), idx, definition)

            elif comp.type == "line_chart" or comp.type == "trend_chart":
                chart = LineChartWidget()
                chart.definition = definition
                chart.set_data(results["labels"], results["series"])
                chart.segment_clicked.connect(self._on_chart_drill_down)
                self.active_charts.append(chart)
                widget = self._wrap_component(chart, self.tr("Trend Analysis"), idx, definition)

            elif comp.type == "table":
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
                    
                    # Phase 113: Drill-Down Support for Tables
                    table.cellClicked.connect(lambda r, c, t=table, d=definition: self._on_table_drill_down(r, c, t, d))

                    widget = self._wrap_component(table, self.tr("Detailed Data"), idx, definition)
                else:
                    widget = QLabel(self.tr("No data for table."))

            elif comp.type == "text":
                editor = QTextEdit()
                editor.setPlaceholderText(self.tr("Enter your comments or summary here..."))
                editor.setText(comp.content or "")
                editor.setMinimumHeight(120)
                editor.setStyleSheet("background: #fdfdfd; font-family: sans-serif; font-size: 11pt; border: 1px solid #e2e8f0;")
                
                # Update content on change
                def update_content(c=comp, e=editor, d=definition):
                    c.content = e.toPlainText()
                    self._mark_dirty(d)

                editor.textChanged.connect(update_content)
                widget = self._wrap_component(editor, self.tr("Annotation / Comment"), idx, definition)

            if widget:
                self.content_layout.addWidget(widget)

        self.apply_zoom_visuals()
    def strip_bottom_stretch(self):
        """Removes the stretch at the end of content_layout if it exists."""
        if self.content_layout.count() > 0:
            item = self.content_layout.itemAt(self.content_layout.count() - 1)
            if item.spacerItem():
                self.content_layout.removeItem(item)

    def _wrap_component(self, inner_widget, title, index, definition):
        frame = QFrame()
        frame.setObjectName("ComponentCard")
        frame.setStyleSheet("""
            QFrame#ComponentCard { 
                background: white; border: 1px solid #e2e8f0; border-radius: 12px; 
            }
        """)
        main_ly = QVBoxLayout(frame)
        main_ly.setContentsMargins(15, 12, 15, 12)

        # Header with Title and Controls
        header = QHBoxLayout()
        title_lbl = QLabel(f"<span style='color: #475569; font-weight: bold;'>{title}</span>")
        header.addWidget(title_lbl)
        header.addStretch()

        # Controls
        btn_up = QToolButton()
        btn_up.setText("↑")
        btn_up.setToolTip(self.tr("Move Up"))
        btn_up.clicked.connect(lambda: self.move_component(index, -1, definition))
        btn_up.setEnabled(index > 0)
        
        btn_down = QToolButton()
        btn_down.setText("↓")
        btn_down.setToolTip(self.tr("Move Down"))
        btn_down.clicked.connect(lambda: self.move_component(index, 1, definition))
        btn_down.setEnabled(index < len(definition.components) - 1)

        btn_del = QToolButton()
        btn_del.setText("✕")
        btn_del.setToolTip(self.tr("Delete Component"))
        btn_del.setStyleSheet("color: #e74c3c;")
        btn_del.clicked.connect(lambda: self.delete_component(index, definition))

        header.addWidget(btn_up)
        header.addWidget(btn_down)
        header.addWidget(btn_del)
        
        main_ly.addLayout(header)
        main_ly.addWidget(inner_widget)
        return frame

    def move_component(self, index, delta, definition):
        comps = definition.components
        new_idx = index + delta
        if 0 <= new_idx < len(comps):
            comps[index], comps[new_idx] = comps[new_idx], comps[index]
            self._mark_dirty(definition)
            self.refresh_data_all() # Fully refresh all reports to reflect move within one

    def delete_component(self, index, definition):
        definition.components.pop(index)
        self._mark_dirty(definition)
        self.refresh_data_all()

    def add_text_block(self):
        if not self.current_definition: return
        self.current_definition.components.append(ReportComponent(type="text", content=""))
        self._mark_dirty(self.current_definition)
        self.refresh_data_all()

    def _mark_dirty(self, definition):
        """Sets a timer to save a specific report definition."""
        if not hasattr(self, "_save_timers"): self._save_timers = {}
        
        timer = self._save_timers.get(definition.id)
        if timer and timer.isActive():
            timer.stop()
        
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._save_report(definition))
        self._save_timers[definition.id] = timer
        timer.start(1000)

    def _save_report(self, definition):
        path = os.path.join(self.report_dir, f"{definition.id}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(definition.model_dump_json(indent=2))
        except Exception as e:
            print(f"Failed to save report: {e}")

    def refresh_data_all(self):
        """Clears and re-renders all currently involve reports."""
        defs_to_reload = list(self.active_definitions)
        self.clear_results()
        
        # Remove placeholder added by clear_results
        if self.content_layout.count() > 0:
            item = self.content_layout.itemAt(0)
            if item.widget() and isinstance(item.widget(), QLabel):
                item.widget().setParent(None)

        for definition in defs_to_reload:
            self._generate_report_for_definition(definition)

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
        chart = self.sender()
        definition = getattr(chart, "definition", self.current_definition)
        self._apply_drill_down(label, definition)

    def _on_table_drill_down(self, row, col, table, definition):
        """Builds a filter based on the clicked table row (Group Label)."""
        # We always take the first column as the grouping label
        item = table.item(row, 0)
        if item:
            self._apply_drill_down(item.text(), definition)

    def _apply_drill_down(self, label, definition):
        """Unified drill-down logic for charts and tables."""
        if not definition: return
        
        # Base filter from report
        query = definition.filter_query or {"operator": "AND", "conditions": []}
        
        drill_cond = None
        group_field = definition.group_by
        
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
            # Phase 115: Better Drill-Down
            # We filter for EVERYTHING shown in the report/histogram (base query)
            # but we request SELECTION for the specific bucket/segment.
            bucket_query = {"operator": "AND", "conditions": [query, drill_cond]}
            
            payload = {
                "query": query, 
                "select_query": bucket_query,
                "label": f"{definition.name} ({label})"
            }
            self.filter_requested.emit(payload)

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
            from PyQt6.QtCore import QBuffer, QIODevice
            from PyQt6.QtGui import QPixmap
            
            # 1. Execute report to get fresh data
            results = self.repo_gen.run_custom_report(self.db_manager, definition)
            
            # 2. Build ordered list of renderable items
            render_items = []
            
            # We need to find the widgets to grab pixmaps for charts
            # Our content_layout has: Title, Description, then Components
            # Indices for widgets in layout: 0=Title, 1=Description (if any), 2+=Components
            # Better way: find the specific widget for each component index
            
            component_widgets = []
            for i in range(self.content_layout.count()):
                w = self.content_layout.itemAt(i).widget()
                if w and w.objectName() == "ComponentCard":
                    component_widgets.append(w)

            for idx, comp in enumerate(definition.components):
                if comp.type in ["bar_chart", "pie_chart", "line_chart", "trend_chart"]:
                    # Find chart in component card
                    card = component_widgets[idx] if idx < len(component_widgets) else None
                    if card:
                        # Chart is usually the second widget in the card layout (Header is 0, Inner is 1)
                        chart_widget = card.layout().itemAt(1).widget()
                        if chart_widget:
                            pixmap = chart_widget.grab()
                            buffer = QBuffer()
                            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                            pixmap.save(buffer, "PNG")
                            render_items.append({"type": "image", "value": buffer.data().data()})
                
                elif comp.type == "table":
                    render_items.append({"type": "table", "value": results["table_rows"]})
                
                elif comp.type == "text":
                    render_items.append({"type": "text", "value": comp.content})
            
            # 3. Generate PDF (with embedded config for re-import)
            pdf_gen = PdfReportGenerator()
            try:
                # Use model_dump() directly for the new metadata API
                pdf_bytes = pdf_gen.generate(
                    results["title"], 
                    render_items, 
                    metadata=definition.model_dump()
                )
                
                path, _ = QFileDialog.getSaveFileName(self, self.tr("Export PDF"), f"{definition.name}_Report.pdf", "PDF Files (*.pdf)")
                if path:
                    with open(path, "wb") as f:
                        f.write(pdf_bytes)
                    QMessageBox.information(self, self.tr("Export PDF"), self.tr("Successfully exported report to PDF."))
            except Exception as e:
                import traceback
                traceback.print_exc()
                QMessageBox.critical(self, self.tr("Error"), f"Failed to generate PDF report: {str(e)}")
            
        elif fmt == "zip":
            # ... existing zip code ...
            path, _ = QFileDialog.getSaveFileName(self, self.tr("Export ZIP"), f"{definition.name}_Documents.zip", "ZIP Files (*.zip)")
            if path:
                import zipfile
                try:
                    with zipfile.ZipFile(path, 'w') as zip_f:
                        for doc in docs:
                            if os.path.exists(doc.path):
                                arcname = os.path.basename(doc.path)
                                zip_f.write(doc.path, arcname)
                    QMessageBox.information(self, self.tr("Export ZIP"), self.tr("Successfully created ZIP archive with %d documents.") % len(docs))
                except Exception as e:
                    QMessageBox.critical(self, self.tr("Error"), f"Failed to create ZIP: {str(e)}")

    def save_layout(self):
        """Saves current canvas state via ExchangeService."""
        if not self.active_definitions:
            QMessageBox.warning(self, self.tr("Save Layout"), self.tr("Canvas is empty."))
            return
            
        from core.exchange import ExchangeService
        
        # Prepare payload: list of current report definitions
        layout_data = {
            "name": "My Layout",
            "reports": [d.model_dump() for d in self.active_definitions]
        }
        
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Save Layout"), "my_layout.kpfx", "KPaperFlux Exchange (*.kpfx *.json)")
        if path:
            try:
                ExchangeService.save_to_file("layout", layout_data, path)
                QMessageBox.information(self, self.tr("Save Layout"), self.tr("Layout saved successfully."))
            except Exception as e:
                QMessageBox.critical(self, self.tr("Error"), f"Failed to save layout: {e}")

    def load_layout(self):
        """Loads a layout arrangement via ExchangeService."""
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Load Layout"), "", "KPaperFlux Files (*.kpfx *.json *.pdf)")
        if not path:
            return
            
        from core.exchange import ExchangeService
        payload = ExchangeService.load_from_file(path)
            
        if payload and payload.type == "layout":
            self.clear_results()
            reports = payload.payload.get("reports", [])
            for r_data in reports:
                try:
                    definition = ReportDefinition(**r_data)
                    self._generate_report_for_definition(definition)
                except Exception as e:
                    print(f"Failed to load report in layout: {e}")
            QMessageBox.information(self, self.tr("Load Layout"), self.tr("Layout loaded successfully."))
        elif payload:
             QMessageBox.warning(self, self.tr("Load Layout"), self.tr("File is not a Layout (Type: %s)") % payload.type)
        else:
             QMessageBox.warning(self, self.tr("Load Layout"), self.tr("No valid KPaperFlux payload found."))
