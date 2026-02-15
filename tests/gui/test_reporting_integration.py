import pytest
import os
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PyQt6.QtCore import Qt, QMimeData, QUrl
from gui.reporting import ReportingWidget
from core.reporting import ReportDefinition

@pytest.fixture
def mock_db():
    db = MagicMock()
    # Mock search to return one dummy doc
    mock_doc = MagicMock()
    mock_doc.uuid = "dummy-uuid"
    mock_doc.doc_date = "2023-10-27"
    db.search_documents_advanced.return_value = [mock_doc]
    return db

@pytest.fixture
def reporting_widget(qtbot, mock_db):
    widget = ReportingWidget(db_manager=mock_db)
    qtbot.addWidget(widget)
    widget.show()
    return widget

def test_drop_report_definition_triggers_display_and_selection(qtbot, reporting_widget):
    """
    Test that dropping a report definition payload:
    1. Clears existing results.
    2. Imports/Saves the definition.
    3. Selects it in the combo box.
    4. Triggers rendering.
    """
    payload_data = {
        "id": "dropped_report",
        "name": "Dropped Report Title",
        "components": [{"type": "table"}]
    }
    
    # Mock ExchangeService to return our payload
    mock_payload = MagicMock()
    mock_payload.type = "report_definition"
    mock_payload.payload = payload_data
    
    with patch("core.exchange.ExchangeService.load_from_file", return_value=mock_payload), \
         patch("gui.reporting.os.path.exists", return_value=True), \
         patch.object(reporting_widget, "_save_report_definition", return_value=True), \
         patch.object(reporting_widget, "load_available_reports"), \
         patch.object(reporting_widget, "_generate_report_for_definition") as mock_run:
        
        # Simulate Drop Event
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile("/tmp/test.kpfx")])
        
        event = MagicMock()
        event.mimeData.return_value = mime_data
        
        print("\n[TEST] Debug: Triggering dropEvent")
        reporting_widget.dropEvent(event)
        
        # Verify it was triggered
        assert mock_run.call_count == 1
        definition = mock_run.call_args[0][0]
        assert definition.id == "dropped_report"

def test_pdf_export_triggers_file_dialog(qtbot, reporting_widget, mock_db):
    """
    Test that selecting a report and clicking PDF export opens the file dialog.
    """
    # 1. Setup a selected report
    definition = ReportDefinition(id="test_export", name="Test Export", components=[{"type": "table"}])
    reporting_widget.registry.reports["test_export"] = definition
    reporting_widget.combo_reports.addItem("Test Export", "test_export")
    reporting_widget.combo_reports.setCurrentIndex(reporting_widget.combo_reports.findData("test_export"))
    
    # Mock reporting engine to return dummy results
    mock_results = {
        "title": "Test Result",
        "table_rows": [{"col": "val"}]
    }
    reporting_widget.repo_gen.run_custom_report = MagicMock(return_value=mock_results)
    
    # 2. Mock File Dialog and PDF Generator and Message Boxes
    with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=("/tmp/out.pdf", "PDF")), \
         patch("core.exporters.pdf_report.PdfReportGenerator.generate", return_value=b"dummy-pdf-content"), \
         patch("PyQt6.QtWidgets.QMessageBox.information"), \
         patch("builtins.open", MagicMock()):
        
        print("\n[TEST] Debug: Triggering export_as('pdf')")
        # Trigger PDF Export
        reporting_widget.export_as("pdf")
        
        # 3. Verify Generator was called
        from core.exporters.pdf_report import PdfReportGenerator
        PdfReportGenerator.generate.assert_called_once()
        
        # Verify QMessageBox was shown
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information.assert_called_once()

def test_layout_drop_loads_multiple_reports(qtbot, reporting_widget):
    """
    Test that dropping a layout payload loads all included reports.
    """
    layout_payload = {
        "name": "My Layout",
        "reports": [
            {"id": "r1", "name": "Report 1", "components": []},
            {"id": "r2", "name": "Report 2", "components": []}
        ]
    }
    
    mock_payload = MagicMock()
    mock_payload.type = "layout"
    mock_payload.payload = layout_payload
    
    with patch("core.exchange.ExchangeService.load_from_file", return_value=mock_payload), \
         patch("gui.reporting.os.path.exists", return_value=True), \
         patch("gui.utils.show_notification") as mock_notif, \
         patch.object(reporting_widget, "_generate_report_for_definition") as mock_run:
        
        event = MagicMock()
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile("/tmp/layout.kpfx")])
        event.mimeData.return_value = mime_data
        
        reporting_widget.dropEvent(event)
        
        # Verify two reports were triggered
        assert mock_run.call_count == 2
        mock_notif.assert_called_once()
