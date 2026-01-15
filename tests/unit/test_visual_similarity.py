
import pytest
from unittest.mock import MagicMock, patch
from core.similarity import SimilarityManager
from core.document import Document
from PIL import Image

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_vault():
    vault = MagicMock()
    vault.get_file_path.side_effect = lambda uuid: f"/tmp/{uuid}.pdf"
    return vault

@pytest.fixture
def mock_exists():
    with patch("pathlib.Path.exists", return_value=True) as mock:
        yield mock

def test_visual_similarity_identical(mock_db, mock_vault, mock_exists):
    # Mock conversion -> Single Page Identical
    with patch('core.similarity.convert_from_path') as mock_convert:
        img = Image.new('L', (64, 80), color=128)
        mock_convert.return_value = [img]
        
        manager = SimilarityManager(mock_db, mock_vault)
        doc_a = Document(uuid="a", original_filename="a.pdf")
        doc_b = Document(uuid="b", original_filename="b.pdf")
        
        score = manager.calculate_visual_similarity(doc_a, doc_b)
        assert score == 1.0

def test_visual_similarity_containment(mock_db, mock_vault, mock_exists):
    # Doc A: Single Page (Gray 128)
    # Doc B: 3 Pages (Black, Gray 128, White)
    # A should match B's 2nd page.
    
    with patch('core.similarity.convert_from_path') as mock_convert:
        img_target = Image.new('L', (64, 80), color=128)
        img_other1 = Image.new('L', (64, 80), color=0)
        img_other2 = Image.new('L', (64, 80), color=255)
        
        def side_effect(path, **kwargs):
            if "a.pdf" in str(path):
                return [img_target]
            elif "b.pdf" in str(path):
                return [img_other1, img_target, img_other2]
            return []
            
        mock_convert.side_effect = side_effect
        
        manager = SimilarityManager(mock_db, mock_vault)
        doc_a = Document(uuid="a", original_filename="a.pdf")
        doc_b = Document(uuid="b", original_filename="b.pdf")
        
        score = manager.calculate_visual_similarity(doc_a, doc_b)
        assert score == 1.0

def test_visual_similarity_different(mock_db, mock_vault, mock_exists):
    with patch('core.similarity.convert_from_path') as mock_convert:
        img_a = Image.new('L', (64, 80), color=0)
        img_b = Image.new('L', (64, 80), color=255)
        
        def side_effect(path, **kwargs):
            if "a.pdf" in str(path): return [img_a]
            else: return [img_b]
            
        mock_convert.side_effect = side_effect
        
        manager = SimilarityManager(mock_db, mock_vault)
        doc_a = Document(uuid="a", original_filename="a.pdf")
        doc_b = Document(uuid="b", original_filename="b.pdf")
        
        score = manager.calculate_visual_similarity(doc_a, doc_b)
        assert score == 0.0
