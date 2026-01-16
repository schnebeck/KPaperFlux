import json
from typing import List, Dict, Optional, Set
from PyQt6.QtCore import QSettings

class VocabularyManager:
    """
    Manages controlled vocabulary for Document Types and Tags,
    including alias (synonym) mapping for normalization.
    """
    
    def __init__(self):
        self._types: Set[str] = set()
        self._tags: Set[str] = set()
        self._type_aliases: Dict[str, str] = {} # Alias -> Target (Target must be in _types)
        self._tag_aliases: Dict[str, str] = {} # Alias -> Target (Target must be in _tags)
        
        self.load()
        
    def load(self):
        """Load vocabulary from QSettings."""
        settings = QSettings("KPaperFlux", "Vocabulary")
        
        # Load Types
        types_list = settings.value("types", [], type=list)
        # QSettings might return list of strings or empty list
        self._types = set(str(t) for t in types_list if t)
        
        # Load Tags
        tags_list = settings.value("tags", [], type=list)
        self._tags = set(str(t) for t in tags_list if t)
        
        # Load Aliases (Stored as JSON string because QSettings dict support is tricky across platforms/versions)
        # Or we can use beginGroup. Let's use JSON string for simplicity of structure.
        type_aliases_json = settings.value("type_aliases", "{}", type=str)
        try:
            self._type_aliases = json.loads(type_aliases_json)
        except json.JSONDecodeError:
            self._type_aliases = {}
            
        tag_aliases_json = settings.value("tag_aliases", "{}", type=str)
        try:
            self._tag_aliases = json.loads(tag_aliases_json)
        except json.JSONDecodeError:
            self._tag_aliases = {}
            
        # Ensure defaults if empty (Optional, maybe seeded?)
        if not self._types:
            self._seed_defaults()

    def save(self):
        """Save vocabulary to QSettings."""
        settings = QSettings("KPaperFlux", "Vocabulary")
        
        settings.setValue("types", list(sorted(self._types)))
        settings.setValue("tags", list(sorted(self._tags)))
        settings.setValue("type_aliases", json.dumps(self._type_aliases))
        settings.setValue("tag_aliases", json.dumps(self._tag_aliases))
        
    def _seed_defaults(self):
        """Add some default common types."""
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
        return sorted(list(self._types))
        
    def add_type(self, type_name: str):
        if type_name:
            self._types.add(type_name)
            self.save()
            
    def remove_type(self, type_name: str):
        if type_name in self._types:
            self._types.remove(type_name)
            
            # Clean up aliases pointing to this type
            to_remove = [k for k, v in self._type_aliases.items() if v == type_name]
            for k in to_remove:
                del self._type_aliases[k]
                
            self.save()
            
    def add_type_alias(self, alias: str, target: str):
        """Add strict alias. Target must exist. Case-insensitive key/check?"""
        if not alias or not target:
            return
            
        # Optional: verify target exists or auto-add it? 
        # Better to enforce target existence to keep hygiene.
        if target not in self._types:
            self.add_type(target)
            
        self._type_aliases[alias] = target
        self.save()
        
    def remove_type_alias(self, alias: str):
        if alias in self._type_aliases:
            del self._type_aliases[alias]
            self.save()

    def get_type_aliases(self) -> Dict[str, str]:
        return self._type_aliases

    # --- Tag Management ---
    
    def get_all_tags(self) -> List[str]:
        return sorted(list(self._tags))
        
    def add_tag(self, tag_name: str):
        if tag_name:
            self._tags.add(tag_name)
            self.save()
            
    def remove_tag(self, tag_name: str):
        if tag_name in self._tags:
            self._tags.remove(tag_name)
            # Clean up aliases
            to_remove = [k for k, v in self._tag_aliases.items() if v == tag_name]
            for k in to_remove:
                del self._tag_aliases[k]
            self.save()
            
    def add_tag_alias(self, alias: str, target: str):
        if not alias or not target:
            return
        if target not in self._tags:
            self.add_tag(target)
        self._tag_aliases[alias] = target
        self.save()
        
    def remove_tag_alias(self, alias: str):
        if alias in self._tag_aliases:
            del self._tag_aliases[alias]
            self.save()

    def get_tag_aliases(self) -> Dict[str, str]:
        return self._tag_aliases

    # --- Normalization Logic ---
    
    def normalize_type(self, input_type: str) -> str:
        """
        Normalize a document type string.
        1. Exact match (case-sensitive) -> return.
        2. Alias match (case-insensitive for key?) -> return target.
        3. If not found -> return original (preserving unknown types).
        """
        if not input_type:
            return ""
            
        # 1. Exact Check
        if input_type in self._types:
            return input_type
            
        # 2. Alias Check (Case interaction?)
        # Let's say we check exact alias first
        if input_type in self._type_aliases:
            return self._type_aliases[input_type]
            
        # 3. Case-Insensitive Alias Check
        # Try to find case-insensitive match in aliases
        input_lower = input_type.lower()
        for alias, target in self._type_aliases.items():
            if alias.lower() == input_lower:
                return target

        # 4. Maybe Case-Insensitive Type Check?
        # If "invoice" comes in, and "Invoice" is in types -> normalize
        for t in self._types:
            if t.lower() == input_lower:
                return t
                
        return input_type

    def normalize_tag(self, input_tag: str) -> str:
        """Similar to normalize_type but for tags."""
        if not input_tag:
            return ""
            
        # Trim
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
