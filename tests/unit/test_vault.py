import pytest
import os
import shutil
from pathlib import Path
from core.vault import DocumentVault
from core.document import Document

@pytest.fixture
def temp_vault(tmp_path):
    """Create a temporary vault directory."""
    vault_path = tmp_path / "vault"
    return DocumentVault(base_path=str(vault_path))

@pytest.fixture
def source_file(tmp_path):
    """Create a dummy source file."""
    p = tmp_path / "source.pdf"
    p.write_text("dummy content")
    return p

def test_vault_init_creates_dir(tmp_path):
    """Test that validating the vault creates the directory."""
    vault_path = tmp_path / "new_vault"
    assert not vault_path.exists()
    
    DocumentVault(base_path=str(vault_path))
    assert vault_path.exists()
    assert vault_path.is_dir()

def test_store_document(temp_vault, source_file):
    """Test storing a document copies it to the vault with UUID name."""
    doc = Document(original_filename=source_file.name)
    
    stored_path = temp_vault.store_document(doc, str(source_file))
    
    assert Path(stored_path).exists()
    assert Path(stored_path).name == f"{doc.uuid}.pdf"
    assert Path(stored_path).parent == Path(temp_vault.base_path)
    # Validate content matches
    assert Path(stored_path).read_text() == "dummy content"

def test_get_file_path(temp_vault):
    """Test retrieving the absolute path of a document."""
    doc = Document(original_filename="test.pdf")
    expected_path = Path(temp_vault.base_path) / f"{doc.uuid}.pdf"
    
    assert temp_vault.get_file_path(doc.uuid) == str(expected_path)

def test_store_document_nonexistent_source(temp_vault):
    """Test error when source file does not exist."""
    doc = Document(original_filename="ghost.pdf")
    with pytest.raises(FileNotFoundError):
        temp_vault.store_document(doc, "/path/to/nothing.pdf")

