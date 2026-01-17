import sqlite3
import json
from typing import Optional, List
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
        # check_same_thread=False allows using the connection across threads (Worker support)
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        # Enable foreign keys
        self.connection.execute("PRAGMA foreign_keys = ON")
        # Enable WAL mode for better concurrency
        self.connection.execute("PRAGMA journal_mode = WAL")

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
                "extra_data": "TEXT", # JSON for dynamic fields
                "last_processed_at": "TEXT", # ISO format
                "export_filename": "TEXT",
                
                # Phase 45 Financials
                "gross_amount": "REAL",
                "postage": "REAL",
                "packaging": "REAL",
                "tax_rate": "REAL",
                "currency": "TEXT",
                
                # Phase 68 Locking
                "locked": "INTEGER" # Boolean (0/1)
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
            page_count, created_at, extra_data, last_processed_at, export_filename,
            gross_amount, postage, packaging, tax_rate, currency, locked
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ? , ?
        )
        """
        
        amount_val = float(doc.amount) if doc.amount is not None else None
        gross_val = float(doc.gross_amount) if doc.gross_amount is not None else None
        post_val = float(doc.postage) if doc.postage is not None else None
        pack_val = float(doc.packaging) if doc.packaging is not None else None
        tax_val = float(doc.tax_rate) if doc.tax_rate is not None else None
        
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
            json.dumps(doc.extra_data) if doc.extra_data else None,
            doc.last_processed_at,
            doc.export_filename,
            gross_val, post_val, pack_val, tax_val, doc.currency, 1 if doc.locked else 0
        )
        
        cursor = self.connection.cursor()
        cursor.execute(sql, values)
        self.connection.commit()
        return cursor.lastrowid

    def get_all_documents(self) -> List[Document]:
        """
        Retrieve all documents from the database.
        Returns a list of Document objects.
        """
        sql = "SELECT uuid, original_filename, doc_date, sender, amount, doc_type, phash, text_content, sender_address, iban, phone, tags, recipient_company, recipient_name, recipient_street, recipient_zip, recipient_city, recipient_country, sender_company, sender_name, sender_street, sender_zip, sender_city, sender_country, page_count, created_at, extra_data, last_processed_at, export_filename, gross_amount, postage, packaging, tax_rate, currency, locked FROM documents ORDER BY created_at DESC"
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
                extra_data=json.loads(row[26]) if row[26] else None,
                last_processed_at=row[27],
                export_filename=row[28],
                gross_amount=row[29],
                postage=row[30],
                packaging=row[31],
                tax_rate=row[32],
                currency=row[33],
                locked=bool(row[34]) if len(row) > 34 and row[34] is not None else False
            )
            results.append(doc)
            
        return results

    def get_document_by_uuid(self, uuid: str) -> Optional[Document]:
        """
        Retrieve a single document by its UUID.
        """
        sql = "SELECT uuid, original_filename, doc_date, sender, amount, doc_type, phash, text_content, sender_address, iban, phone, tags, recipient_company, recipient_name, recipient_street, recipient_zip, recipient_city, recipient_country, sender_company, sender_name, sender_street, sender_zip, sender_city, sender_country, page_count, created_at, extra_data, last_processed_at, export_filename, gross_amount, postage, packaging, tax_rate, currency, locked FROM documents WHERE uuid = ?"
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
                extra_data=json.loads(row[26]) if row[26] else None,
                last_processed_at=row[27],
                export_filename=row[28],
                gross_amount=row[29],
                postage=row[30],
                packaging=row[31],
                tax_rate=row[32],
                currency=row[33],
                locked=bool(row[34]) if len(row) > 34 and row[34] is not None else False
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
            "uuid", "original_filename", "doc_date", "sender",
            "doc_type", "phash", "text_content", "sender_address", "iban", "phone", "tags",
            "recipient_company", "recipient_name", "recipient_street", "recipient_zip", "recipient_city", "recipient_country",
            "sender_company", "sender_name", "sender_street", "sender_zip", "sender_city", "sender_country",
            "page_count", "created_at", "extra_data", "last_processed_at", "export_filename",
            
            # Phase 45 Financials
            "amount", "gross_amount", "postage", "packaging", "tax_rate", "currency", "locked"
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

    def search_documents(self, text_query: str = None, dynamic_filters: dict = None) -> List[Document]:
        """
        Search documents by text content/filename AND/OR dynamic JSON properties.
        
        :param text_query: Search string for text_content, original_filename, or tags (LIKE %query%).
        :param dynamic_filters: Dictionary of JSON paths to values.
               Example: {"stamps.cost_center": "100"}
               Logic: json_extract(extra_data, '$.stamps.cost_center') = '100'
        :return: List of matching Documents.
        """
        
        # Base query - MATCHES get_all_documents SCHEMA (34 columns)
        sql = "SELECT uuid, original_filename, doc_date, sender, amount, doc_type, phash, text_content, sender_address, iban, phone, tags, recipient_company, recipient_name, recipient_street, recipient_zip, recipient_city, recipient_country, sender_company, sender_name, sender_street, sender_zip, sender_city, sender_country, page_count, created_at, extra_data, last_processed_at, export_filename, gross_amount, postage, packaging, tax_rate, currency, locked FROM documents WHERE 1=1"
        values = []
        
        # Text Search
        if text_query:
            # We use a simple OR logic for text fields
            sql += " AND (text_content LIKE ? OR original_filename LIKE ? OR tags LIKE ?)"
            wildcard = f"%{text_query}%"
            values.extend([wildcard, wildcard, wildcard])
            
        # Dynamic JSON Filters
        if dynamic_filters:
            for key, value in dynamic_filters.items():
                json_path = f"$.{key}"
                sql += f" AND json_extract(extra_data, ?) = ?"
                values.extend([json_path, str(value)])
                
        # Sort desc
        sql += " ORDER BY created_at DESC"
                
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, values)
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
                    extra_data=json.loads(row[26]) if row[26] else None,
                    last_processed_at=row[27],
                    export_filename=row[28],
                    gross_amount=row[29],
                    postage=row[30],
                    packaging=row[31],
                    tax_rate=row[32],
                    currency=row[33],
                    locked=bool(row[34]) if len(row) > 34 and row[34] is not None else False
                )
                results.append(doc)
            return results
            
        except sqlite3.Error as e:
            print(f"Search Error: {e}")
            return []
            
        except sqlite3.Error as e:
            print(f"Search Error: {e}")
            return []

    def get_available_extra_keys(self) -> list[str]:
        """
        Scan all documents for unique keys in the 'extra_data' JSON.
        Returns flattened keys like 'stamps.cost_center'.
        """
        sql = "SELECT extra_data FROM documents WHERE extra_data IS NOT NULL"
        cursor = self.connection.cursor()
        keys = set()
        
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            for row in rows:
                try:
                    data = json.loads(row[0])
                    if not isinstance(data, dict):
                        continue
                        
                    # Flatten keys
                    # Supported depth: 2 levels for now (e.g. stamps.cost_center)
                    # Or generic recursion.
                    def extract_keys(obj, prefix=""):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                new_prefix = f"{prefix}.{k}" if prefix else k
                                if isinstance(v, dict):
                                     extract_keys(v, new_prefix)
                                elif isinstance(v, list):
                                     # Recurse into list items (dictionaries) to discover nested keys
                                     # e.g. stamps -> [{cost_center: 10}] -> keys: stamps, stamps.cost_center
                                     keys.add(new_prefix) # Add the list key itself
                                     for item in v:
                                         if isinstance(item, dict):
                                             extract_keys(item, new_prefix)
                                else:
                                     keys.add(new_prefix)
                                     
                    extract_keys(data)
                    
                except json.JSONDecodeError:
                    continue
                    
            return sorted(list(keys))
            
        except sqlite3.Error as e:
            print(f"Error fetching extra keys: {e}")
            return []

    def search_documents_advanced(self, query: dict) -> List[Document]:
        """
        Search documents using a structured query object.
        Supported operators: AND, OR, equals, contains, starts_with, gt, lt, gte, lte.
        """
        # Base query - MATCHES get_all_documents SCHEMA
        sql = "SELECT uuid, original_filename, doc_date, sender, amount, doc_type, phash, text_content, sender_address, iban, phone, tags, recipient_company, recipient_name, recipient_street, recipient_zip, recipient_city, recipient_country, sender_company, sender_name, sender_street, sender_zip, sender_city, sender_country, page_count, created_at, extra_data, last_processed_at, export_filename, gross_amount, postage, packaging, tax_rate, currency, locked FROM documents WHERE 1=1"
        params = []
        
        if query:
            where_clause = self._build_advanced_sql(query, params)
            if where_clause:
                sql += f" AND ({where_clause})"
                
        sql += " ORDER BY created_at DESC"
        
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, params)
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
                    extra_data=json.loads(row[26]) if row[26] else None,
                    last_processed_at=row[27],
                    export_filename=row[28],
                    gross_amount=row[29],
                    postage=row[30],
                    packaging=row[31],
                    tax_rate=row[32],
                    currency=row[33],
                    locked=bool(row[34]) if len(row) > 34 and row[34] is not None else False
                )
                results.append(doc)
            return results
        except sqlite3.Error as e:
            print(f"Advanced Search Error: {e}")
            return []

    def _build_advanced_sql(self, node: dict, params: list) -> str:
        if not node:
            return ""
            
        # Recursive Group
        if "operator" in node and "conditions" in node:
            op = node["operator"].upper()
            if op not in ["AND", "OR"]:
                op = "AND"
            
            parts = []
            for child in node["conditions"]:
                child_sql = self._build_advanced_sql(child, params)
                if child_sql:
                    parts.append(child_sql)
            
            if not parts:
                return ""
            
            separator = f" {op} "
            joined = separator.join(parts)
            return f"({joined})" if len(parts) > 1 else parts[0]
            
        # Leaf Condition
        field = node.get("field")
        op = node.get("op", "equals")
        val = node.get("value")
        negate = node.get("negate", False)
        
        if not field:
            return ""
            
        # Map Field
        col_sql = ""
        is_json_field = False
        json_pattern = ""
        
        if field.startswith("json:"):
            is_json_field = True
            key = field[5:]
            # Generate LIKE pattern for json_tree fullkey
            # e.g. key="stamps.cost_bearer" -> pattern="%stamps%cost_bearer%"
            # This handles arrays ($[0]), quotes ("key"), and separation (.)
            parts = key.split(".")
            # Escape pattern parts to avoid injection? (Parameters handled separately)
            # For typical alphanumeric keys this is fine. 
            # We construct: %part1%part2%...%
            json_pattern = "%" + "%".join(parts) + "%"
        else:
            # Prevent SQL Injection on column names via allowlist
            allowed_cols = [
                "amount", "doc_date", "sender", "tags", "doc_type", "original_filename", "created_at", 
                "recipient_name", "gross_amount", "tax_rate",
                "last_processed_at", 
                "recipient_company", "recipient_street", "recipient_city", "recipient_zip", "recipient_country",
                "sender_name", "sender_company", "sender_street", "sender_city", "sender_zip", "sender_country",
                "postage", "packaging", "currency",
                "iban", "phone", "page_count", "export_filename", "text_content", "uuid"
            ]
            if field in allowed_cols:
                col_sql = field
            else:
                return "" # Ignore unknown columns
                
        # Map Operator
        sql_op = "="
        if op == "contains":
            sql_op = "LIKE"
            val = f"%{val}%"
        elif op == "starts_with":
            sql_op = "LIKE"
            val = f"{val}%"
        elif op == "gt":
            sql_op = ">"
        elif op == "lt":
            sql_op = "<"
        elif op == "gte":
            sql_op = ">="
        elif op == "lte":
            sql_op = "<="
        
        # Handle special IS EMPTY / IS NOT EMPTY
        if op == "is_empty":
            if is_json_field:
                # Recursive NOT EXISTS
                return f"NOT EXISTS (SELECT 1 FROM json_tree(documents.extra_data) WHERE fullkey LIKE ? AND value != '' AND value IS NOT NULL)"
            else:
                return f"({col_sql} IS NULL OR {col_sql} = '')"
        elif op == "is_not_empty":
            if is_json_field:
                return f"EXISTS (SELECT 1 FROM json_tree(documents.extra_data) WHERE fullkey LIKE ? AND value != '' AND value IS NOT NULL)"
            else:
                return f"({col_sql} IS NOT NULL AND {col_sql} != '')"
        elif op in ["in", "is_in_list"]:
             # List Operator: val should be a list of strings/ints
             if not isinstance(val, list) or not val:
                 # Empty list -> Matches Nothing
                 return "1=0"
             
             if is_json_field:
                 # JSON Array containment or direct value?
                 # Assuming direct value check against list
                 # We construct multiple LIKE ? OR ... 
                 # OR better: EXISTS ... AND value IN (?,?,?)
                 # SQLite json_tree value is string/num.
                 placeholders = ",".join(["?"] * len(val))
                 params.append(json_pattern)
                 params.extend(val)
                 return f"EXISTS (SELECT 1 FROM json_tree(documents.extra_data) WHERE fullkey LIKE ? AND value IN ({placeholders}))"
             else:
                 placeholders = ",".join(["?"] * len(val))
                 params.extend(val)
                 return f"{col_sql} IN ({placeholders})"
            
        sql = f"{col_sql} {sql_op} ?"
        if is_json_field:
             # Logic for JSON...
             if op in ["is_empty", "is_not_empty"]:
                  params.append(json_pattern)
             else:
                  params.append(json_pattern)
                  params.append(val)
                  sql = f"EXISTS (SELECT 1 FROM json_tree(documents.extra_data) WHERE fullkey LIKE ? AND value {sql_op} ?)"

        else:
             params.append(val)

        if negate:
             return f"NOT ({sql})"
        return sql

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
