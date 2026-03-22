"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           conftest.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Code
Description:    Root pytest configuration. Prevents accidental collection of
                dev scripts outside the tests/ directory.
------------------------------------------------------------------------------
"""

collect_ignore_glob = ["scripts/*.py", "devel/*.py", "tools/*.py"]
