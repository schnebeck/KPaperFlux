print("Script starting...")
import sys
import unittest
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt, QCoreApplication, QSettings
import time

# Core and GUI imports
from core.database import DatabaseManager
from core.config import AppConfig
from core.pipeline import PipelineProcessor
from gui.main_window import MainWindow

# Ensure we have a display
if not os.environ.get('DISPLAY'):
    os.environ['DISPLAY'] = ':1'

class TestWindowExpansion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print("Starting setUpClass...")
        # Use a separate test organization to avoid loading user settings
        QCoreApplication.setOrganizationName("KPaperFluxTest")
        QCoreApplication.setApplicationName("ExpansionTest")

        # Create QApplication if it doesn't exist
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)
            
        # Explicitly clear any existing test settings
        settings = QSettings()
        settings.clear()
        settings.sync()
        print("setUpClass finished.")

    def test_landscape_loading_no_expansion(self):
        print("Running test_landscape_loading_no_expansion...")
        db_path = "/home/schnebeck/.local/share/kpaperflux/kpaperflux.db"
        app_config = AppConfig()
        vault_path = app_config.get_vault_path()
        
        pipeline = PipelineProcessor(base_path=str(vault_path), db=DatabaseManager(db_path))
        
        print("Initializing MainWindow...")
        window = MainWindow(pipeline=pipeline, db_manager=pipeline.db, app_config=app_config)
        window.show()
        
        # Sane initial size
        initial_w = 1000
        initial_h = 700
        window.resize(initial_w, initial_h)
        self.app.processEvents()
        
        # Explorer view (Page 1)
        window.central_stack.setCurrentIndex(1)
        self.app.processEvents()
        
        # Known Landscape UUID
        landscape_pdf_path = "/home/schnebeck/Documents/KPaperFlux/vault/b98f3148-4db2-4f48-aec1-c403d065ac79.pdf"
        
        if not os.path.exists(landscape_pdf_path):
            self.fail(f"Landscape PDF not found at {landscape_pdf_path}")
            
        print(f"Loading landscape PDF: {landscape_pdf_path}")
        window.pdf_viewer.load_document(landscape_pdf_path)
        
        # Let the layout settle
        print("Waiting for layout to settle...")
        for i in range(30):
            self.app.processEvents()
            time.sleep(0.1)
            if i % 10 == 0:
                print(f"  Pulse {i} - Width: {window.width()}")
            
        final_w = window.width()
        final_h = window.height()
        
        print(f"Final results:")
        print(f"  Window: {window.width()}x{window.height()}")
        print(f"  Main Splitter sizes: {window.main_splitter.sizes()}")
        print(f"  Left Pane width: {window.left_pane_splitter.width()} minHint.w: {window.left_pane_splitter.minimumSizeHint().width()}")
        print(f"  Advanced Filter minHint.w: {window.advanced_filter.minimumSizeHint().width()}")
        print(f"  Document List minHint.w: {window.list_widget.minimumSizeHint().width()}")
        print(f"  Metadata Editor minHint.w: {window.editor_widget.minimumSizeHint().width()}")
        print(f"  PDF Viewer width: {window.pdf_viewer.width()} minHint.w: {window.pdf_viewer.minimumSizeHint().width()}")
        print(f"  PDF Toolbar minHint.w: {window.pdf_viewer.toolbar.minimumSizeHint().width()}")
        print(f"  PDF Canvas Zoom: {window.pdf_viewer.canvas.zoom_factor}")
        
        if final_w > initial_w + 30:
            print("\n!!! WINDOW EXPANSION DETECTED !!!")
        
        # Check if window expanded significantly
        self.assertLessEqual(final_w, initial_w + 30, f"Window expanded from {initial_w} to {final_w}")
        
        window.close()
        print("Test completed successfully.")

if __name__ == "__main__":
    unittest.main()
