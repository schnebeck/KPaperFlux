"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/metadata_normalizer.py
Version:        1.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Standardizes raw semantic metadata into structured fields based
                on document types and configurable definitions. Handles type-specific
                normalization for dates, amounts, and currencies.
------------------------------------------------------------------------------
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Generator

from core.document import Document


class MetadataNormalizer:
    """
    Translates raw 'semantic_data' into standardized metadata based on 'doc_type'.
    Uses 'resources/type_definitions.json' for configuration.
    """

    _config: Optional[Dict[str, Any]] = None

    @staticmethod
    def _normalize_date(value: str) -> Optional[str]:
        """
        Normalizes date strings to YYYY-MM-DD.
        Supports: DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD.

        Args:
            value: The raw date string to normalize.

        Returns:
            The normalized date string in ISO format or original if parsing fails.
        """
        if not value:
            return None
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

        return value

    @staticmethod
    def _normalize_amount(value: Any) -> float:
        """
        Normalizes amount values to float.
        Handles: "1.234,56", "1,234.56", "100 €".

        Args:
            value: The raw amount value (string, int, or float).

        Returns:
            The normalized float amount.
        """
        if isinstance(value, (int, float)):
            return float(value)

        if not value:
            return 0.0

        s = str(value).strip()

        # Remove Currency Symbols
        s = re.sub(r"[€$£¥]", "", s).strip()
        s = re.sub(r"\s[A-Z]{3}$", "", s).strip()  # EUR, USD suffix

        # Determine format (German: 1.234,56 vs US: 1,234.56)
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                # German: 1.000,50
                s = s.replace(".", "").replace(",", ".")
            else:
                # US: 1,000.50
                s = s.replace(",", "")
        elif "," in s:
            # Heuristic: If comma is 3rd from end? Or just assume DE if no dots.
            if len(s.split(",")[-1]) == 2:  # "50" -> Decimal
                s = s.replace(",", ".")
            else:
                s = s.replace(",", ".")

        try:
            return float(s)
        except ValueError:
            return 0.0

    @staticmethod
    def _normalize_currency(value: str) -> str:
        """
        Standardize currency to ISO code.

        Args:
            value: The raw currency string.

        Returns:
            The ISO 4217 currency code.
        """
        if not value:
            return "EUR"
        v = str(value).strip().upper()

        mapping = {
            "€": "EUR",
            "$": "USD",
            "£": "GBP",
            "¥": "JPY"
        }
        return mapping.get(v, v)

    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """
        Lazy load configuration from type_definitions.json.

        Returns:
            The configuration dictionary.
        """
        if cls._config is None:
            # Try to resolve relative to this file or root
            path = os.path.join("resources", "type_definitions.json")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        cls._config = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Error loading type_definitions: {e}")
                    cls._config = {"types": {}}
            else:
                cls._config = {"types": {}}
        return cls._config

    @classmethod
    def normalize_metadata(cls, doc: Document) -> Dict[str, Any]:
        """
        Extracts standardized fields for the document's type.

        Args:
            doc: The Document object to normalize.

        Returns:
            A dictionary containing the standardized field values.
        """
        if not doc.semantic_data:
            return {}

        # Determine DocType (favor direct field over nested summary)
        doc_type = doc.doc_type
        if not doc_type and isinstance(doc.semantic_data, dict):
            summary = doc.semantic_data.get("summary", {})
            if isinstance(summary, dict):
                doc_type = summary.get("doc_type", "Other")

        # Normalize DocType string (handle single or list)
        if isinstance(doc_type, list) and doc_type:
            doc_type = str(doc_type[0])
        elif doc_type:
            doc_type = str(doc_type)
        else:
            doc_type = "Other"

        config = cls.get_config()
        type_def = config.get("types", {}).get(doc_type)

        if not type_def:
            return {}

        result: Dict[str, Any] = {}
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
    def _resolve_json_path(data: Dict[str, Any], path: str) -> Any:
        """
        Simple dot-notation resolver.

        Args:
            data: The data dictionary.
            path: Dot-separated path string.

        Returns:
            The resolved value or None.
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
        Recursive search for keys matching aliases within the data structure.

        Args:
            data: The data to search.
            aliases: List of keys to find.

        Returns:
            The associated value if found, else None.
        """
        lower_aliases = [a.lower() for a in aliases]

        for pair in cls._iter_kv_pairs(data):
            k = str(pair.get("key", "")).strip().lower()
            if k in lower_aliases:
                return pair.get("value")

        return None

    @classmethod
    def _iter_kv_pairs(cls, data: Any) -> Generator[Dict[str, Any], None, None]:
        """
        Recursively yields KV pairs from 'key_value' blocks.

        Args:
            data: The data structure to traverse.

        Yields:
            A pair dictionary containing 'key' and 'value'.
        """
        if isinstance(data, dict):
            if data.get("type") == "key_value" and "pairs" in data:
                pairs = data.get("pairs")
                if isinstance(pairs, list):
                    for p in pairs:
                        if isinstance(p, dict):
                            yield p

            for value in data.values():
                yield from cls._iter_kv_pairs(value)

        elif isinstance(data, list):
            for item in data:
                yield from cls._iter_kv_pairs(item)

    @classmethod
    def update_field(cls, doc: Document, field_id: str, new_value: Any) -> bool:
        """
        Updates a specific normalized field in the document's semantic_data.

        Args:
            doc: The Document object to update.
            field_id: The ID of the field to update.
            new_value: The new value for the field.

        Returns:
            True if the update was successful.
        """
        if not doc.semantic_data:
            doc.semantic_data = {"summary": {}}

        doc_type = doc.doc_type
        if not doc_type and isinstance(doc.semantic_data, dict):
            summary = doc.semantic_data.get("summary", {})
            if isinstance(summary, dict):
                doc_type = summary.get("doc_type", "Other")

        if isinstance(doc_type, list) and doc_type:
            doc_type = str(doc_type[0])
        elif doc_type:
            doc_type = str(doc_type)
        else:
            doc_type = "Other"

        config = cls.get_config()
        type_def = config.get("types", {}).get(doc_type) or config.get("types", {}).get("Other")
        if not type_def:
            return False

        # Find Field Definition
        target_path = None
        for field in type_def.get("fields", []):
            if field["id"] == field_id:
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
    def _set_json_path(data: Dict[str, Any], path: str, value: Any) -> bool:
        """
        Sets a value at a nested path, creating sub-dicts if necessary.

        Args:
            data: The data dictionary to modify.
            path: Dot-separated path string.
            value: The value to set.

        Returns:
            True if successful.
        """
        parts = path.split(".")
        current = data

        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
            if not isinstance(current, dict):
                return False

        last_key = parts[-1]
        current[last_key] = value
        return True
