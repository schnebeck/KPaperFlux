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
import os
import argparse
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTranslator, QCoreApplication
from PyQt6.QtGui import QIcon

from core.vault import DocumentVault
from core.database import DatabaseManager
from core.pipeline import PipelineProcessor
from gui.main_window import MainWindow
from core.config import AppConfig
from core.logger import setup_logging, get_logger

# Global list to prevent QTranslator garbage collection
_translators: list[QTranslator] = []

def load_translations(app: QApplication, app_config: AppConfig) -> None:
    """
    Loads and installs system translations based on configuration.
    On first run, detects system language and persists it to config.
    Afterwards, strictly follows the configuration.

    Args:
        app: The current QApplication instance.
        app_config: The application configuration manager.
    """
    # 1. Handle First Run / Auto-Detection
    if not app_config.settings.contains(app_config.KEY_LANGUAGE):
        import os
        env_lang = os.environ.get("LANGUAGE") or os.environ.get("LANG")
        detected_lang = "en"
        if env_lang:
            detected_lang = env_lang.split(".")[0].split("_")[0]
        
        # Verify if we actually have a translation for this
        base_dir = Path(__file__).resolve().parent
        test_path = base_dir / "resources" / "l10n" / detected_lang / "gui_strings.qm"
        
        if not test_path.exists():
            detected_lang = "en"
            
        app_config.set_language(detected_lang)
        get_logger("core").info(f"First run: Language auto-detected and saved as '{detected_lang}'")

    # Note: We no longer install the translator here globally.
    # MainWindow handles the initial translation loading and subsequent 
    # hot-reloads via its _switch_language method to ensure a single 
    # source of truth for active translators.


def main() -> None:
    """
    KPaperFlux Entry Point.
    Initializes infrastructure and launches the GUI.
    """
    parser = argparse.ArgumentParser(description="KPaperFlux - Intelligent Document Organizer")
    parser.add_argument("-P", "--profile", type=str, help="Application profile for isolation (e.g. 'dev', 'tax')")
    args, unknown = parser.parse_known_args()

    app = QApplication(sys.argv)
    
    # Use profile name in App ID if provided
    app_id = "kpaperflux"
    if args.profile:
        app_id = f"kpaperflux-{args.profile}"
        
    QCoreApplication.setApplicationName(app_id)
    app.setWindowIcon(QIcon("resources/icon.png"))
    
    app_config = AppConfig(profile=args.profile)

    # Initialize Professional Logging
    setup_logging(
        level=app_config.get_log_level(),
        log_file=str(app_config.get_log_file_path()),
        component_levels=app_config.get_log_components()
    )
    logger = get_logger("core")
    logger.info(f"KPaperFlux started (Profile: {args.profile or 'default'})")

    load_translations(app, app_config)

    # 1. Initialize Infrastructure
    vault_path = app_config.get_vault_path()
    vault = DocumentVault(base_path=vault_path)

    # Database location is strictly defined by XDG AppDataLocation via AppConfig
    db_path = app_config.get_data_dir() / f"{app_id}.db"
    db = DatabaseManager(db_path=str(db_path))
    db.init_db()

    # 2. Initialize Logic
    pipeline = PipelineProcessor(vault=vault, db=db)

    # Background fetch Gemini models to populate cache for Settings
    def _bg_fetch_models():
        try:
            api_key = app_config.get_api_key()
            if api_key:
                from core.ai_analyzer import AIAnalyzer
                analyzer = AIAnalyzer(api_key, model_name=app_config.get_gemini_model())
                models = analyzer.list_models()
                if models:
                    AppConfig._cached_models = models
                    print(f"[AI] Domain-Discovery: {len(models)} Gemini models available.")
        except Exception:
            pass
            
    import threading
    threading.Thread(target=_bg_fetch_models, daemon=True).start()

    # 3. Initialize GUI (Passing profile for UI feedback)
    window = MainWindow(pipeline=pipeline, db_manager=db, app_config=app_config)
    if args.profile:
        window.setWindowTitle(f"{window.windowTitle()} [PROFILE: {args.profile.upper()}]")
        
    window.show()

    # 4. Event Loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
