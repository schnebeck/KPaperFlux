import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSize, QPointF
from PyQt6.QtPdf import QPdfDocument
from unittest.mock import MagicMock
from gui.pdf_viewer import DualPdfViewerWidget

def run_diagnosis():
    app = QApplication(sys.argv)
    dual = DualPdfViewerWidget()
    dual.show()

    # 1. Setup: Documents A4 (100x100 points for simplicity)
    for viewer in [dual.left_viewer, dual.right_viewer]:
        viewer.document = MagicMock()
        viewer.document.pageCount.return_value = 1
        viewer.document.pagePointSize.return_value = QSize(100, 100)
        viewer.document.status.return_value = QPdfDocument.Status.Ready
        viewer.view.viewport = MagicMock()
        viewer.view.viewport().width.return_value = 100
        viewer.view.viewport().height.return_value = 1000 # Portrait

    # 2. Master Link + Fit
    dual.btn_link.setChecked(True)
    dual.left_viewer.btn_fit.setChecked(True)
    dual._on_fit_clicked(dual.left_viewer, dual.right_viewer)

    print(f"--- INIT ---")
    print(f"Master Fit: {dual.left_viewer.view.zoomMode()}")
    print(f"Slave Delta: {dual._zoom_delta}")
    print(f"Slave Zoom: {dual.right_viewer.view.zoomFactor()}")

    # 3. INTERACTION: Zoom In on Slave
    print(f"\n--- TRIGGER ZOOM-IN RIGHT ---")
    dual.right_viewer.zoom_in()

    print(f"New Delta: {dual._zoom_delta}")
    print(f"Slave Mode: {dual.right_viewer.view.zoomMode()}")
    print(f"Slave Zoom: {dual.right_viewer.view.zoomFactor()}")

    # 4. SIMULATE RESIZE / RE-SYNC
    print(f"\n--- RE-LEVEL SYNC ---")
    dual._do_sync_all(dual.left_viewer, dual.right_viewer)
    print(f"Final Delta: {dual._zoom_delta}")
    print(f"Final Slave Zoom: {dual.right_viewer.view.zoomFactor()}")

if __name__ == "__main__":
    run_diagnosis()
