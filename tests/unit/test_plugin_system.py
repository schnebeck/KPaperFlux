
import unittest
import os
import shutil
import tempfile
import json
from pathlib import Path
from core.plugins.manager import PluginManager
from core.plugins.base import KPaperFluxPlugin

class MockPlugin(KPaperFluxPlugin):
    def get_info(self):
        return {"name": "Mock Plugin", "version": "1.0.0"}
    
    def run(self, hook, data=None):
        return f"Ran {hook}"

class TestPluginSystem(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.plugin_dir = Path(self.test_dir) / "plugins"
        self.plugin_dir.mkdir()
        
        # Create a dummy plugin
        self.mock_plugin_path = self.plugin_dir / "mock_plugin"
        self.mock_plugin_path.mkdir()
        
        manifest = {
            "name": "Mock Plugin",
            "version": "1.0.0",
            "entry_point": "main.py",
            "class_name": "MockPlugin"
        }
        with open(self.mock_plugin_path / "manifest.json", "w") as f:
            json.dump(manifest, f)
            
        with open(self.mock_plugin_path / "main.py", "w") as f:
            f.write("""
from core.plugins.base import KPaperFluxPlugin
class MockPlugin(KPaperFluxPlugin):
    def get_info(self):
        return {"name": "Mock Plugin", "version": "1.0.0"}
    def run(self, hook, data=None):
        return f"Ran {hook}"
""")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_manager_loads_plugin(self):
        manager = PluginManager(plugin_dirs=[str(self.plugin_dir)])
        manager.discover_plugins()
        self.assertEqual(len(manager.plugins), 1)
        
        plugin = manager.plugins[0]
        self.assertEqual(plugin.get_info()["name"], "Mock Plugin")
        self.assertEqual(plugin.run("test_hook"), "Ran test_hook")

if __name__ == "__main__":
    unittest.main()
