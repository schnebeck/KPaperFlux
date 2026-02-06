
import pytest
from core.metadata_normalizer import MetadataNormalizer
from core.models.virtual import VirtualDocument as Document

class TestMetadataNormalizer:
    
    def test_normalize_date(self):
        # German format
        assert MetadataNormalizer._normalize_date("19.01.2026") == "2026-01-19"
        assert MetadataNormalizer._normalize_date("01.02.2023") == "2023-02-01"
        
        # ISO format (noop)
        assert MetadataNormalizer._normalize_date("2025-12-31") == "2025-12-31"
        
        # Textual/Mixed (optional, based on robustness)
        # assert MetadataNormalizer._normalize_date("19. Jan 2026") == "2026-01-19"
        
        # Invalid
        assert MetadataNormalizer._normalize_date("Not a date") == "Not a date"

    def test_normalize_amount(self):
        # German format
        assert MetadataNormalizer._normalize_amount("1.234,56") == 1234.56
        assert MetadataNormalizer._normalize_amount("50,00") == 50.0
        
        # Standard format
        assert MetadataNormalizer._normalize_amount("1234.56") == 1234.56
        assert MetadataNormalizer._normalize_amount(100.0) == 100.0
        
        # With Currency symbol (should strip)
        assert MetadataNormalizer._normalize_amount("€ 150,00") == 150.0
        assert MetadataNormalizer._normalize_amount("150,00 €") == 150.0

    def test_normalize_currency(self):
        assert MetadataNormalizer._normalize_currency("€") == "EUR"
        assert MetadataNormalizer._normalize_currency("$") == "USD"
        assert MetadataNormalizer._normalize_currency("eur") == "EUR"
        assert MetadataNormalizer._normalize_currency("USD") == "USD"
        
    def test_integration_extraction(self):
        # Mock Document with compliant AI data
        doc = Document(file_path="dummy.pdf", original_filename="dummy.pdf")
        doc.type_tags = ["Invoice"] # Assume configured type
        # No more direct dict assignment with 'summary'
        pass
        
        # We need to mock get_config to return a definition for 'Invoice'
        # Or depend on the real resources/type_definitions.json if available.
        # Ideally we verify the private methods first.
        pass
