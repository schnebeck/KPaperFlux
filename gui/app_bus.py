"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/app_bus.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Application-level event bus. Thin QObject that owns canonical
                cross-subsystem signals. MainWindow routes subsystem signals
                through the bus so subsystems remain decoupled from each other.
------------------------------------------------------------------------------
"""
from PyQt6.QtCore import QObject, pyqtSignal


class ApplicationBus(QObject):
    """Thin signal broker for cross-subsystem events.

    Only contains signals that have TWO OR MORE subscribers in MainWindow.
    Signals with a single subscriber stay as direct connections.

    Routing rules (verified against main_window.py):

    ``metadata_saved``
        Source: ``editor_widget.metadata_saved``
        Subscribers (3):
          - ``list_widget.refresh_list``
          - ``cockpit_widget.refresh_stats``
          - ``advanced_filter.refresh_dynamic_data``

    ``filter_changed``
        Source: ``advanced_filter.filter_changed``
        Subscribers (2):
          - ``MainWindow._on_filter_changed``
          - ``list_widget.apply_advanced_filter``
    """

    # Emitted after the metadata editor saves a document.
    # Three subsystems subscribe: list, cockpit, and filter panel.
    metadata_saved = pyqtSignal()

    # Emitted when the advanced filter criteria change.
    # Two subscribers: MainWindow._on_filter_changed and list_widget.apply_advanced_filter.
    # Carries the filter criteria dict forwarded from AdvancedFilterWidget.filter_changed.
    filter_changed = pyqtSignal(dict)
