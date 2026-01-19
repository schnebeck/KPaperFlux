import json
import os
import re
from typing import Dict, Any, List, Optional
from core.document import Document
from datetime import datetime

class MetadataNormalizer:


    # ... existing extraction helpers ...

    @staticmethod
    def _normalize_date(value: str) -> str:
        """
        Normalizes date strings to YYYY-MM-DD.
        Supports: DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD
        """
        if not value: return None
        value = str(value).strip()
        
        # Already ISO?
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            return value
            
        # DD.MM.YYYY
        match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", value)
        if match:
            d, m, y = match.groups()
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            
        # DD/MM/YYYY
        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", value)
        if match:
            d, m, y = match.groups()
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            
        # Try fuzzy parse? For now stick to strict regex for safety
        return value

    @staticmethod
    def _normalize_amount(value: Any) -> float:
        """
        Normalizes amount to float.
        Handles: "1.234,56", "1,234.56", "100 €"
        """
        if isinstance(value, (int, float)):
            return float(value)
            
        if not value:
            return 0.0
            
        s = str(value).strip()
        
        # Remove Currency Symbols
        s = re.sub(r"[€$£¥]", "", s).strip()
        s = re.sub(r"\s[A-Z]{3}$", "", s).strip() # EUR, USD suffix
        
        # Determine format
        # German: 1.234,56
        # US: 1,234.56
        
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                # German: 1.000,50
                s = s.replace(".", "").replace(",", ".")
            else:
                # US: 1,000.50
                s = s.replace(",", "")
        elif "," in s:
            # Maybe 1234,56 (DE) or 1,234 (US int)
            # Heuristic: If comma is 3rd from end? Or just assume DE if no dots?
            # Standard German: decimal comma.
            if len(s.split(",")[-1]) == 2: # "50" -> Decimal
                s = s.replace(",", ".")
            else:
                 # Check if multiple commas?
                 pass
                 # Default to replace comma with dot for simple "10,50"
                 s = s.replace(",", ".")
        
        try:
            return float(s)
        except ValueError:
            return 0.0

    @staticmethod
    def _normalize_currency(value: str) -> str:
        """Standardize currency to ISO code."""
        if not value: return "EUR"
        v = str(value).strip().upper()
        
        mapping = {
            "€": "EUR",
            "$": "USD",
            "£": "GBP",
            "¥": "JPY"
        }
        return mapping.get(v, v)
    """
    Translates raw 'semantic_data' into standardized metadata based on 'doc_type'.
    Uses 'resources/type_definitions.json' for configuration.
    """
    
    _config: Optional[Dict[str, Any]] = None
    
    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """Lazy load configuration."""
        if cls._config is None:
            path = os.path.join("resources", "type_definitions.json")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        cls._config = json.load(f)
                except Exception as e:
                    print(f"Error loading type_definitions: {e}")
                    cls._config = {"types": {}}
            else:
                cls._config = {"types": {}}
        return cls._config

    @classmethod
    def normalize_metadata(cls, doc: Document) -> Dict[str, Any]:
        """
        Extracts standardized fields for the document's type.
        Returns a dictionary { "field_id": "value", ... }
        """
        if not doc.semantic_data:
            return {}
            
        # Determine strict DocType (might be string or list in JSON)
        # We rely on doc.doc_type from DB column usually, but let's check semantic data too
        doc_type = doc.doc_type 
        if not doc_type and isinstance(doc.semantic_data, dict):
             # Fallback to Summary
             doc_type = doc.semantic_data.get("summary", {}).get("doc_type", "Other")
             
        # Normalize DocType string (handle "Invoice" vs ["Invoice"])
        if isinstance(doc_type, list):
            doc_type = doc_type[0]
            
        config = cls.get_config()
        type_def = config.get("types", {}).get(doc_type)
        
        if not type_def:
            # Try to match keys case-insensitive? Or fallback
            # For now exact match on "Invoice" etc.
            return {}
            
        result = {}
        for field_def in type_def.get("fields", []):
            field_id = field_def["id"]
            strategies = field_def.get("strategies", [])
            
            value = None
            for strategy in strategies:
                st_type = strategy.get("type")
                if st_type == "json_path":
                    value = cls._resolve_json_path(doc.semantic_data, strategy.get("path"))
                elif st_type == "fuzzy_key":
                    value = cls._find_fuzzy_key(doc.semantic_data, strategy.get("aliases", []))
                    
                if value:
                    break
            
            if value:
                # Apply Normalization
                ftype = field_def.get("type", "string")
                if ftype == "date":
                    value = cls._normalize_date(str(value))
                elif ftype == "amount":
                    value = cls._normalize_amount(value)
                elif ftype == "currency":
                    value = cls._normalize_currency(str(value))
                    
                result[field_id] = value
                
        return result

    @staticmethod
    def _resolve_json_path(data: Dict, path: str) -> Any:
        """
        Simple dot-notation resolver: "summary.invoice_number"
        Does NOT support full JsonPath syntax (arrays etc) for now, keeps it simple.
        """
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    @classmethod
    def _find_fuzzy_key(cls, data: Any, aliases: List[str]) -> Any:
        """
        Recursively searches for KeyValueBlocks where key matches one of aliases.
        """
        # We search specifically for objects looking like { "type": "key_value", "pairs": [...] }
        # Or generic traversal? Generic traversal is safer to find any "key": "value" pair if structured differently
        # But schema says KeyValueBlock has "pairs": [{"key": "...", "value": "..."}]
        
        lower_aliases = [a.lower() for a in aliases]
        
        # Generator to find all pairs
        for pair in cls._iter_kv_pairs(data):
            k = str(pair.get("key", "")).strip().lower()
            if k in lower_aliases:
                return pair.get("value")
                
        # Also check simple dict keys? (e.g. summary keys)
        # Maybe useful if AI puts it in summary under a synonymous name
        return None

    @classmethod
    def _iter_kv_pairs(cls, data: Any):
        """Recursively yield all KV pairs from 'key_value' blocks."""
        if isinstance(data, dict):
            # Check if this is a KeyValueBlock
            if data.get("type") == "key_value" and "pairs" in data:
                for p in data["pairs"]:
                    yield p
            
            # Recurse
            for value in data.values():
                yield from cls._iter_kv_pairs(value)
                
        elif isinstance(data, list):
            for item in data:
                yield from cls._iter_kv_pairs(item)

    @classmethod
    def update_field(cls, doc: Document, field_id: str, new_value: Any) -> bool:
        """
        Updates a specific normalized field in the document's semantic_data.
        Uses the FIRST json_path strategy defined for the field.
        Returns True if successful.
        """
        if not doc.semantic_data:
            doc.semantic_data = {"summary": {}} # Initialize if missing
            
        doc_type = doc.doc_type 
        if not doc_type and isinstance(doc.semantic_data, dict):
             doc_type = doc.semantic_data.get("summary", {}).get("doc_type", "Other")
        if isinstance(doc_type, list): doc_type = doc_type[0]
            
        config = cls.get_config()
        type_def = config.get("types", {}).get(doc_type)
        if not type_def: return False
        
        # Find Field Definition
        target_path = None
        for field in type_def.get("fields", []):
            if field["id"] == field_id:
                # Find Write Strategy (First json_path)
                for strategy in field.get("strategies", []):
                    if strategy.get("type") == "json_path":
                        target_path = strategy.get("path")
                        break
                break
        
        if not target_path:
            return False
            
        # Execute Update
        return cls._set_json_path(doc.semantic_data, target_path, new_value)

    @staticmethod
    def _set_json_path(data: Dict, path: str, value: Any) -> bool:
        """
        Sets a value at a nested path, creating keys if necessary.
        e.g. "summary.invoice_number" -> data["summary"]["invoice_number"] = value
        """
        parts = path.split(".")
        current = data
        
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            current = current[part]
            if not isinstance(current, dict):
                # Path conflict (e.g. trying to set children on a string)
                return False
                
        last_key = parts[-1]
        current[last_key] = value
        return True
