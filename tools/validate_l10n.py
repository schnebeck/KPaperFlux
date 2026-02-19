#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import os
import sys
from pathlib import Path

def validate_ts_files():
    """
    Checks all .ts files in the resources/l10n directory for XML integrity.
    """
    project_root = Path(__file__).parent.parent
    l10n_dir = project_root / "resources" / "l10n"
    
    if not l10n_dir.exists():
        print(f"Error: Localization directory not found at {l10n_dir}")
        return False

    ts_files = list(l10n_dir.rglob("*.ts"))
    if not ts_files:
        print("No .ts files found to validate.")
        return True

    errors_found = False
    print(f"Validating {len(ts_files)} localization files...")

    for ts_path in ts_files:
        rel_path = ts_path.relative_to(project_root)
        try:
            # 1. Check if file is empty or missing closing tag (fast check)
            content = ts_path.read_text(encoding="utf-8").strip()
            if not content:
                print(f"[FAIL] {rel_path}: File is empty.")
                errors_found = True
                continue
            
            if not content.endswith("</TS>"):
                print(f"[FAIL] {rel_path}: Missing closing </TS> tag. File might be truncated.")
                errors_found = True
                continue

            # 2. Strict XML Parsing
            ET.parse(ts_path)
            print(f"[ OK ] {rel_path}")

        except ET.ParseError as e:
            print(f"[FAIL] {rel_path}: XML Syntax Error: {e}")
            errors_found = True
        except Exception as e:
            print(f"[FAIL] {rel_path}: Unexpected error: {e}")
            errors_found = True

    if errors_found:
        print("\nValidation FAILED. Please repair the corrupted .ts files.")
        return False
    
    print("\nValidation SUCCESSFUL. All localization files are healthy.")
    return True

if __name__ == "__main__":
    if not validate_ts_files():
        sys.exit(1)
    sys.exit(0)
