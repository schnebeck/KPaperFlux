
import os
import pytest
from core.database import DatabaseManager
from core.pipeline import PipelineProcessor
from core.repositories.logical_repo import LogicalRepository
from core.models.virtual import VirtualDocument

def test_archive_logic(tmp_path):
    # Use tmp_path fixture for isolated test environment
    db_path = str(tmp_path / "test_archive.db")
    vault_path = str(tmp_path / "test_vault")
    os.makedirs(vault_path)

    db_manager = DatabaseManager(db_path)
    db_manager.init_db()
    
    pipeline = PipelineProcessor(base_path=vault_path, db=db_manager)
    repo = LogicalRepository(db_manager)

    # 1. Create a dummy document
    doc_uuid = "test-archive-uuid-123"
    doc = VirtualDocument(uuid=doc_uuid, status="READY")
    repo.save(doc)
    
    # Verify it exists and is not archived
    fetched = repo.get_by_uuid(doc_uuid)
    assert fetched is not None
    assert fetched.archived is False
    
    # 1a. Verify it shows up in "Normal View" and counts
    assert any(d.uuid == doc_uuid for d in db_manager.get_all_entities_view())
    assert db_manager.count_entities() == 1

    # 2. Perform ARCHIVE via Pipeline
    pipeline.archive_entity(doc_uuid, archive=True)
    
    # Verify it is archived
    fetched = repo.get_by_uuid(doc_uuid)
    assert fetched is not None
    assert fetched.archived is True
    
    # 2a. Verify it DISAPPEARS from "Normal View" and counts
    assert not any(d.uuid == doc_uuid for d in db_manager.get_all_entities_view())
    assert db_manager.count_entities() == 0

    # 3. Perform UNARCHIVE (Restore)
    pipeline.archive_entity(doc_uuid, archive=False)
    
    # Verify it is back to normal
    fetched = repo.get_by_uuid(doc_uuid)
    assert fetched is not None
    assert fetched.archived is False
    
    # 3a. Verify it REAPPEARS in "Normal View" and counts
    assert any(d.uuid == doc_uuid for d in db_manager.get_all_entities_view())
    assert db_manager.count_entities() == 1
