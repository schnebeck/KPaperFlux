"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/activity_widgets.py
Version:        1.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Minimalist status bar widget for background activity.
                Replaces the large panel with a compact integration.
------------------------------------------------------------------------------
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QProgressBar, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize

class BackgroundActivityStatusBar(QFrame):
    """
    A minimalist, compact widget designed for the QStatusBar.
    Provides feedback and control without wasting space.
    """
    
    pause_requested = pyqtSignal(bool)
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusActivityWidget")
        self.init_ui()

    def init_ui(self):
        # Ultra-compact styling to match system look
        self.setStyleSheet("""
            #StatusActivityWidget {
                background: transparent;
                padding: 0px;
                margin: 0px;
            }
            QLabel {
                font-size: 11px;
                color: #222;
            }
            QProgressBar {
                border: 1px solid #ccc;
                background-color: #eee;
                height: 12px;
                width: 80px;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #89b4fa;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 2px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton#PauseBtn:checked {
                background-color: #fab387;
                border: 1px solid #e67e22;
            }
            QPushButton#StopBtn:hover {
                background-color: #f28fad;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Mini Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide() # Hide when idle
        layout.addWidget(self.progress_bar)

        # Mini Controls
        self.pause_btn = QPushButton()
        self.pause_btn.setObjectName("PauseBtn")
        self.pause_btn.setCheckable(True)
        self.pause_btn.setFixedSize(20, 20)
        self.pause_btn.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_MediaPause))
        self.pause_btn.setToolTip("Pause Background AI")
        self.pause_btn.clicked.connect(self._on_pause_clicked)
        layout.addWidget(self.pause_btn)

        self.stop_btn = QPushButton()
        self.stop_btn.setObjectName("StopBtn")
        self.stop_btn.setFixedSize(20, 20)
        self.stop_btn.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_MediaStop))
        self.stop_btn.setToolTip("Stop Background AI")
        self.stop_btn.clicked.connect(self.stop_requested)
        layout.addWidget(self.stop_btn)

    def _on_pause_clicked(self, checked):
        if checked:
            self.pause_btn.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_MediaPlay))
        else:
            self.pause_btn.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_MediaPause))
        self.pause_requested.emit(checked)

    @pyqtSlot(int, int)
    def update_progress(self, current, total):
        if total <= 0:
            self.progress_bar.hide()
        else:
            self.progress_bar.show()
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)

    @pyqtSlot(str)
    def update_status(self, text):
        if "Idle" in text or "Paused" in text or "Stopped" in text:
            self.progress_bar.hide()

    @pyqtSlot(bool)
    def on_pause_state_changed(self, is_paused):
        self.pause_btn.setChecked(is_paused)
        if is_paused:
            self.pause_btn.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_MediaPlay))
            self.progress_bar.hide()
        else:
            self.pause_btn.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_MediaPause))
