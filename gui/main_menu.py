"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/main_menu.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Mixin that adds the menu bar, toolbar, tab navigation and
                retranslate_ui logic to MainWindow.  All methods rely on
                attributes created by MainWindow's _setup_* helpers, so
                the mixin must always be mixed in together with QMainWindow.
------------------------------------------------------------------------------
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QToolBar, QToolButton, QWidget, QHBoxLayout, QSizePolicy,
)
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtCore import Qt, QSize

from core.logger import get_logger
from core.scanner import SANE_AVAILABLE

logger = get_logger("gui.main_menu")


class MainWindowMenuMixin:
    """
    Pure-mixin (no __init__) that contributes menu bar, toolbar and
    localisation helpers to MainWindow.

    Assumes MainWindow attributes:
        pipeline, db_manager, app_config, plugin_manager, central_stack,
        cockpit_widget, reporting_widget, workflow_manager, list_widget,
        advanced_filter, left_pane_splitter, main_status_label,
        _last_selected_uuid, pdf_viewer
    """

    # ── Menu Bar ──────────────────────────────────────────────────────────────

    def create_menu_bar(self) -> None:
        menubar = self.menuBar()

        # -- File Menu --
        self.file_menu = menubar.addMenu("")

        self.action_import = QAction("", self)
        self.action_import.setShortcut("Ctrl+O")
        self.action_import.triggered.connect(self.import_document_slot)
        self.file_menu.addAction(self.action_import)

        self.action_import_transfer = QAction("", self)
        self.action_import_transfer.triggered.connect(self.import_from_transfer_slot)
        self.file_menu.addAction(self.action_import_transfer)
        self._update_transfer_menu_visibility()

        self.action_scan = QAction("", self)
        self.action_scan.setShortcut("Ctrl+S")
        self.action_scan.triggered.connect(self.open_scanner_slot)
        if SANE_AVAILABLE:
            self.file_menu.addAction(self.action_scan)
        else:
            self.action_scan.setVisible(False)
            logger.info("Scanner functionality disabled: SANE_AVAILABLE is False")

        self.action_print = QAction("", self)
        self.action_print.setShortcut("Ctrl+P")
        self.action_print.setEnabled(False)
        self.file_menu.addAction(self.action_print)

        self.file_menu.addSeparator()

        self.action_delete = QAction("", self)
        self.action_delete.setShortcut("Del")
        self.action_delete.triggered.connect(self.delete_selected_slot)
        self.file_menu.addAction(self.action_delete)

        self.file_menu.addSeparator()

        self.action_export = QAction("", self)
        self.action_export.triggered.connect(self.export_visible_documents_slot)
        self.file_menu.addAction(self.action_export)

        self.file_menu.addSeparator()

        self.action_exit = QAction("", self)
        self.action_exit.setShortcut("Ctrl+Q")
        self.action_exit.triggered.connect(self.close)
        self.file_menu.addAction(self.action_exit)

        # -- View Menu --
        self.view_menu = menubar.addMenu("")

        self.action_refresh = QAction("", self)
        self.action_refresh.setShortcut("F5")
        self.action_refresh.triggered.connect(self.refresh_list_slot)
        self.view_menu.addAction(self.action_refresh)

        self.action_extra = QAction("", self)
        self.action_extra.setShortcut("Ctrl+E")
        self.action_extra.setCheckable(True)
        self.action_extra.setChecked(True)
        self.action_extra.triggered.connect(self.toggle_editor_visibility)
        self.view_menu.addAction(self.action_extra)

        self.view_menu.addSeparator()

        self.action_toggle_filter = QAction("", self)
        self.action_toggle_filter.setCheckable(True)
        self.action_toggle_filter.setChecked(True)
        self.action_toggle_filter.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.action_toggle_filter.triggered.connect(self._toggle_filter_view)
        self.view_menu.addAction(self.action_toggle_filter)

        # -- Maintenance Menu --
        self.maintenance_menu = menubar.addMenu("")

        self.action_maintenance = QAction("", self)
        self.action_maintenance.triggered.connect(self.open_maintenance_slot)
        self.maintenance_menu.addAction(self.action_maintenance)

        self.action_duplicates = QAction("", self)
        self.action_duplicates.triggered.connect(self.find_duplicates_slot)
        self.maintenance_menu.addAction(self.action_duplicates)

        self.action_tag_manager = QAction("", self)
        self.action_tag_manager.triggered.connect(self.open_tag_manager_slot)
        self.maintenance_menu.addAction(self.action_tag_manager)

        # -- Tools Menu --
        self.tools_menu = menubar.addMenu("")

        self.action_purge_data = QAction("", self)
        self.action_purge_data.triggered.connect(self.purge_data_slot)
        self.tools_menu.addAction(self.action_purge_data)

        self.tools_menu.addSeparator()
        self.plugin_submenu = self.tools_menu.addMenu("")
        self._refresh_plugin_menu()

        # -- Debug Menu --
        self.debug_menu = menubar.addMenu("")

        self.action_debug_orphans = QAction("", self)
        self.action_debug_orphans.triggered.connect(self._debug_show_orphans_slot)
        self.debug_menu.addAction(self.action_debug_orphans)

        self.action_prune_orphans = QAction("", self)
        self.action_prune_orphans.triggered.connect(self._debug_prune_orphans_slot)
        self.debug_menu.addAction(self.action_prune_orphans)

        self.debug_menu.addSeparator()

        self.action_debug_broken = QAction("", self)
        self.action_debug_broken.triggered.connect(self._debug_show_broken_slot)
        self.debug_menu.addAction(self.action_debug_broken)

        self.action_prune_broken = QAction("", self)
        self.action_prune_broken.triggered.connect(self._debug_prune_broken_slot)
        self.debug_menu.addAction(self.action_prune_broken)

        self.debug_menu.addSeparator()

        self.action_debug_dedup = QAction("", self)
        self.action_debug_dedup.triggered.connect(self._debug_deduplicate_vault_slot)
        self.debug_menu.addAction(self.action_debug_dedup)

        self.debug_menu.addSeparator()

        self.action_prune_orphan_workflows = QAction("", self)
        self.action_prune_orphan_workflows.triggered.connect(
            self._debug_prune_orphan_workflows_slot
        )
        self.debug_menu.addAction(self.action_prune_orphan_workflows)

        # -- Config Menu --
        self.config_menu = menubar.addMenu("")

        self.action_settings = QAction("", self)
        self.action_settings.triggered.connect(self.open_settings_slot)
        self.config_menu.addAction(self.action_settings)

        # -- Semantic Data Menu --
        self.semantic_menu = menubar.addMenu("")

        self.action_missing_semantic = QAction("", self)
        self.action_missing_semantic.triggered.connect(self.list_missing_semantic_data_slot)
        self.semantic_menu.addAction(self.action_missing_semantic)

        self.action_mismatched_semantic = QAction("", self)
        self.action_mismatched_semantic.triggered.connect(self.list_mismatched_semantic_data_slot)
        self.semantic_menu.addAction(self.action_mismatched_semantic)

        self.semantic_menu.addSeparator()

        self.action_run_stage2_selected = QAction("", self)
        self.action_run_stage2_selected.triggered.connect(self.run_stage_2_selected_slot)
        self.semantic_menu.addAction(self.action_run_stage2_selected)

        self.action_run_stage2_missing = QAction("", self)
        self.action_run_stage2_missing.triggered.connect(self.run_stage_2_all_missing_slot)
        self.semantic_menu.addAction(self.action_run_stage2_missing)

        # -- Help Menu --
        self.help_menu = menubar.addMenu("")

        self.action_about = QAction("", self)
        self.action_about.triggered.connect(self.show_about_dialog)
        self.help_menu.addAction(self.action_about)

    def _refresh_plugin_menu(self) -> None:
        """Populate the Plugins submenu with actions from loaded plugins."""
        if not hasattr(self, "plugin_submenu") or not self.plugin_manager:
            return

        self.plugin_submenu.clear()

        found_any = False
        for plugin in self.plugin_manager.plugins:
            try:
                actions = plugin.get_tool_actions(parent=self)
                if actions:
                    found_any = True
                    for action in actions:
                        self.plugin_submenu.addAction(action)
            except Exception as e:
                logger.error(f"Error loading tools from {plugin.__class__.__name__}: {e}")

        if not found_any:
            load_errors = getattr(self.plugin_manager, "load_errors", {})
            if load_errors:
                self.plugin_submenu.addAction(self.tr("Plugin Loading Errors...")).setEnabled(False)
                self.plugin_submenu.addSeparator()
                err_menu = self.plugin_submenu.addMenu(self.tr("Details"))
                for path, err in load_errors.items():
                    err_menu.addAction(f"{Path(path).name}: {err}").setEnabled(False)
            else:
                self.plugin_submenu.addAction(self.tr("No plugin actions")).setEnabled(False)

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def create_tool_bar(self) -> None:
        self.navbar = QToolBar("Navigation")
        self.navbar.setIconSize(QSize(20, 20))
        self.navbar.setMovable(False)
        from gui.theme import (
            CLR_NAV_BG, CLR_BORDER, CLR_SURFACE, CLR_SURFACE_ROW, CLR_SURFACE_HOVER,
            CLR_PRIMARY_NAV, CLR_PRIMARY_LIGHT, CLR_TEXT, CLR_TEXT_SECONDARY,
            FONT_BASE, RADIUS_SM, NAV_HEIGHT,
        )
        self.navbar.setStyleSheet(f"""
            QToolBar {{
                background-color: {CLR_NAV_BG};
                border-bottom: 1px solid {CLR_BORDER};
                padding-top: 12px;
                spacing: 2px;
            }}
            QToolButton {{
                padding: 6px 15px;
                border: 1px solid transparent;
                border-bottom: 3px solid transparent;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: 500;
                font-size: {FONT_BASE}px;
                color: {CLR_TEXT_SECONDARY};
            }}
            QToolButton:hover {{
                background-color: {CLR_SURFACE_HOVER};
            }}
            QWidget#tabContainer {{
                background-color: transparent;
                border: 1px solid transparent;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-bottom: -1px;
                margin-top: 10px;
                min-height: {NAV_HEIGHT}px;
            }}
            QWidget#tabContainer[active="true"] {{
                background-color: {CLR_SURFACE};
                border-color: {CLR_BORDER};
                border-bottom: 1px solid {CLR_SURFACE};
            }}
            QWidget#tabContainer[active="true"] QToolButton {{
                background-color: transparent;
                border: 1px solid transparent;
                color: {CLR_PRIMARY_NAV};
                font-weight: bold;
            }}
            QToolButton#mainTabBtn[active="true"] {{
                border-bottom: 3px solid {CLR_PRIMARY_NAV};
                color: {CLR_PRIMARY_NAV};
            }}
            QWidget#tabContainer QToolButton#filterBtn {{
                margin: 0px 6px;
                padding: 4px 10px;
                border: 1px solid {CLR_BORDER};
                border-radius: {RADIUS_SM}px;
                background-color: {CLR_SURFACE_ROW};
                font-size: {FONT_BASE}px;
                color: {CLR_TEXT};
            }}
            QWidget#tabContainer QToolButton#filterBtn:hover {{
                background-color: {CLR_SURFACE_HOVER};
                border-color: {CLR_BORDER};
            }}
            QWidget#tabContainer QToolButton#filterBtn:checked {{
                background-color: {CLR_PRIMARY_LIGHT};
                border: 1px solid {CLR_PRIMARY_NAV};
                color: {CLR_PRIMARY_NAV};
                font-weight: bold;
            }}
            QWidget#tabContainer QToolButton#subModeBtn {{
                background: transparent;
                border: none;
                border-bottom: 3px solid transparent;
                border-radius: 0px;
                padding: 6px 15px;
                color: {CLR_TEXT_SECONDARY};
                font-size: {FONT_BASE}px;
            }}
            QWidget#tabContainer QToolButton#subModeBtn:hover {{
                background-color: {CLR_SURFACE_HOVER};
                color: {CLR_PRIMARY_NAV};
            }}
            QWidget#tabContainer QToolButton#subModeBtn:checked {{
                color: {CLR_PRIMARY_NAV};
                border-bottom: 3px solid {CLR_PRIMARY_NAV};
                background-color: {CLR_PRIMARY_LIGHT};
                font-weight: bold;
            }}
        """)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.navbar)

        def _make_tab(icon_pixmap=None) -> tuple[QWidget, QToolButton]:
            container = QWidget()
            container.setObjectName("tabContainer")
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
            btn = QToolButton()
            btn.setObjectName("mainTabBtn")
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            if icon_pixmap:
                btn.setIcon(self.style().standardIcon(icon_pixmap))
            layout.addWidget(btn)
            return container, btn

        self.cockpit_nav_container, self.btn_cockpit = _make_tab(
            self.style().StandardPixmap.SP_ComputerIcon
        )
        self.btn_cockpit.clicked.connect(self.go_home_slot)
        self.navbar.addWidget(self.cockpit_nav_container)

        self.doc_container, self.btn_documents = _make_tab(
            self.style().StandardPixmap.SP_FileIcon
        )
        self.btn_documents.clicked.connect(lambda: self.central_stack.setCurrentIndex(1))
        self.navbar.addWidget(self.doc_container)

        self.wf_container, self.btn_workflows = _make_tab()
        self.btn_workflows.setIcon(QIcon())
        self.btn_workflows.clicked.connect(lambda: self.central_stack.setCurrentIndex(2))
        self.navbar.addWidget(self.wf_container)

        self.report_container, self.btn_reports = _make_tab(
            self.style().StandardPixmap.SP_FileDialogDetailedView
        )
        self.btn_reports.clicked.connect(lambda: self.central_stack.setCurrentIndex(3))
        self.navbar.addWidget(self.report_container)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.navbar.addWidget(spacer)

    # ── Tab navigation ────────────────────────────────────────────────────────

    def _on_tab_changed(self, index: int) -> None:
        """Update navigation UI when the central stack changes."""
        is_cockpit  = (index == 0)
        is_explorer = (index == 1)
        is_workflow = (index == 2)
        is_reporting = (index == 3)

        containers = [
            self.cockpit_nav_container,
            self.doc_container,
            self.wf_container,
            self.report_container,
        ]
        flags = [is_cockpit, is_explorer, is_workflow, is_reporting]

        for container, active in zip(containers, flags):
            container.setProperty("active", active)

        btn_flags = [
            (self.btn_cockpit,   is_cockpit),
            (self.btn_documents, is_explorer),
            (self.btn_workflows, is_workflow),
            (self.btn_reports,   is_reporting),
        ]
        for btn, active in btn_flags:
            btn.setProperty("active", active)
            btn.setChecked(active)

        for container in containers:
            container.style().unpolish(container)
            container.style().polish(container)
            for child in container.findChildren(QToolButton):
                child.style().unpolish(child)
                child.style().polish(child)

        if is_cockpit:
            self.cockpit_widget.refresh_stats()
        elif is_reporting:
            self.reporting_widget.refresh_data()
        elif is_workflow:
            self.workflow_manager.load_workflows()

        if index == 1 and hasattr(self, "list_widget"):
            if self._last_selected_uuid:
                self.list_widget.target_uuid_to_restore = self._last_selected_uuid
                self.list_widget.refresh_list(force_select_first=False)
            else:
                self.list_widget.refresh_list(force_select_first=True)

    def _toggle_filter_view(self, checked: bool) -> None:
        """Toggle visibility of the unified filter console."""
        if hasattr(self, "advanced_filter"):
            self.advanced_filter.setVisible(checked)
            if hasattr(self, "action_toggle_filter"):
                self.action_toggle_filter.setChecked(checked)

    # ── Localisation ──────────────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        """Update all UI strings for on-the-fly localisation."""
        if not hasattr(self, "file_menu"):
            return

        self.setWindowTitle("KPaperFlux v2")

        self.file_menu.setTitle(self.tr("&File"))
        self.action_import.setText(self.tr("&Import Document"))
        self.action_import_transfer.setText(self.tr("Import from Transfer"))
        self.action_scan.setText(self.tr("&Scan..."))
        self.action_print.setText(self.tr("&Print"))
        self.action_delete.setText(self.tr("&Delete Selected"))
        self.action_export.setText(self.tr("Export shown List..."))
        self.action_exit.setText(self.tr("E&xit"))

        self.view_menu.setTitle(self.tr("&View"))
        self.action_refresh.setText(self.tr("&Refresh List"))
        self.action_extra.setText(self.tr("Show Extra Data"))
        self.action_toggle_filter.setText("🗂️ " + self.tr("Filter Panel"))

        self.maintenance_menu.setTitle(self.tr("&Maintenance"))
        self.action_maintenance.setText(self.tr("Check Integrity (Orphans/Ghosts)"))
        self.action_duplicates.setText(self.tr("Find Duplicates"))
        self.action_tag_manager.setText(self.tr("Manage Tags"))

        self.tools_menu.setTitle(self.tr("&Tools"))
        self.action_purge_data.setText(self.tr("Purge All Data (Reset)"))
        self.plugin_submenu.setTitle(self.tr("External Plugins"))

        self.debug_menu.setTitle(self.tr("&Debug"))
        self.action_debug_orphans.setText(self.tr("Show Orphaned Vault Files"))
        self.action_prune_orphans.setText(self.tr("Prune Orphaned Vault Files (Console)"))
        self.action_debug_broken.setText(self.tr("Show Broken Entity References"))
        self.action_prune_broken.setText(self.tr("Prune Broken Entity References (Console)"))
        self.action_debug_dedup.setText(self.tr("Deduplicate Vault (Inhaltsbasiert)"))
        self.action_prune_orphan_workflows.setText(
            self.tr("Prune Orphaned Workflow References...")
        )

        self.config_menu.setTitle(self.tr("&Config"))
        self.action_settings.setText(self.tr("&Settings..."))

        self.semantic_menu.setTitle(self.tr("&Semantic Data"))
        self.action_missing_semantic.setText(self.tr("List Missing"))
        self.action_mismatched_semantic.setText(self.tr("List Mismatched"))
        self.action_run_stage2_selected.setText(self.tr("Run Extraction (Selected)"))
        self.action_run_stage2_missing.setText(self.tr("Process empty Documents"))

        self.help_menu.setTitle(self.tr("&Help"))
        self.action_about.setText(self.tr("&About"))

        self.btn_cockpit.setText(self.tr("Cockpit"))
        self.btn_cockpit.setToolTip(self.tr("Main overview and statistics"))
        self.btn_documents.setText(self.tr("Documents"))
        self.btn_documents.setToolTip(self.tr("Browse and manage document list"))
        self.btn_workflows.setText("🤖 " + self.tr("Workflows"))
        self.btn_reports.setText(self.tr("Reports"))

        if hasattr(self, "main_status_label") and self.main_status_label:
            self._refresh_status_bar()
