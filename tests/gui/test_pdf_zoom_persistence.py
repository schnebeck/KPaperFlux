import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtPdfWidgets import QPdfView
from gui.pdf_viewer import PdfViewerWidget

def test_zoom_persistence_reproduction(qtbot, qapp):
    """
    Test that zoom state is correctly saved and restored.
    This simulates an app restart by creating two separate widget instances.
    """
    # Ensure clean state
    settings = QSettings("KPaperFlux", "PdfViewer")
    settings.clear()
    
    # --- Session 1: Set Zoom to Fit ---
    viewer1 = PdfViewerWidget()
    qtbot.addWidget(viewer1)
    viewer1.enable_controls(True)
    
    # Simulate user clicking "Fit"
    # Note: restore_state is called in __init__
    
    # Verify initial state (should be default)
    # Default is Custom, 1.0 (as per code)
    
    # Change to FitInView
    from PyQt6.QtCore import Qt
    qtbot.mouseClick(viewer1.btn_fit, Qt.MouseButton.LeftButton)
    
    # Verify State 1
    assert viewer1.view.zoomMode() == QPdfView.ZoomMode.FitInView
    assert viewer1.btn_fit.isChecked() == True
    
    # Verify Settings (should be saved immediately on change? 
    # toggle_fit doesn't explicitly call save_state, but does it trigger zoomFactorChanged?
    # FitInView might NOT trigger zoomFactorChanged if it's just a mode change?)
    
    # Let's check if save_state happened
    assert settings.value("zoomMode") is not None
    assert int(settings.value("zoomMode")) == QPdfView.ZoomMode.FitInView.value
    
    viewer1.close()
    
    # --- Session 2: Restart ---
    viewer2 = PdfViewerWidget()
    qtbot.addWidget(viewer2)
    
    # Logic in __init__ calls restore_state()
    
    # Verify State 2
    assert viewer2.view.zoomMode() == QPdfView.ZoomMode.FitInView
    assert viewer2.btn_fit.isChecked() == True
    
    viewer2.close()

def test_zoom_factor_persistence(qtbot):
    """Test saving a custom zoom factor."""
    settings = QSettings("KPaperFlux", "PdfViewer")
    settings.clear()
    
    viewer1 = PdfViewerWidget()
    qtbot.addWidget(viewer1)
    
    # Set custom zoom
    # zoom_in triggers update_zoom_label -> save_state
    viewer1.zoom_in() 
    target_factor = viewer1.view.zoomFactor()
    
    # Verify settings updated
    saved_factor = float(settings.value("zoomFactor"))
    assert abs(saved_factor - target_factor) < 0.001
    
    viewer1.close()
    
    # Restart
    viewer2 = PdfViewerWidget()
    qtbot.addWidget(viewer2)
    
    assert viewer2.view.zoomMode() == QPdfView.ZoomMode.Custom
    assert abs(viewer2.view.zoomFactor() - target_factor) < 0.001
    
    viewer2.close()
