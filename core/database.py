import sqlite3
import json
from typing import Optional
from decimal import Decimal
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
            
            # Schema Migration: Add new columns if valid
            # We check columns dynamically
            cursor = self.connection.cursor()
            cursor.execute("PRAGMA table_info(documents)")
            existing_columns = [row[1] for row in cursor.fetchall()]
            
            new_columns = {
                "sender_address": "TEXT",
                "iban": "TEXT",
                "phone": "TEXT",
                "tags": "TEXT",
                "recipient_company": "TEXT",
                "recipient_name": "TEXT",
                "recipient_street": "TEXT",
                "recipient_zip": "TEXT",
                "recipient_city": "TEXT",
                "recipient_country": "TEXT",
                "sender_company": "TEXT",
                "sender_name": "TEXT",
                "sender_street": "TEXT",
                "sender_zip": "TEXT",
                "sender_city": "TEXT",
                "sender_country": "TEXT",
                "page_count": "INTEGER",
                "created_at_iso": "TEXT", # Kept for compatibility if used elsewhere or future
                "extra_data": "TEXT" # JSON for dynamic fields
            }
            
            for col_name, col_type in new_columns.items():
                if col_name not in existing_columns:
                    print(f"Migrating DB: Adding column '{col_name}'")
                    self.connection.execute(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}")

    def insert_document(self, doc: Document) -> int:
        """
        Insert a document's metadata into the database.
        Returns the new row ID.
        """
        sql = """
        INSERT OR REPLACE INTO documents (
            uuid, original_filename, doc_date, sender, amount, doc_type, phash, text_content,
            sender_address, iban, phone, tags,
            recipient_company, recipient_name, recipient_street, recipient_zip, recipient_city, recipient_country,
            sender_company, sender_name, sender_street, sender_zip, sender_city, sender_country,
            page_count, created_at, extra_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        amount_val = float(doc.amount) if doc.amount is not None else None
        
        values = (
            doc.uuid,
            doc.original_filename,
            doc.doc_date.isoformat() if doc.doc_date else None,
            doc.sender,
            amount_val,
            doc.doc_type,
            doc.phash,
            doc.text_content,
            doc.sender_address,
            doc.iban,
            doc.phone,
            doc.tags,
            doc.recipient_company, doc.recipient_name, doc.recipient_street, doc.recipient_zip, doc.recipient_city, doc.recipient_country,
            doc.sender_company, doc.sender_name, doc.sender_street, doc.sender_zip, doc.sender_city, doc.sender_country,
            doc.page_count,
            doc.created_at,
            json.dumps(doc.extra_data) if doc.extra_data else None
        )
        
        cursor = self.connection.cursor()
        cursor.execute(sql, values)
        self.connection.commit()
        return cursor.lastrowid

    def get_all_documents(self) -> list[Document]:
        """
        Retrieve all documents from the database.
        Returns a list of Document objects.
        """
        sql = "SELECT uuid, original_filename, doc_date, sender, amount, doc_type, phash, text_content, sender_address, iban, phone, tags, recipient_company, recipient_name, recipient_street, recipient_zip, recipient_city, recipient_country, sender_company, sender_name, sender_street, sender_zip, sender_city, sender_country, page_count, created_at, extra_data FROM documents"
        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            doc = Document(
                uuid=row[0],
                original_filename=row[1],
                doc_date=row[2], 
                sender=row[3],
                amount=row[4],
                doc_type=row[5],
                phash=row[6],
                text_content=row[7],
                sender_address=row[8],
                iban=row[9],
                phone=row[10],
                tags=row[11],
                recipient_company=row[12], recipient_name=row[13], recipient_street=row[14], recipient_zip=row[15], recipient_city=row[16], recipient_country=row[17],
                sender_company=row[18], sender_name=row[19], sender_street=row[20], sender_zip=row[21], sender_city=row[22], sender_country=row[23],
                page_count=row[24], created_at=row[25],
                extra_data=json.loads(row[26]) if row[26] else None
            )
            results.append(doc)
            
        return results

    def get_document_by_uuid(self, uuid: str) -> Optional[Document]:
        """
        Retrieve a single document by its UUID.
        """
        sql = "SELECT uuid, original_filename, doc_date, sender, amount, doc_type, phash, text_content, sender_address, iban, phone, tags, recipient_company, recipient_name, recipient_street, recipient_zip, recipient_city, recipient_country, sender_company, sender_name, sender_street, sender_zip, sender_city, sender_country, page_count, created_at, extra_data FROM documents WHERE uuid = ?"
        cursor = self.connection.cursor()
        cursor.execute(sql, (uuid,))
        row = cursor.fetchone()
        
        if row:
            return Document(
                uuid=row[0],
                original_filename=row[1],
                doc_date=row[2],
                sender=row[3],
                amount=row[4],
                doc_type=row[5],
                phash=row[6],
                text_content=row[7],
                sender_address=row[8],
                iban=row[9],
                phone=row[10],
                tags=row[11],
                recipient_company=row[12], recipient_name=row[13], recipient_street=row[14], recipient_zip=row[15], recipient_city=row[16], recipient_country=row[17],
                sender_company=row[18], sender_name=row[19], sender_street=row[20], sender_zip=row[21], sender_city=row[22], sender_country=row[23],
                page_count=row[24], created_at=row[25],
                extra_data=json.loads(row[26]) if row[26] else None
            )
        return None

    def update_document_metadata(self, uuid: str, updates: dict) -> bool:
        """
        Update specific fields of a document.
        :param uuid: The document UUID
        :param updates: Dictionary of field_name -> new_value
        :return: True if successful
        """
        if not updates:
            return False
            
        # Security: Allow-list columns to prevent injection
        allowed_columns = {
            "original_filename", "doc_date", "sender", "amount", "doc_type", 
            "phash", "text_content", "sender_address", "iban", "phone", "tags",
            "recipient_company", "recipient_name", "recipient_street", "recipient_zip", "recipient_city", "recipient_country",
            "sender_company", "sender_name", "sender_street", "sender_zip", "sender_city", "sender_country",
            "page_count", "created_at", "extra_data"
        }
        
        set_clauses = []
        values = []
        
        for key, value in updates.items():
            if key not in allowed_columns:
                print(f"Warning: Attempt to update invalid column '{key}'")
                continue
            
            # Serialize extra_data if dictionary
            if key == "extra_data" and isinstance(value, dict):
                value = json.dumps(value)
                
            set_clauses.append(f"{key} = ?")
            values.append(value)
            
        if not set_clauses:
            return False
            
        values.append(uuid)
        sql = f"UPDATE documents SET {', '.join(set_clauses)} WHERE uuid = ?"
        
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, values)
            self.connection.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            print(f"Database Error updating {uuid}: {e}")
            return False

    def delete_document(self, uuid: str) -> bool:
        """
        Delete a document by its UUID.
        Returns True if a row was deleted, False otherwise.
        """
        sql = "DELETE FROM documents WHERE uuid = ?"
        cursor = self.connection.cursor()
        cursor.execute(sql, (uuid,))
        self.connection.commit()
        return cursor.rowcount > 0

    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
