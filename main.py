import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTranslator
from PyQt6.QtGui import QIcon

from core.vault import DocumentVault
from core.database import DatabaseManager
from core.pipeline import PipelineProcessor
from gui.main_window import MainWindow
from core.config import AppConfig


def main():
    """
    KPaperFlux Entry Point.
    Initializes infrastructure and launches the GUI.
    """
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("resources/icon.png"))
    app_config = AppConfig()

    # Load Translations
    lang = app_config.get_language()
    if lang != "en":
        translator = QTranslator()
        # Look for kpaperflux_<lang>.qm in resources/translations relative to this file
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

    # 1. Initialize Infrastructure
    # Use path from config
    vault_path = app_config.get_vault_path()
    vault = DocumentVault(base_path=vault_path)
    
    # DB Layout Migration
    import shutil
    db_filename = "kpaperflux.db"
    
    # New Standard Path
    data_dir = app_config.get_data_dir()
    db_path = data_dir / db_filename
    
    # Old Local Path
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
            # Fallback to local if move failed? Or just crash?
            # We let it standard crash later if DB can't be opened, but path is now set.
    
    # If explicit path override is ever needed, we could add it to Config.
    # For now, we strictly use the XDG data location.
    
    db = DatabaseManager(db_path=str(db_path))
    db.init_db() # Ensure tables exist

    # 2. Initialize Logic
    pipeline = PipelineProcessor(vault=vault, db=db)

    # 3. Initialize GUI
    window = MainWindow(pipeline=pipeline, db_manager=db)
    window.show()

    # 4. Event Loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
