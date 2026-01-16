import pytest
from PyQt6.QtCore import QSettings
from core.vocabulary import VocabularyManager

@pytest.fixture
def clean_settings():
    """Clear settings before/after test."""
    settings = QSettings("KPaperFlux", "Vocabulary")
    settings.clear()
    yield
    settings.clear()

def test_defaults(clean_settings):
    vm = VocabularyManager()
    # Should have seeded defaults
    types = vm.get_all_types()
    assert "Invoice" in types
    assert "Contract" in types
    
    # Aliases
    aliases = vm.get_type_aliases()
    assert aliases.get("Rechnung") == "Invoice"

def test_normalization_types(clean_settings):
    vm = VocabularyManager()
    
    # Exact Match
    assert vm.normalize_type("Invoice") == "Invoice"
    
    # Strict Alias
    assert vm.normalize_type("Rechnung") == "Invoice"
    
    # Case-Insensitive Alias
    assert vm.normalize_type("rechnung") == "Invoice"
    
    # Case-Insensitive Type
    assert vm.normalize_type("invoice") == "Invoice"
    
    # Unknown (Pass-through)
    assert vm.normalize_type("AlienBlueprint") == "AlienBlueprint"

def test_normalization_tags(clean_settings):
    vm = VocabularyManager()
    
    vm.add_tag("Urgent")
    vm.add_tag_alias("Wichtig", "Urgent")
    
    assert vm.normalize_tag("Urgent") == "Urgent"
    assert vm.normalize_tag("Wichtig") == "Urgent"
    assert vm.normalize_tag("wichtig") == "Urgent" # Case insensitive alias
    assert vm.normalize_tag("urgent") == "Urgent" # Case insensitive target matching
    
    assert vm.normalize_tag("Private") == "Private" # Unknown

def test_crud_operations(clean_settings):
    vm = VocabularyManager()
    
    # Types
    vm.add_type("Blueprint")
    assert "Blueprint" in vm.get_all_types()
    
    vm.add_type_alias("Plan", "Blueprint")
    assert vm.get_type_aliases()["Plan"] == "Blueprint"
    
    vm.remove_type("Blueprint")
    assert "Blueprint" not in vm.get_all_types()
    # Alias should be gone too
    assert "Plan" not in vm.get_type_aliases()
    
    # Tags
    vm.add_tag("Paid")
    vm.add_tag_alias("Bezahlt", "Paid")
    assert "Paid" in vm.get_all_tags()
    assert vm.get_tag_aliases()["Bezahlt"] == "Paid"
    
    vm.remove_tag("Paid")
    assert "Paid" not in vm.get_all_tags()
    assert "Bezahlt" not in vm.get_tag_aliases()
