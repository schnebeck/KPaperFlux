
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtCore import QUrl, Qt
from pathlib import Path

class PdfViewerWidget(QWidget):
    """
    Modern PDF Viewer using QtPdf (Qt6).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.document = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(5, 5, 5, 5)
        
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setFixedWidth(30)
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setFixedWidth(30)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        
        self.lbl_zoom = QLabel("100%")
        
        toolbar.addWidget(QLabel("Zoom:"))
        toolbar.addWidget(self.btn_zoom_out)
        toolbar.addWidget(self.lbl_zoom)
        toolbar.addWidget(self.btn_zoom_in)
        toolbar.addStretch()
        
        layout.addLayout(toolbar)
        layout.addWidget(self.view)
        
        # Connect signals
        self.view.zoomFactorChanged.connect(self.update_zoom_label)
        
    def load_document(self, file_path: str):
        if not file_path:
            self.clear()
            return
            
        path = Path(file_path).resolve()
        if not path.exists():
            self.clear()
            return
            
        # QPdfDocument.load takes a file path or QIODevice?
        # In PyQt6, load takes a filename string.
        # But wait, QPdfDocument.load() signature: load(QIODevice) or load(str).
        try:
            self.document.load(str(path))
            # Set Title?
        except Exception as e:
            print(f"Error loading PDF: {e}")
            
    def clear(self):
        # How to unload? Create new empty QPdfDocument or load empty?
        # self.document.close() only if QPdfDocument has it.
        # QPdfDocument inherits QObject.
        # Just loading nothing?
        # Re-creating might be safer if no unload exists.
        pass

    def zoom_in(self):
        current = self.view.zoomFactor()
        self.view.setZoomFactor(current * 1.2)
        
    def zoom_out(self):
        current = self.view.zoomFactor()
        self.view.setZoomFactor(current / 1.2)
        
    def update_zoom_label(self, factor):
        self.lbl_zoom.setText(f"{int(factor * 100)}%")
