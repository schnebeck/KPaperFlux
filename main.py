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
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTranslator, QCoreApplication
from PyQt6.QtGui import QIcon

from core.vault import DocumentVault
from core.database import DatabaseManager
from core.pipeline import PipelineProcessor
from gui.main_window import MainWindow
from core.config import AppConfig


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
    QCoreApplication.setApplicationName("kpaperflux")
    app.setWindowIcon(QIcon("resources/icon.png"))
    
    app_config = AppConfig()

    load_translations(app, app_config)

    # 1. Initialize Infrastructure
    vault_path = app_config.get_vault_path()
    vault = DocumentVault(base_path=vault_path)

    # Database location is now strictly defined by XDG AppDataLocation via AppConfig
    db_path = app_config.get_data_dir() / "kpaperflux.db"
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
