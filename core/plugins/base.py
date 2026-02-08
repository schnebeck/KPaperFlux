"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/plugins/base.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Defines base classes for the KPaperFlux plugin system,
                including the KPaperFluxPlugin base and the ApiContext bridge.
------------------------------------------------------------------------------
"""

from typing import Any, Dict, List, Optional
from pathlib import Path

class ApiContext:
    """
    Bridge object providing plugins with controlled access to KPaperFlux core.
    """
    def __init__(self, db=None, vault=None, config=None, rules=None, main_window=None):
        self.db = db
        self.vault = vault
        self.config = config
        self.rules = rules
        self.main_window = main_window
        
        # Repositories (if db available)
        if db:
            from core.repositories import LogicalRepository, PhysicalRepository
            self.logical_repo = LogicalRepository(db)
            self.physical_repo = PhysicalRepository(db)
        else:
            self.logical_repo = None
            self.physical_repo = None

class KPaperFluxPlugin:
    """
    Abstract base class for all KPaperFlux plugins.
    """
    def __init__(self, api: ApiContext):
        self.api = api

    def get_info(self) -> Dict[str, Any]:
        """
        Returns metadata about the plugin.
        Should be overridden by subclasses or provided via manifest.json.
        """
        return {
            "name": "Base Plugin",
            "version": "0.0.0",
            "author": "Unknown",
            "description": "",
            "hooks": []
        }

    def run(self, hook: str, data: Any = None) -> Any:
        """
        Main execution point for the plugin. Called by the PluginManager.
        
        Args:
            hook: The name of the event/hook being triggered.
            data: Optional data associated with the hook.
            
        Returns:
            Status or result of the plugin execution.
        """
        pass

    def get_settings_widget(self, parent=None):
        """
        Optional: Returns a QWidget for the settings dialog.
        Requires PyQt6 imports in the subclass.
        """
        return None

    def get_tool_actions(self, parent=None) -> List[Any]:
        """
        Optional: Returns a list of QAction objects to be added to the 'Tools' menu.
        Requires PyQt6 imports in the subclass.
        """
        return []
