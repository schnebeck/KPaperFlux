
"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_ai_analyzer_preflight.py
Version:        1.0.0
Producer:       
Generator:      Antigravity
Description:    Reproduction test for f-string formatting error in AI Pre-Flight.
------------------------------------------------------------------------------
"""

import pytest
from unittest.mock import MagicMock, patch
from core.ai_analyzer import AIAnalyzer

@pytest.fixture
def analyzer():
    return AIAnalyzer(api_key="test")

def test_ask_type_check_formatting(analyzer):
    """
    Reproduce the 'Invalid format specifier' error.
    This occurs if curly braces in the f-string template are not escaped.
    """
    with patch.object(analyzer, "_generate_json") as mock_gen:
        mock_gen.return_value = {"primary_type": "INVOICE"}
        
        # This will raise a ValueError or NameError if the f-string is broken
        try:
            res = analyzer.ask_type_check(["Some page content"])
            assert res["primary_type"] == "INVOICE"
        except Exception as e:
            pytest.fail(f"ask_type_check failed with formatting error: {e}")
