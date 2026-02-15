import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QToolButton, QLabel, QFrame
from PyQt6.QtCore import Qt
from gui.reporting import ReportingWidget
from core.models.reporting import ReportDefinition, ReportComponent
from core.database import DatabaseManager

@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])

@pytest.fixture
def reporting_widget(qtbot):
    db_mock = MagicMock(spec=DatabaseManager)
    db_mock.search_documents_advanced.return_value = []
    widget = ReportingWidget(db_manager=db_mock)
    qtbot.addWidget(widget)
    return widget

def test_delete_all_components_removes_all_artifacts(qtbot, reporting_widget):
    with patch('gui.utils.show_selectable_message_box'), \
         patch('PyQt6.QtWidgets.QMessageBox.critical'), \
         patch('PyQt6.QtWidgets.QMessageBox.warning'):
        
        report_def = ReportDefinition(id="test", name="Mock Report", components=[ReportComponent(type="table")])
        results = {"title": "ARTIF_TITLE", "labels": [], "series": [], "table_rows": [{"val": 1}]}
        
        reporting_widget.render_report(results, report_def)
        
        # Verify rendered
        assert any("ARTIF_TITLE" in getattr(w, 'text', lambda: '')() for w in reporting_widget.findChildren(QLabel))
        
        def sync_refresh():
            reporting_widget.clear_results()
            reporting_widget.render_report(results, report_def)

        with patch.object(reporting_widget, 'refresh_data_all', side_effect=sync_refresh):
            btn = [b for b in reporting_widget.findChildren(QToolButton) if b.text() == "✕"][0]
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        
        # Only placeholder should remain
        labels = [w.text() for w in reporting_widget.findChildren(QLabel) if hasattr(w, 'text')]
        assert any("Please select" in l for l in labels)
        assert not any("ARTIF_TITLE" in l for l in labels)
        
        seps = [w for w in reporting_widget.findChildren(QFrame) if w.frameShape() == QFrame.Shape.HLine]
        assert len(seps) == 0

def test_delete_one_report_leaves_others_intact(qtbot, reporting_widget):
    with patch('gui.utils.show_selectable_message_box'), \
         patch('PyQt6.QtWidgets.QMessageBox.critical'), \
         patch('PyQt6.QtWidgets.QMessageBox.warning'):
        
        ra = ReportDefinition(id="ra", name="Report A", components=[ReportComponent(type="table")])
        rb = ReportDefinition(id="rb", name="Report B", components=[ReportComponent(type="table")])
        
        res_a = {"title": "TITLE_A", "labels": [], "series": [], "table_rows": [{"x": 1}]}
        res_b = {"title": "TITLE_B", "labels": [], "series": [], "table_rows": [{"x": 1}]}
        
        reporting_widget.active_definitions = [ra, rb]
        reporting_widget.render_report(res_a, ra)
        reporting_widget.render_report(res_b, rb)
        
        delete_buttons = [b for b in reporting_widget.findChildren(QToolButton) if b.text() == "✕"]
        assert len(delete_buttons) == 2
        
        def sync_refresh():
            # Real refresh_data_all does self.clear_results()
            reporting_widget.active_charts = []
            # We DONT clear active_definitions because we want to re-render remaining ones
            while reporting_widget.content_layout.count():
                item = reporting_widget.content_layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
            
            # Re-render active ones. ra is now empty, rb is not.
            reporting_widget.render_report(res_a, ra)
            reporting_widget.render_report(res_b, rb)
            
        with patch.object(reporting_widget, 'refresh_data_all', side_effect=sync_refresh):
            qtbot.mouseClick(delete_buttons[0], Qt.MouseButton.LeftButton)
            
        labels = [w.text() for w in reporting_widget.findChildren(QLabel) if hasattr(w, 'text')]
        assert any("TITLE_B" in t for t in labels)
        assert not any("TITLE_A" in t for t in labels)
        
        seps = [w for w in reporting_widget.findChildren(QFrame) if w.frameShape() == QFrame.Shape.HLine]
        assert len(seps) == 0
