
import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from core.database import DatabaseManager
from core.vault import DocumentVault
from core.document import Document
from core.integrity import IntegrityManager

@pytest.fixture
def mock_db():
    db = MagicMock(spec=DatabaseManager)
    return db

@pytest.fixture
def temp_vault():
    with tempfile.TemporaryDirectory() as d:
        yield DocumentVault(d)

def test_integrity_check_clean(mock_db, temp_vault):
    # Setup: 1 Doc in DB and Vault
    doc1 = Document(uuid="uuid-1", original_filename="doc1.pdf")
    mock_db.get_all_documents.return_value = [doc1]
    
    # Create file
    path = temp_vault.base_path / "uuid-1.pdf"
    path.write_text("content")
    
    manager = IntegrityManager(mock_db, temp_vault)
    report = manager.check_integrity()
    
    assert len(report.orphans) == 0
    assert len(report.ghosts) == 0

def test_integrity_orphans(mock_db, temp_vault):
    # Setup: 2 Docs in DB, 1 in Vault
    doc1 = Document(uuid="uuid-1", original_filename="doc1.pdf")
    doc2 = Document(uuid="uuid-2", original_filename="doc2.pdf")
    
    mock_db.get_all_documents.return_value = [doc1, doc2]
    
    # Create only file 1
    (temp_vault.base_path / "uuid-1.pdf").write_text("content")
    
    manager = IntegrityManager(mock_db, temp_vault)
    report = manager.check_integrity()
    
    assert len(report.orphans) == 1
    assert report.orphans[0].uuid == "uuid-2"
    assert len(report.ghosts) == 0

def test_integrity_ghosts(mock_db, temp_vault):
    # Setup: 1 Doc in DB, 2 in Vault
    doc1 = Document(uuid="uuid-1", original_filename="doc1.pdf")
    
    mock_db.get_all_documents.return_value = [doc1]
    
    # Create file 1 and 2
    (temp_vault.base_path / "uuid-1.pdf").write_text("content")
    (temp_vault.base_path / "uuid-ghost.pdf").write_text("boo")
    
    manager = IntegrityManager(mock_db, temp_vault)
    report = manager.check_integrity()
    
    assert len(report.orphans) == 0
    assert len(report.ghosts) == 1
    assert report.ghosts[0].name == "uuid-ghost.pdf"
