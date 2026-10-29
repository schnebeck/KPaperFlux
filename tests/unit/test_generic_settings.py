"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_generic_settings.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Guard: code, tests and docs must not carry a particular user's
                infrastructure (private LAN addresses, host names, keyring
                folders, wake-up flag files) as defaults or examples.
------------------------------------------------------------------------------
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
# Patterns are assembled so this file does not match itself.
FORBIDDEN = [re.compile(p, re.IGNORECASE) for p in (
    r"192" + r"\.168\.", r"\b" + "ai" + r"da\b", "kwallet" + r"-query", r"/run/" + "ai" + "da",
)]
SCANNED = ["core", "gui", "plugins", "tests", "tools", "main.py", "CLAUDE.md", "README.md", "requirements.txt"]


def _files():
    for entry in SCANNED:
        path = ROOT / entry
        if path.is_file():
            yield path
        elif path.is_dir():
            for file in path.rglob("*"):
                if file.is_file() and file.suffix in {".py", ".md", ".json", ".txt", ".toml"} and "__pycache__" not in file.parts:
                    yield file


def test_no_user_specific_infrastructure() -> None:
    """Defaults, placeholders, tooltips, fixtures and docs stay generic."""
    hits = []
    for file in _files():
        text = file.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{file.relative_to(ROOT)}:{line}: {match.group(0)}")
    assert not hits, "User-specific infrastructure found:\n" + "\n".join(hits)


def test_engine_defaults_are_generic() -> None:
    """Library mode by default, no AI server override, local service and OCR defaults."""
    from core.config import AppConfig
    assert AppConfig.DEFAULT_FLUXSENSE_MODE == "library"
    assert AppConfig.DEFAULT_FLUXSENSE_URL.startswith(("http://127.0.0.1", "http://localhost"))
    assert AppConfig.DEFAULT_DOCLING_URL.startswith(("http://127.0.0.1", "http://localhost"))
