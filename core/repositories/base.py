from core.database import DatabaseManager
import sqlite3

class BaseRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.conn = db_manager.connection
