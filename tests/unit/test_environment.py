import pytest
import importlib
from pathlib import Path

def test_requirements_available():
    """
    Checks if all packages listed in requirements.txt are actually installable and importable.
    This prevents 'No module named ...' errors at runtime.
    """
    req_file = Path(__file__).parent.parent.parent / "requirements.txt"
    if not req_file.exists():
        pytest.skip("requirements.txt not found")

    with open(req_file, "r") as f:
        packages = f.readlines()

    # Mapping of pip package names to import names
    mapping = {
        "PyQt6": "PyQt6",
        "pytest": "pytest",
        "pytest-qt": "pytestqt",
        "pydantic": "pydantic",
        "google-genai": "google.genai",
        "ocrmypdf": "ocrmypdf",
        "python-dotenv": "dotenv",
        "pikepdf": "pikepdf",
        "pdf2image": "pdf2image",
        "Pillow": "PIL",
        "reportlab": "reportlab",
        "python-sane": "sane",
        "qrcode[pil]": "qrcode",
        "opencv-python-headless": "cv2",
        "numpy": "numpy"
    }

    errors = []
    for line in packages:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        # Strip versions/extras
        pkg_name = line.split(">")[0].split("=")[0].split("[")[0].strip()
        
        # Special case for qrcode[pil] -> we check 'qrcode'
        if "qrcode" in line:
            import_name = "qrcode"
        else:
            import_name = mapping.get(pkg_name, pkg_name)
        
        try:
            importlib.import_module(import_name)
        except ImportError as e:
            errors.append(f"Package '{pkg_name}' (import '{import_name}') is missing: {e}")

    if errors:
        pytest.fail("\n".join(errors))

def test_plugin_manager_captures_import_error(tmp_path):
    """
    Verify that PluginManager correctly captures and reports ImportErrors 
    instead of crashing the whole app.
    """
    from core.plugins.manager import PluginManager
    import json
    
    plugin_dir = tmp_path / "broken_plugin"
    plugin_dir.mkdir()
    
    # Create manifest
    manifest = {
        "id": "broken",
        "class_name": "BrokenPlugin",
        "entry_point": "broken.py"
    }
    with open(plugin_dir / "manifest.json", "w") as f:
        json.dump(manifest, f)
        
    # Create broken script that imports non-existent module
    with open(plugin_dir / "broken.py", "w") as f:
        f.write("import non_existent_module_xyz\nclass BrokenPlugin: pass")
        
    manager = PluginManager(plugin_dirs=[str(tmp_path)])
    manager.discover_plugins()
    
    assert len(manager.plugins) == 0
    assert str(plugin_dir) in manager.load_errors
    assert "non_existent_module_xyz" in manager.load_errors[str(plugin_dir)]
