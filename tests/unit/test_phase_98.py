import pytest
import json
from unittest.mock import MagicMock, patch
from core.ai_analyzer import AIAnalyzer

@pytest.fixture
def mock_genai():
    with patch("core.ai_analyzer.genai") as mock:
        yield mock

def test_identify_entities_uses_refinement(mock_genai):
    """Verify that identify_entities calls refine_semantic_entities when semantic_data has pages."""
    analyzer = AIAnalyzer(api_key="test")
    
    # Mock refine_semantic_entities to check call
    with patch.object(analyzer, 'refine_semantic_entities', return_value=[{"type": "TEST"}]) as mock_refine:
        semantic_data = {"pages": [{"page_number": 1}]}
        
        result = analyzer.identify_entities("some text", semantic_data)
        
        mock_refine.assert_called_once_with(semantic_data)
        assert result == [{"type": "TEST"}]

def test_identify_entities_falls_back_legacy(mock_genai):
    """Verify fallback to legacy if semantic_data is missing pages."""
    analyzer = AIAnalyzer(api_key="test")
    
    with patch.object(analyzer, '_identify_entities_legacy', return_value=[{"type": "LEGACY"}]) as mock_legacy:
        # Case 1: None
        analyzer.identify_entities("text", None)
        mock_legacy.assert_called()
        
        # Case 2: Empty dict
        mock_legacy.reset_mock()
        analyzer.identify_entities("text", {})
        mock_legacy.assert_called()

def test_refine_semantic_entities_prompt_structure(mock_genai):
    """Verify the prompt contains the JSON dump."""
    analyzer = AIAnalyzer(api_key="test")
    
    semantic_data = {
        "pages": [
            {"page_number": 1, "regions": [{"type": "Text", "content": "Page 1 Content"}]},
            {"page_number": 2, "regions": [{"type": "Table", "rows": [["Col1", "Col2"]]}]}
        ]
    }
    
    mock_response = MagicMock()
    mock_response.text = json.dumps([
        {"type": "INVOICE", "pages": [1, 2], "confidence": 0.9}
    ])
    analyzer.client.models.generate_content.return_value = mock_response
    
    result = analyzer.refine_semantic_entities(semantic_data)
    
    assert len(result) == 1
    assert result[0]["type"] == "INVOICE"
    assert result[0]["pages"] == [1, 2]
    
    # Verify Prompt content
    # The analyzer uses self.client.models.generate_content(model=..., contents=[prompt])
    model_mock = analyzer.client.models
    call_args = model_mock.generate_content.call_args
    
    assert call_args is not None, "generate_content was not called"
    
    args, kwargs = call_args
    # It sends contents=[prompt] as kwarg
    contents = kwargs.get('contents')
    if not contents and args:
         # fallback if positional (model, contents) or (contents)
         # signature is (model, contents, config...) usually
         contents = args[1] if len(args) > 1 else args[0]
         
    prompt_str = contents[0] if contents else ""
    
    assert "Logical Document Structure" in prompt_str
    assert "Page 1 Content" in prompt_str # Part of JSON dump
    assert "Col1" in prompt_str # Part of JSON dump
    
    # New Check: Verify it uses existing types
    # Since semantic_data in this test has no summary/doc_type, it defaults to OTHER
    assert "EXISTING ANALYSIS" in prompt_str
    assert "OTHER" in prompt_str 
