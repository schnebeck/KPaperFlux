"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           conftest.py
Version:        1.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Code
Description:    Root pytest configuration. Prevents accidental collection of
                dev scripts outside the tests/ directory and isolates the test
                run from the user's real configuration and data: QSettings and
                QStandardPaths resolve XDG locations into a temporary
                directory, and FluxSense never reads the user's config.
------------------------------------------------------------------------------
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

collect_ignore_glob = ["scripts/*.py", "devel/*.py", "tools/*.py"]

# Must run before any test module creates a QSettings / QStandardPaths lookup.
_TEST_ROOT: Path = Path(tempfile.mkdtemp(prefix="kpaperflux-tests-"))
for _var, _sub in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
    os.environ[_var] = str(_TEST_ROOT / _sub)
os.environ["FLUXSENSE_CONFIG"] = str(_TEST_ROOT / "fluxsense-config.toml")
atexit.register(shutil.rmtree, _TEST_ROOT, True)
