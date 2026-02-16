"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/plugins/manager.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Manages lifecycle of plugins: discovery, loading, and 
                execution of hooks. Supports multiple plugin directories.
------------------------------------------------------------------------------
"""

import os
import json
import importlib.util
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from core.plugins.base import KPaperFluxPlugin, ApiContext

class PluginManager:
    """
    Handles discovery and loading of KPaperFlux plugins.
    """
    def __init__(self, plugin_dirs: List[str] = None, api_context: ApiContext = None):
        self.plugin_dirs = plugin_dirs or []
        self.api = api_context or ApiContext()
        self.plugins: List[KPaperFluxPlugin] = []
        self._loaded_modules = {}
        self.load_errors = {} # path -> error_msg
        self.scanned_dirs = []

    def discover_plugins(self) -> int:
        """
        Scans all registered directories for valid plugins.
        A valid plugin has a manifest.json and an entry point script.
        
        Returns:
            The number of plugins successfully loaded.
        """
        self.plugins = []
        self.load_errors = {}
        self.scanned_dirs = []
        for d in self.plugin_dirs:
            p_dir = Path(d).resolve()
            self.scanned_dirs.append(str(p_dir))
            if not p_dir.exists():
                continue
            
            for sub_dir in p_dir.iterdir():
                if sub_dir.is_dir():
                    manifest_path = sub_dir / "manifest.json"
                    if manifest_path.exists():
                        self._load_plugin(sub_dir, manifest_path)
        
        return len(self.plugins)

    def _load_plugin(self, plugin_path: Path, manifest_path: Path):
        """
        Loads a single plugin based on its manifest.
        """
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            entry_point = manifest.get("entry_point", "main.py")
            class_name = manifest.get("class_name")
            
            if not class_name:
                print(f"[PluginManager] Error: manifest.json in {plugin_path} missing 'class_name'.")
                return

            script_path = plugin_path / entry_point
            if not script_path.exists():
                print(f"[PluginManager] Error: entry point {entry_point} not found in {plugin_path}.")
                return

            # Dynamic Import
            module_name = f"plugin_{plugin_path.name}"
            spec = importlib.util.spec_from_file_location(module_name, str(script_path))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                
                plugin_class = getattr(module, class_name)
                if issubclass(plugin_class, KPaperFluxPlugin) or any(base.__name__ == 'KPaperFluxPlugin' for base in plugin_class.__mro__):
                    instance = plugin_class(self.api)
                    
                    # --- l10n Support ---
                    lang = self.api.config.get_language() if self.api.config else "en"
                    if lang != "en":
                        l10n_path = plugin_path / "l10n" / lang / "messages.qm"
                        if l10n_path.exists():
                            instance.load_translator(str(l10n_path))
                            print(f"[PluginManager] Loaded {lang} translations for: {plugin_path.name}")
                    
                    self.plugins.append(instance)
                    print(f"[PluginManager] Successfully loaded plugin: {manifest.get('name', plugin_path.name)}")
                else:
                    print(f"[PluginManager] Error: {class_name} in {plugin_path} does not inherit from KPaperFluxPlugin.")
                    print(f"[PluginManager] Debug: Bases are {[base.__name__ for base in plugin_class.__bases__]}")
                    
        except Exception as e:
            error_msg = f"Critical error loading: {e}"
            self.load_errors[str(plugin_path)] = error_msg
            print(f"[PluginManager] {error_msg} from {plugin_path}")

    def trigger_hook(self, hook: str, data: Any = None) -> List[Any]:
        """
        Triggers a hook on all loaded plugins.
        
        Returns:
            A list of results from each plugin.
        """
        results = []
        for plugin in self.plugins:
            try:
                res = plugin.run(hook, data)
                if res is not None:
                    results.append(res)
            except Exception as e:
                print(f"[PluginManager] Error running hook '{hook}' on plugin {plugin.__class__.__name__}: {e}")
        return results
