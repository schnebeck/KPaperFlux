import pytest
import os
from pathlib import Path
import pikepdf
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager
from core.vault import DocumentVault

@pytest.fixture
def temp_infra(tmp_path):
    # Setup
    db_path = tmp_path / "test.db"
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    
    db = DatabaseManager(str(db_path))
    db.init_db()
    
    vault = DocumentVault(str(vault_path))
    pipeline = PipelineProcessor(base_path=str(vault_path), db_path=str(db_path), vault=vault, db=db)
    
    return pipeline, db, vault, tmp_path

def test_ingest_physical_file(temp_infra):
    """Test standard V2 ingestion: Physical -> Virtual -> Shadow."""
    pipeline, db, vault, root = temp_infra
    
    # Create Dummy PDF
    pdf_path = root / "dummy.pdf"
    with pikepdf.new() as pdf:
        pdf.add_blank_page()
        pdf.save(pdf_path)
        
    # Run Process (Skip AI)
    doc = pipeline.process_document(str(pdf_path), skip_ai=True)
    
    # 1. Assert Legacy Return matches
    assert doc is not None
    assert doc.uuid is not None
    assert doc.original_filename == "dummy.pdf"
    
    # 2. Verify Physical File Store
    cursor = db.connection.cursor()
    phys_rows = cursor.execute("SELECT * FROM physical_files").fetchall()
    assert len(phys_rows) == 1
    p_row = phys_rows[0]
    assert p_row["original_filename"] == "dummy.pdf"
    
    # 3. Verify Logical Entity Store
    v_doc = pipeline.logical_repo.get_by_uuid(doc.uuid)
    assert v_doc is not None
    assert v_doc.uuid == doc.uuid # Fixed entity_uuid -> uuid
    assert len(v_doc.source_mapping) == 1
    assert v_doc.source_mapping[0].file_uuid == p_row["uuid"]
    
    # 4. Verify Database View
    s_doc = db.get_document_by_uuid(doc.uuid)
    assert s_doc.page_count == 1

def test_deduplication(temp_infra):
    """Test that importing the same file twice reuses physical file."""
    pipeline, db, vault, root = temp_infra
    
    # Create Dummy PDF
    pdf_path = root / "duplicate.pdf"
    with pikepdf.new() as pdf:
        pdf.add_blank_page()
        pdf.save(pdf_path)
        
    # Import 1
    doc1 = pipeline.process_document(str(pdf_path), skip_ai=True)
    
    # Import 2 (Same file content)
    doc2 = pipeline.process_document(str(pdf_path), skip_ai=True)
    
    assert doc1.uuid != doc2.uuid # Distinct Logic Entities
    
    # Verify Physical Files Count = 1
    cursor = db.connection.cursor()
    phys_rows = cursor.execute("SELECT * FROM physical_files").fetchall()
    assert len(phys_rows) == 1
    
    # Verify both virtual docs reference the same physical file
    p_uuid = phys_rows[0]["uuid"]
    refs = pipeline.logical_repo.get_by_source_file(p_uuid)
    assert len(refs) == 2
