
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Adjust path to find core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core.pipeline import PipelineProcessor
from core.canonizer import CanonizerService
from core.document import Document
from core.models.identity import IdentityProfile
from core.ai_analyzer import AIAnalyzer

class TestPhase102Integration(unittest.TestCase):
    
    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_config = MagicMock()
        
    @patch('core.canonizer.CanonizerService')
    @patch('core.config.AppConfig')
    def test_pipeline_delegates_to_canonizer(self, MockConfig, MockCanonizerService):
        """
        Verify that Pipeline no longer calls legacy AI, but delegates to CanonizerService.
        """
        # Setup
        pipeline = PipelineProcessor(db=self.mock_db)
        
        # Test Doc
        doc = Document(uuid="test-uuid", text_content="Sample PDF Text", path="/tmp/test.pdf", original_filename="test.pdf")
        
        # Mock Canonizer Instance
        mock_canonizer_instance = MockCanonizerService.return_value
        
        # Act
        # But _perform_ai_analysis is what we changed.
        # process_document does steps: import -> save -> OCR -> AI.
        # But _perform_ai_analysis is what we changed.
        pipeline._run_ai_analysis(doc, file_path=None)
        
        # Assert
        # 1. Canonizer should be instantiated
        MockCanonizerService.assert_called_once()
        
        # 2. process_document should be called on the instance
        mock_canonizer_instance.process_document.assert_called_once_with(doc.uuid, doc.text_content, file_path=None)
        
    @patch('core.canonizer.AIAnalyzer') 
    @patch('core.canonizer.AppConfig')
    def test_canonizer_uses_classify_structure(self, MockConfig, MockAIAnalyzer):
        """
        Verify that Canonizer calls classify_structure (Stage 1) and then extracts data.
        """
        # Setup
        service = CanonizerService(self.mock_db, MockConfig.return_value)
        # Mock Config JSON return to None or Valid JSON
        MockConfig.return_value.get_private_profile_json.return_value = None
        MockConfig.return_value.get_business_profile_json.return_value = None
        
        service.analyzer = MockAIAnalyzer.return_value # Inject mock analyzer
        
        # Setup Mock Responses
        # Classify should return a structure
        service.analyzer.classify_structure.return_value = {
            "source_file_summary": {},
            "detected_entities": [
                {"doc_type": "INVOICE", "direction": "INBOUND", "tenant_context": "BUSINESS"}
            ]
        }
        
        doc_uuid = "test-doc-123"
        text_content = "Page 1 Content \f Page 2 Content"
        
        # Act
        service.process_document(doc_uuid, text_content)
        
        # Assert
        # 1. classify_structure MUST be called (Stage 1)
        service.analyzer.classify_structure.assert_called_once()
        
        # Verify args (Should pass page list)
        call_args = service.analyzer.classify_structure.call_args
        pages = call_args[0][0] # First arg is pages
        self.assertEqual(len(pages), 2)
        
        # 2. extract_canonical_data MUST be called (Stage 2)
        service.analyzer.extract_canonical_data.assert_called_once()
        
        # 3. _classify_direction should NOT be called if AI returned direction?
        # Actually it's fallback. If AI returns INBOUND, fallback is skipped.
        # We can't easily assertion checking internal method call unless we spy on self.
        # But we can check if entity was saved with correct direction.
        
    @patch('core.canonizer.AIAnalyzer')
    def test_canonizer_cleanup_logic(self, MockAIAnalyzer):
        """
        Verify that Canonizer performs DELETE before (or after success) processing.
        """
        service = CanonizerService(self.mock_db, self.mock_config)
        service.analyzer = MockAIAnalyzer.return_value
        
        # Mock Success
        service.analyzer.classify_structure.return_value = {"doc_type": "OTHER"}
        
        # Act
        service.process_document("cleanup-uuid", "text")
        
        # Assert DB execute called with DELETE
        # We need to find the DELETE call in the mock_db.connection.execute list
        found_delete = False
        for call in self.mock_db.connection.execute.call_args_list:
            sql = call[0][0]
            if "DELETE FROM semantic_entities" in sql:
                found_delete = True
                break
        
        self.assertTrue(found_delete, "Should have executed DELETE FROM semantic_entities")

if __name__ == '__main__':
    unittest.main()
