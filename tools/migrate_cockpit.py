#!/usr/bin/env python3
"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tools/migrate_cockpit.py
Description:    Migration tool for renaming 'Dashboard' to 'Cockpit'.
                This script renames the configuration file and can also
                optionally update portable exchange files (*.kpfx).
------------------------------------------------------------------------------
"""

import os
import sys
import json
import shutil
from pathlib import Path

# Add project root to sys.path to access core.config if needed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from core.config import AppConfig
    CONFIG_DIR = AppConfig().get_config_dir()
except ImportError:
    # Fallback if core is not available
    if sys.platform == "win32":
        CONFIG_DIR = Path(os.environ["APPDATA"]) / "KPaperFlux"
    else:
        CONFIG_DIR = Path.home() / ".config" / "kpaperflux"

def migrate_config():
    print(f"[*] Checking configuration in: {CONFIG_DIR}")
    
    old_config = CONFIG_DIR / "dashboard_config.json"
    new_config = CONFIG_DIR / "cockpit_config.json"
    
    # Check local CWD as well (legacy dev behavior)
    cwd_config = Path("dashboard_config.json")
    
    migrated = False

    # 1. Migrate config dir
    if old_config.exists():
        if new_config.exists():
            print(f"[!] Warning: Both {old_config.name} and {new_config.name} exist.")
            print(f"    Skipping migration of {old_config.name} to avoid overwriting.")
        else:
            try:
                shutil.move(str(old_config), str(new_config))
                print(f"[+] Migrated {old_config} -> {new_config}")
                migrated = True
            except Exception as e:
                print(f"[!] Error migrating config: {e}")

    # 2. Migrate CWD config (dev only)
    if cwd_config.exists():
        if (CONFIG_DIR / "cockpit_config.json").exists():
            print(f"[!] Warning: dashboard_config.json in CWD exists but cockpit_config.json already in config dir.")
        else:
            try:
                shutil.move(str(cwd_config), str(new_config))
                print(f"[+] Migrated local-cwd {cwd_config} -> {new_config}")
                migrated = True
            except Exception as e:
                print(f"[!] Error migrating local config: {e}")

    if not migrated:
        print("[*] No legacy configuration found to migrate.")

def migrate_payloads(directory):
    """Optionally migrate technical types inside .kpfx files."""
    print(f"[*] Searching for KPFX files in: {directory}")
    kpfx_files = list(Path(directory).rglob("*.kpfx")) + list(Path(directory).rglob("*.json"))
    
    count = 0
    for p in kpfx_files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
                if '"type": "dashboard"' in content:
                    new_content = content.replace('"type": "dashboard"', '"type": "layout"')
                    with open(p, "w", encoding="utf-8") as wf:
                        wf.write(new_content)
                    print(f"[+] Updated payload type in: {p}")
                    count += 1
        except Exception:
            pass
    
    if count > 0:
        print(f"[*] Successfully updated {count} files.")
    else:
        print("[*] No files with 'dashboard' payload type found.")

if __name__ == "__main__":
    print("=== KPaperFlux Cockpit Migration Tool ===")
    migrate_config()
    
    # Ask or just do it? User said "sucht und umschreibt". 
    # I'll check common directories.
    vault_path = None
    try:
        vault_path = AppConfig().get_vault_path()
    except Exception:
        pass
        
    if vault_path and os.path.exists(vault_path):
        migrate_payloads(vault_path)
    
    print("\n[✔] Migration complete.")
