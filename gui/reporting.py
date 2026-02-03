import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QFrame, QScrollArea, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QPen

from core.reporting import ReportGenerator

class BarChartWidget(QWidget):
    """Simple Bar Chart using QPainter."""
    def __init__(self, data: Dict[str, float], color: QColor, parent=None):
        super().__init__(parent)
        self.data = data # { "2023-01": 120.50, ... }
        self.color = color
        self.setMinimumHeight(250)

    def set_data(self, data: Dict[str, float]):
        self.data = data
        self.update()

    def paintEvent(self, event):
        if not self.data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        margin = 40
        chart_width = width - 2 * margin
        chart_height = height - 2 * margin

        keys = sorted(self.data.keys())
        values = [self.data[k] for k in keys]
        max_val = max(values) if values else 0
        if max_val == 0: max_val = 1

        bar_count = len(keys)
        bar_spacing = 10
        bar_width = (chart_width - (bar_count - 1) * bar_spacing) / bar_count
        if bar_width < 1: bar_width = 1

        # Draw axis
        painter.setPen(QPen(Qt.GlobalColor.gray, 1))
        painter.drawLine(margin, height - margin, width - margin, height - margin)
        painter.drawLine(margin, margin, margin, height - margin)

        # Draw Labels & Bars
        font = QFont("Sans Serif", 8)
        painter.setFont(font)

        for i, key in enumerate(keys):
            val = self.data[key]
            bar_h = (val / max_val) * chart_height
            
            x = margin + i * (bar_width + bar_spacing)
            y = height - margin - bar_h
            
            # Bar
            painter.setBrush(self.color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(x), int(y), int(bar_width), int(bar_h))
            
            # Key Label (rotate if too many)
            painter.setPen(Qt.GlobalColor.black)
            label_rect = QRect(int(x), height - margin + 5, int(bar_width), margin)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, key[-2:] if len(keys) > 12 else key)

        # Draw Max Value
        painter.drawText(5, margin + 10, f"{max_val:,.0f}")

class ReportingWidget(QWidget):
    """Deep-dive reporting tab with tables and charts."""
    
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.repo_gen = ReportGenerator()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        header = QHBoxLayout()
        title = QLabel("Financial Reporting")
        title.setStyleSheet("font-size: 20pt; font-weight: bold; color: #2c3e50;")
        header.addWidget(title)
        
        header.addStretch()
        
        self.btn_refresh = QPushButton("🔄 Refresh Reports")
        self.btn_refresh.clicked.connect(self.refresh_data)
        self.btn_refresh.setStyleSheet("padding: 8px 15px; font-weight: bold;")
        header.addWidget(self.btn_refresh)
        
        self.btn_export = QPushButton("📤 Export to Excel (CSV)")
        self.btn_export.clicked.connect(self.export_csv)
        self.btn_export.setStyleSheet("background-color: #1b5e20; color: white; padding: 8px 15px; font-weight: bold;")
        header.addWidget(self.btn_export)
        
        layout.addLayout(header)

        # Scrollable Content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Charts Section
        chart_frame = QFrame()
        chart_frame.setStyleSheet("background-color: white; border-radius: 12px; border: 1px solid #ddd;")
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.addWidget(QLabel("Monthly Invoiced Totals (Rolling 12 Months)"))
        self.invoiced_chart = BarChartWidget({}, QColor("#f59e0b"), self)
        chart_layout.addWidget(self.invoiced_chart)
        self.content_layout.addWidget(chart_frame)

        # Summary Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Month", "Total Net", "Total Gross"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("background-color: white; border-radius: 8px;")
        self.content_layout.addWidget(QLabel("Detailed Summary Table"))
        self.content_layout.addWidget(self.table)
        
        # Tax Section
        self.tax_table = QTableWidget()
        self.tax_table.setColumnCount(2)
        self.tax_table.setHorizontalHeaderLabels(["Tax Rate", "Total Tax Amount"])
        self.tax_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.content_layout.addWidget(QLabel("Tax Breakdown"))
        self.content_layout.addWidget(self.tax_table)

    def refresh_data(self):
        if not self.db_manager: return
        
        # Fetch all processed documents for the last year ideally, but for now just ALL
        docs = self.db_manager.get_all_entities_view()
        # Filter for Invoices/Receipts
        finance_docs = [d for d in docs if "INVOICE" in (d.type_tags or []) or "RECEIPT" in (d.type_tags or [])]
        
        # Monthly Summary
        monthly = self.repo_gen.get_monthly_summary(finance_docs)
        self.table.setRowCount(0)
        chart_data = {}
        
        for month in sorted(monthly.keys(), reverse=True):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(month))
            self.table.setItem(r, 1, QTableWidgetItem(f"{monthly[month]['net']:,.2f} €"))
            self.table.setItem(r, 2, QTableWidgetItem(f"{monthly[month]['gross']:,.2f} €"))
            chart_data[month] = float(monthly[month]['gross'])

        self.invoiced_chart.set_data(chart_data)

        # Tax Summary
        tax = self.repo_gen.get_tax_summary(finance_docs)
        self.tax_table.setRowCount(0)
        for rate, amount in tax.items():
            r = self.tax_table.rowCount()
            self.tax_table.insertRow(r)
            self.tax_table.setItem(r, 0, QTableWidgetItem(rate))
            self.tax_table.setItem(r, 1, QTableWidgetItem(f"{amount:,.2f} €"))

    def export_csv(self):
        docs = self.db_manager.get_all_entities_view()
        csv_data = self.repo_gen.export_to_csv(docs)
        
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Export Report", "KPaperFlux_Export.csv", "CSV Files (*.csv)")
        if path:
            with open(path, "wb") as f:
                f.write(csv_data)
            from gui.utils import show_notification
            show_notification(self, "Export Done", f"Saved report to {path}")
