
import pytest
import os
import shutil
import tempfile
from pathlib import Path
from core.vault import DocumentVault
from core.models.virtual import VirtualDocument as Document

@pytest.fixture
def vault_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)

@pytest.fixture
def source_file():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"content")
        name = f.name
    yield Path(name)
    if os.path.exists(name):
        os.remove(name)

def test_store_document_copy(vault_dir, source_file):
    vault = DocumentVault(str(vault_dir))
    doc = Document(original_filename="test.pdf")
    
    stored_path = vault.store_document(doc, str(source_file), move=False)
    
    assert os.path.exists(stored_path)
    assert os.path.exists(source_file) # Source remains
    assert Path(stored_path).read_bytes() == b"content"

def test_store_document_move(vault_dir, source_file):
    vault = DocumentVault(str(vault_dir))
    doc = Document(original_filename="moved.pdf")
    
    stored_path = vault.store_document(doc, str(source_file), move=True)
    
    assert os.path.exists(stored_path)
    assert not os.path.exists(source_file) # Source deleted
    assert Path(stored_path).read_bytes() == b"content"
