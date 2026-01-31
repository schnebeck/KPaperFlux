"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           main.py
Version:        1.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Gemini 3pro
Description:    Application entry point. Initializes the Qt environment,
                loads translations, and sets up core infrastructure components
                (Vault, Database, Pipeline) before launching the main window.
------------------------------------------------------------------------------
"""

import sys
import shutil
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTranslator
from PyQt6.QtGui import QIcon

from core.vault import DocumentVault
from core.database import DatabaseManager
from core.pipeline import PipelineProcessor
from gui.main_window import MainWindow
from core.config import AppConfig


def migrate_database(app_config: AppConfig) -> Path:
    """
    Handles migration of the database file from local path to XDG data directory.

    Args:
        app_config: The application configuration manager.

    Returns:
        The resolved path to the database file.
    """
    db_filename = "kpaperflux.db"
    data_dir = app_config.get_data_dir()
    db_path = data_dir / db_filename
    local_db_path = Path(".").resolve() / db_filename

    if local_db_path.exists() and not db_path.exists():
        print(f"Migrating Database from {local_db_path} to {db_path}...")
        try:
            shutil.move(str(local_db_path), str(db_path))
            print("Database migration successful.")

            # Move WAL/SHM files if they exist (SQLite temporary files)
            for ext in ["-wal", "-shm"]:
                wal_src = local_db_path.with_name(db_filename + ext)
                wal_dst = db_path.with_name(db_filename + ext)
                if wal_src.exists():
                    shutil.move(str(wal_src), str(wal_dst))
        except Exception as e:
            print(f"Error migrating database: {e}")
            # Fallback will be handled by returning the intended path (which might not exist)

    return db_path


def load_translations(app: QApplication, app_config: AppConfig) -> None:
    """
    Loads and installs system translations based on configuration.

    Args:
        app: The current QApplication instance.
        app_config: The application configuration manager.
    """
    lang = app_config.get_language()
    if lang != "en":
        translator = QTranslator()
        base_dir = Path(__file__).resolve().parent
        qm_path = base_dir / "resources" / "translations" / f"kpaperflux_{lang}.qm"

        if qm_path.exists():
            if translator.load(str(qm_path)):
                app.installTranslator(translator)
                print(f"Loaded translation: {qm_path}")
            else:
                print(f"Failed to load translation: {qm_path}")
        else:
            print(f"Translation file not found: {qm_path}")


def main() -> None:
    """
    KPaperFlux Entry Point.
    Initializes infrastructure and launches the GUI.
    """
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("resources/icon.png"))
    app_config = AppConfig()

    load_translations(app, app_config)

    # 1. Initialize Infrastructure
    vault_path = app_config.get_vault_path()
    vault = DocumentVault(base_path=vault_path)

    db_path = migrate_database(app_config)
    db = DatabaseManager(db_path=str(db_path))
    db.init_db()

    # 2. Initialize Logic
    pipeline = PipelineProcessor(vault=vault, db=db)

    # 3. Initialize GUI
    window = MainWindow(pipeline=pipeline, db_manager=db)
    window.show()

    # 4. Event Loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
