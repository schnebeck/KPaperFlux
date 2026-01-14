import sqlite3
from typing import Optional
from core.document import Document

class DatabaseManager:
    """
    Manages SQLite database connections and schema.
    """
    
    def __init__(self, db_path: str = "kpaperflux.db"):
        self.db_path = db_path
        self.connection = None
        self._connect()

    def _connect(self):
        """Establish connection to the database."""
        self.connection = sqlite3.connect(self.db_path)
        # Enable foreign keys
        self.connection.execute("PRAGMA foreign_keys = ON")

    def init_db(self):
        """Initialize the database schema."""
        create_documents_table = """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE NOT NULL,
            original_filename TEXT,
            doc_date DATE,
            sender TEXT,
            amount REAL,
            doc_type TEXT,
            phash TEXT,
            text_content TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        create_overlays_table = """
        CREATE TABLE IF NOT EXISTS overlays (
            doc_id INTEGER,
            overlay_type TEXT,
            content TEXT,
            position_x INTEGER,
            position_y INTEGER,
            FOREIGN KEY(doc_id) REFERENCES documents(id)
        );
        """
        
        with self.connection:
            self.connection.execute(create_documents_table)
            self.connection.execute(create_overlays_table)

    def insert_document(self, doc: Document) -> int:
        """
        Insert a document's metadata into the database.
        Returns the new row ID.
        """
        sql = """
        INSERT INTO documents (
            uuid, original_filename, doc_date, sender, amount, doc_type, phash, text_content
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        # Pydantic models can be converted to dict, but we need to handle Decimal manually for SQLite
        # Or let sqlite adapaters handle it? Standard python sqlite3 needs 'register_adapter' for Decimal usually,
        # or we cast to float/str. Spec says DECIMAL(10,2) but SQLite uses REAL/NUMERIC. 
        # For simplicity and robust usage, we'll store amount as float (REAL) here as specced 
        # broadly in the CREATE TABLE (REAL).
        
        amount_val = float(doc.amount) if doc.amount is not None else None
        
        values = (
            doc.uuid,
            doc.original_filename,
            doc.doc_date,
            doc.sender,
            amount_val,
            doc.doc_type,
            doc.phash,
            doc.text_content
        )
        
        cursor = self.connection.cursor()
        cursor.execute(sql, values)
        self.connection.commit()
        return cursor.lastrowid

    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
