
import os
import json
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, 
    QTextEdit, QComboBox, QTableWidget, QTableWidgetItem, 
    QPushButton, QLabel, QCheckBox, QHeaderView, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from core.models.reporting import ReportDefinition, Aggregation
from core.reporting import ReportRegistry

logger = logging.getLogger("KPaperFlux.Reporting")

from gui.widgets.filter_group import FilterGroupWidget

class ReportEditorWidget(QWidget):
    """Editor for a single Report Definition with integrated filter builder."""
    changed = pyqtSignal()
    
    def __init__(self, db_manager=None, filter_tree=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.filter_tree = filter_tree
        self.current_report = None
        self._lock_signals = False
        
        # Dynamic metadata
        self.extra_keys = []
        self.available_tags = []
        self.available_system_tags = []
        if self.db_manager:
            self.extra_keys = self.db_manager.get_available_extra_keys()
            self.available_tags = self.db_manager.get_available_tags(system=False)
            self.available_system_tags = self.db_manager.get_available_tags(system=True)

        self._init_ui()

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        
        # Meta Info
        self.meta_frame = QFrame()
        self.meta_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.meta_frame.setStyleSheet("background: #fdfdfd; border-radius: 6px;")
        meta_layout = QFormLayout(self.meta_frame)
        
        self.edit_name = QLineEdit()
        self.edit_name.textChanged.connect(self._on_changed)
        self.edit_desc = QTextEdit()
        self.edit_desc.setMaximumHeight(60)
        self.edit_desc.textChanged.connect(self._on_changed)
        
        meta_layout.addRow("Report Name:", self.edit_name)
        meta_layout.addRow("Description:", self.edit_desc)
        
        self.layout.addWidget(self.meta_frame)
        
        # Configuration Section
        config_frame = QFrame()
        config_layout = QVBoxLayout(config_frame)
        
        # Group By
        group_layout = QHBoxLayout()
        group_layout.addWidget(QLabel("Group By:"))
        self.combo_group = QComboBox()
        self.combo_group.addItems([
            "None", "doc_date:month", "doc_date:year", "sender", "type",
            "amount:10", "amount:50", "amount:100", "amount:500"
        ])
        self.combo_group.setToolTip("Select 'amount:X' for histogram view (grouping by price ranges).")
        self.combo_group.currentIndexChanged.connect(self._on_changed)
        group_layout.addWidget(self.combo_group, 1)
        config_layout.addLayout(group_layout)
        
        # Aggregations
        config_layout.addWidget(QLabel("Aggregations:"))
        self.agg_table = QTableWidget(0, 2)
        self.agg_table.setHorizontalHeaderLabels(["Field", "Operation"])
        self.agg_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.agg_table.itemChanged.connect(self._on_changed)
        config_layout.addWidget(self.agg_table)
        
        btn_agg_layout = QHBoxLayout()
        self.btn_add_agg = QPushButton("+ Add Aggregation")
        self.btn_add_agg.clicked.connect(self._add_agg_row)
        self.btn_del_agg = QPushButton("- Remove Selected")
        self.btn_del_agg.clicked.connect(self._remove_agg_row)
        btn_agg_layout.addWidget(self.btn_add_agg)
        btn_agg_layout.addWidget(self.btn_del_agg)
        btn_agg_layout.addStretch()
        config_layout.addLayout(btn_agg_layout)
        
        # Visualizations
        viz_layout = QHBoxLayout()
        viz_layout.addWidget(QLabel("Show as:"))
        self.chk_table = QCheckBox("Table")
        self.chk_chart = QCheckBox("Bar Chart")
        self.chk_pie = QCheckBox("Pie Chart")
        self.chk_trend = QCheckBox("Trend")
        self.chk_csv = QCheckBox("CSV Export")
        for chk in [self.chk_table, self.chk_chart, self.chk_pie, self.chk_trend, self.chk_csv]:
            chk.stateChanged.connect(self._on_changed)
            viz_layout.addWidget(chk)
        viz_layout.addStretch()
        config_layout.addLayout(viz_layout)
        
        self.layout.addWidget(config_frame)
        
        # --- Filter Section ---
        filter_box = QFrame()
        filter_box.setFrameShape(QFrame.Shape.StyledPanel)
        filter_box.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;")
        filter_vbox = QVBoxLayout(filter_box)
        
        fl_header = QHBoxLayout()
        fl_header.addWidget(QLabel("<b>Data Source (Filter):</b>"))
        fl_header.addStretch()
        
        if self.filter_tree:
            self.combo_saved_filters = QComboBox()
            self.combo_saved_filters.addItem("-- Import from Saved Filter --", None)
            for f in self.filter_tree.get_all_filters():
                self.combo_saved_filters.addItem(f.name, f.data)
            self.combo_saved_filters.currentIndexChanged.connect(self._import_filter_criteria)
            fl_header.addWidget(self.combo_saved_filters)
            
        filter_vbox.addLayout(fl_header)
        
        # Use recursive FilterGroupWidget
        self.filter_builder = FilterGroupWidget(
            extra_keys=self.extra_keys,
            available_tags=self.available_tags,
            available_system_tags=self.available_system_tags,
            is_root=True
        )
        self.filter_builder.changed.connect(self._on_changed)
        
        # Scroll area for filter if it gets long
        filter_scroll = QScrollArea()
        filter_scroll.setWidgetResizable(True)
        filter_scroll.setMinimumHeight(200)
        filter_scroll.setWidget(self.filter_builder)
        filter_vbox.addWidget(filter_scroll)
        
        self.layout.addWidget(filter_box)
        
        # Action Buttons
        self.btn_save = QPushButton("Save Report Definition")
        self.btn_save.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 10px;")
        self.btn_save.clicked.connect(self.save_report)
        self.layout.addWidget(self.btn_save)

    def _on_changed(self):
        if not self._lock_signals:
            self.changed.emit()

    def _add_agg_row(self):
        row = self.agg_table.rowCount()
        self.agg_table.insertRow(row)
        field_item = QComboBox()
        field_item.addItems(["gross", "net", "tax", "amount"])
        field_item.setEditable(True)
        self.agg_table.setCellWidget(row, 0, field_item)
        
        op_item = QComboBox()
        op_item.addItems(["sum", "avg", "count", "min", "max", "median", "percent"])
        self.agg_table.setCellWidget(row, 1, op_item)
        
        field_item.currentIndexChanged.connect(self._on_changed)
        op_item.currentIndexChanged.connect(self._on_changed)

    def _remove_agg_row(self):
        row = self.agg_table.currentRow()
        if row >= 0:
            self.agg_table.removeRow(row)
            self._on_changed()

    def _import_filter_criteria(self, index):
        if index <= 0: return
        query = self.combo_saved_filters.currentData()
        if query:
            self.filter_builder.set_query(query)

    def load_report(self, report: ReportDefinition):
        self._lock_signals = True
        self.current_report = report
        self.edit_name.setText(report.name)
        self.edit_desc.setPlainText(report.description or "")
        
        idx = self.combo_group.findText(report.group_by or "None")
        self.combo_group.setCurrentIndex(max(0, idx))
        
        # Load filter criteria
        if report.filter_query:
            self.filter_builder.set_query(report.filter_query)
        else:
            self.filter_builder.clear()

        self.agg_table.setRowCount(0)
        for agg in report.aggregations:
            row = self.agg_table.rowCount()
            self.agg_table.insertRow(row)
            
            field_combo = QComboBox()
            field_combo.addItems(["gross", "net", "tax", "amount"])
            field_combo.setEditable(True)
            field_combo.setCurrentText(agg.field)
            self.agg_table.setCellWidget(row, 0, field_combo)
            
            op_combo = QComboBox()
            op_combo.addItems(["sum", "avg", "count", "min", "max", "median", "percent"])
            op_combo.setCurrentText(agg.op)
            self.agg_table.setCellWidget(row, 1, op_combo)
            
            field_combo.currentIndexChanged.connect(self._on_changed)
            op_combo.currentIndexChanged.connect(self._on_changed)

        self.chk_table.setChecked("table" in report.visualizations)
        self.chk_chart.setChecked("bar_chart" in report.visualizations)
        self.chk_pie.setChecked("pie_chart" in report.visualizations)
        self.chk_trend.setChecked("trend_chart" in report.visualizations)
        self.chk_csv.setChecked("csv" in report.visualizations)
        
        self._lock_signals = False

    def get_report_definition(self) -> ReportDefinition:
        import time
        pb_id = self.current_report.id if (self.current_report and self.current_report.id) else f"report_{int(time.time())}"
        
        aggs = []
        for r in range(self.agg_table.rowCount()):
            f_widget = self.agg_table.cellWidget(r, 0)
            o_widget = self.agg_table.cellWidget(r, 1)
            if isinstance(f_widget, QComboBox) and isinstance(o_widget, QComboBox):
                aggs.append(Aggregation(field=f_widget.currentText(), op=o_widget.currentText()))
        
        viz = []
        if self.chk_table.isChecked(): viz.append("table")
        if self.chk_chart.isChecked(): viz.append("bar_chart")
        if self.chk_pie.isChecked(): viz.append("pie_chart")
        if self.chk_trend.isChecked(): viz.append("trend_chart")
        if self.chk_csv.isChecked(): viz.append("csv")
        
        group = self.combo_group.currentText()
        if group == "None": group = None
        
        return ReportDefinition(
            id=pb_id,
            name=self.edit_name.text(),
            description=self.edit_desc.toPlainText(),
            group_by=group,
            aggregations=aggs,
            visualizations=viz,
            filter_query=self.filter_builder.get_query()
        )

    def save_report(self):
        try:
            report = self.get_report_definition()
            report_dir = "resources/reports"
            os.makedirs(report_dir, exist_ok=True)
            
            file_path = os.path.join(report_dir, f"{report.id}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report.model_dump(), f, indent=2)
            
            QMessageBox.information(self, "Success", f"Report definition '{report.name}' saved.")
            ReportRegistry().load_from_directory(report_dir)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save report: {e}")
