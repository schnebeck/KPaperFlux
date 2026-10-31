"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/paths.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Locations of bundled files, independent of the working
                directory the application is started from.
------------------------------------------------------------------------------
"""
from pathlib import Path

PROJECT_DIR: Path = Path(__file__).resolve().parent.parent
RESOURCES_DIR: Path = PROJECT_DIR / "resources"
