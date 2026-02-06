#!/bin/bash
set -e

echo "Running translation formatting verification..."
QT_QPA_PLATFORM=offscreen ./venv/bin/pytest tests/unit/test_translation_formatting.py

echo "Verification passed. Updating translations..."
/usr/bin/lrelease resources/l10n/de/gui_strings.ts -qm resources/l10n/de/gui_strings.qm

echo "Done."
