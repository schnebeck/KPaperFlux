"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/vocabulary.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Manages controlled vocabulary for document types and tags.
                Provides normalization and alias mapping (synonyms) using 
                persistent storage via QSettings.
------------------------------------------------------------------------------
"""

import json
from typing import Dict, List, Optional, Set

from PyQt6.QtCore import QSettings


class VocabularyManager:
    """
    Manages controlled vocabulary for Document Types and Tags,
    including alias (synonym) mapping for normalization.
    """

    def __init__(self) -> None:
        """Initializes the VocabularyManager and loads existing settings."""
        self._types: Set[str] = set()
        self._tags: Set[str] = set()
        self._type_aliases: Dict[str, str] = {}  # Alias -> Target (Target must be in _types)
        self._tag_aliases: Dict[str, str] = {}  # Alias -> Target (Target must be in _tags)

        self.load()

    def load(self) -> None:
        """Load vocabulary from QSettings."""
        settings = QSettings("KPaperFlux", "Vocabulary")

        # Load Types
        types_list = settings.value("types", [], type=list)
        self._types = {str(t) for t in types_list if t}

        # Load Tags
        tags_list = settings.value("tags", [], type=list)
        self._tags = {str(t) for t in tags_list if t}

        # Load Aliases (Stored as JSON string for complex structure support)
        type_aliases_json = str(settings.value("type_aliases", "{}", type=str))
        try:
            self._type_aliases = json.loads(type_aliases_json)
        except json.JSONDecodeError:
            self._type_aliases = {}

        tag_aliases_json = str(settings.value("tag_aliases", "{}", type=str))
        try:
            self._tag_aliases = json.loads(tag_aliases_json)
        except json.JSONDecodeError:
            self._tag_aliases = {}

        # Ensure defaults if empty
        if not self._types:
            self._seed_defaults()

    def save(self) -> None:
        """Save vocabulary to QSettings."""
        settings = QSettings("KPaperFlux", "Vocabulary")

        settings.setValue("types", sorted(list(self._types)))
        settings.setValue("tags", sorted(list(self._tags)))
        settings.setValue("type_aliases", json.dumps(self._type_aliases))
        settings.setValue("tag_aliases", json.dumps(self._tag_aliases))

    def _seed_defaults(self) -> None:
        """Add some default common document types and aliases."""
        defaults = ["Invoice", "Contract", "Receipt", "Letter", "Statement", "Prescription", "Other"]
        self._types.update(defaults)

        # Seed some logical aliases (German -> English basics)
        self._type_aliases["Rechnung"] = "Invoice"
        self._type_aliases["Quittung"] = "Receipt"
        self._type_aliases["Vertrag"] = "Contract"
        self._type_aliases["Brief"] = "Letter"

        self.save()

    # --- Type Management ---

    def get_all_types(self) -> List[str]:
        """
        Returns all registered document types.

        Returns:
            A sorted list of unique type names.
        """
        return sorted(list(self._types))

    def add_type(self, type_name: str) -> None:
        """
        Registers a new document type.

        Args:
            type_name: The name of the document type to add.
        """
        if type_name:
            self._types.add(type_name)
            self.save()

    def remove_type(self, type_name: str) -> None:
        """
        Removes a document type and its associated aliases.

        Args:
            type_name: The name of the type to remove.
        """
        if type_name in self._types:
            self._types.remove(type_name)

            # Clean up aliases pointing to this type
            to_remove = [k for k, v in self._type_aliases.items() if v == type_name]
            for k in to_remove:
                del self._type_aliases[k]

            self.save()

    def add_type_alias(self, alias: str, target: str) -> None:
        """
        Adds an alias for a document type. Automatically adds the target type if needed.

        Args:
            alias: The visual alias (synonym).
            target: The normalized target type name.
        """
        if not alias or not target:
            return

        if target not in self._types:
            self.add_type(target)

        self._type_aliases[alias] = target
        self.save()

    def remove_type_alias(self, alias: str) -> None:
        """
        Removes a type alias.

        Args:
            alias: The alias to remove.
        """
        if alias in self._type_aliases:
            del self._type_aliases[alias]
            self.save()

    def get_type_aliases(self) -> Dict[str, str]:
        """
        Returns all registered type aliases.

        Returns:
            A dictionary of {alias: target}.
        """
        return self._type_aliases

    # --- Tag Management ---

    def get_all_tags(self) -> List[str]:
        """
        Returns all registered user tags.

        Returns:
            A sorted list of unique tag names.
        """
        return sorted(list(self._tags))

    def add_tag(self, tag_name: str) -> None:
        """
        Registers a new user tag.

        Args:
            tag_name: The name of the tag to add.
        """
        if tag_name:
            self._tags.add(tag_name)
            self.save()

    def remove_tag(self, tag_name: str) -> None:
        """
        Removes a tag and its associated aliases.

        Args:
            tag_name: The name of the tag to remove.
        """
        if tag_name in self._tags:
            self._tags.remove(tag_name)
            to_remove = [k for k, v in self._tag_aliases.items() if v == tag_name]
            for k in to_remove:
                del self._tag_aliases[k]
            self.save()

    def add_tag_alias(self, alias: str, target: str) -> None:
        """
        Adds an alias for a user tag.

        Args:
            alias: The visual alias.
            target: The normalized target tag name.
        """
        if not alias or not target:
            return
        if target not in self._tags:
            self.add_tag(target)
        self._tag_aliases[alias] = target
        self.save()

    def remove_tag_alias(self, alias: str) -> None:
        """Removes a tag alias."""
        if alias in self._tag_aliases:
            del self._tag_aliases[alias]
            self.save()

    def get_tag_aliases(self) -> Dict[str, str]:
        """Returns all tag aliases."""
        return self._tag_aliases

    # --- Normalization Logic ---

    def normalize_type(self, input_type: Optional[str]) -> str:
        """
        Normalizes a document type string using aliasing and case-insensitive matching.

        Args:
            input_type: The raw string to normalize.

        Returns:
            The normalized string or original if no mapping exists.
        """
        if not input_type:
            return ""

        input_type = input_type.strip()

        # 1. Exact Check
        if input_type in self._types:
            return input_type

        # 2. Exact Alias Check
        if input_type in self._type_aliases:
            return self._type_aliases[input_type]

        # 3. Case-Insensitive Alias Check
        input_lower = input_type.lower()
        for alias, target in self._type_aliases.items():
            if alias.lower() == input_lower:
                return target

        # 4. Case-Insensitive Type Check
        for t in self._types:
            if t.lower() == input_lower:
                return t

        return input_type

    def normalize_tag(self, input_tag: Optional[str]) -> str:
        """
        Normalizes a user tag string.

        Args:
            input_tag: The raw tag string to normalize.

        Returns:
            The normalized tag or original.
        """
        if not input_tag:
            return ""

        input_tag = input_tag.strip()

        if input_tag in self._tags:
            return input_tag

        if input_tag in self._tag_aliases:
            return self._tag_aliases[input_tag]

        input_lower = input_tag.lower()
        for alias, target in self._tag_aliases.items():
            if alias.lower() == input_lower:
                return target

        for t in self._tags:
            if t.lower() == input_lower:
                return t

        return input_tag
