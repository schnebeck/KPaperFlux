
import os
import pytest
from pathlib import Path
from core.database import DatabaseManager
from core.pipeline import PipelineProcessor
from core.repositories.logical_repo import LogicalRepository
from core.models.virtual import VirtualDocument

def test_deletion_logic(tmp_path):
    # Use tmp_path fixture for isolated test environment
    db_path = str(tmp_path / "test_deletion.db")
    vault_path = str(tmp_path / "test_vault")
    os.makedirs(vault_path)

    db_manager = DatabaseManager(db_path)
    db_manager.init_db()
    
    pipeline = PipelineProcessor(base_path=vault_path, db=db_manager)
    repo = LogicalRepository(db_manager)

    # Create a dummy physical file and register it in DB
    file_uuid = "test-file-123"
    file_path = os.path.join(vault_path, f"{file_uuid}.pdf")
    with open(file_path, "w") as f:
        f.write("dummy content")
    
    with db_manager.connection:
        db_manager.connection.execute(
            "INSERT INTO physical_files (uuid, file_path) VALUES (?, ?)",
            (file_uuid, file_path)
        )

    # 1. Create a dummy document
    doc_uuid = "test-uuid-123"
    doc = VirtualDocument(uuid=doc_uuid, status="READY")
    doc.add_source(file_uuid, [1])
    repo.save(doc)
    
    # Verify it exists
    fetched = repo.get_by_uuid(doc_uuid)
    assert fetched is not None
    assert fetched.deleted is False
    assert os.path.exists(file_path)

    # 2. Perform SOFT deletion via Pipeline
    pipeline.delete_entity(doc_uuid, purge=False)
    
    # Verify it STILL exists but is marked deleted
    fetched = repo.get_by_uuid(doc_uuid)
    assert fetched is not None
    assert fetched.deleted is True
    assert fetched.deleted_at is not None
    # CRITICAL: Physical file MUST still exist!
    assert os.path.exists(file_path)

    # 3. Perform HARD deletion (Purge)
    pipeline.delete_entity(doc_uuid, purge=True)
    
    # Verify it is GONE from DB
    fetched = repo.get_by_uuid(doc_uuid)
    assert fetched is None
    # CRITICAL: Physical file MUST be gone now (since no other doc refers to it)
    assert not os.path.exists(file_path)
