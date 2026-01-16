#!/bin/bash
set -e

echo "Running translation formatting verification..."
QT_QPA_PLATFORM=offscreen ./venv/bin/pytest tests/unit/test_translation_formatting.py

echo "Verification passed. Updating translations..."
/usr/bin/lrelease resources/translations/kpaperflux_de.ts -qm resources/translations/kpaperflux_de.qm

echo "Done."
