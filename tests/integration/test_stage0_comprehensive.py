import pytest
import os
import shutil
import tempfile
import json
import uuid
import pikepdf
from pathlib import Path
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager
from core.vault import DocumentVault
from core.models.virtual import VirtualDocument, SourceReference

def create_dummy_pdf(path, pages=1):
    """Create a multi-page PDF with some text content."""
    pdf = pikepdf.Pdf.new()
    for i in range(pages):
        page = pdf.add_blank_page(page_size=(595, 842))
        # pikepdf doesn't easily 'draw' text without a content stream, 
        # but for Stage 0 we only need the presence of pages and valid PDF structure.
    pdf.save(path)

@pytest.fixture
def test_env():
    """Setup a temporary vault and database."""
    temp_dir = tempfile.mkdtemp()
    vault_path = os.path.join(temp_dir, "vault")
    db_path = os.path.join(temp_dir, "test.db")
    os.makedirs(vault_path)
    
    db_manager = DatabaseManager(db_path)
    db_manager.init_db()
    vault = DocumentVault(vault_path)
    pipeline = PipelineProcessor(vault=vault, db=db_manager)
    
    # Mock OCR to avoid external binary dependency
    from unittest.mock import MagicMock
    pipeline._run_ocr = MagicMock(return_value={"1": "OCR Text", "2": "OCR Text", "3": "OCR Text", "4": "OCR Text"})
    
    yield {
        "pipeline": pipeline,
        "db": db_manager,
        "vault": vault,
        "temp_dir": temp_dir
    }
    
    # Cleanup
    shutil.rmtree(temp_dir)

def test_stage0_workflow_comprehensive(test_env):
    """
    Comprehensive test covering:
    1. Import (Single & Multiple)
    2. Verification of structure
    3. Restructure (Split & Rotation)
    4. Logical Merge
    5. Orphan Purge (Cleanup)
    """
    pipeline = test_env["pipeline"]
    db = test_env["db"]
    vault = test_env["vault"]
    temp_dir = test_env["temp_dir"]
    
    # --- 1. PREPARATION ---
    pdf1_path = os.path.join(temp_dir, "doc1.pdf") # 1 page
    pdf2_path = os.path.join(temp_dir, "doc2.pdf") # 4 pages
    create_dummy_pdf(pdf1_path, 1)
    create_dummy_pdf(pdf2_path, 4)
    
    # --- 2. IMPORT ---
    uuids = []
    for p in [pdf1_path, pdf2_path]:
        res = pipeline.process_document(p, skip_ai=True)
        if isinstance(res, str):
            uuids.append(res)
        elif hasattr(res, 'uuid'):
            uuids.append(res.uuid)
    
    assert len(uuids) == 2
    
    doc1_uuid = uuids[0]
    doc2_uuid = uuids[1]
    
    print(f"\n[DEBUG] Import Finished. Entities in DB: {db.count_entities()}")
    print(f"[DEBUG] Initial UUIDs: {uuids}")
    
    # Verify initial counts
    ent_count = db.count_entities()
    assert ent_count == 2
    
    d2 = db.get_document_by_uuid(doc2_uuid)
    print(f"[DEBUG] Doc2 UUID: {doc2_uuid}, Found: {d2 is not None}")
    assert d2 is not None
    assert d2.page_count == 4
    
    # --- 3. RESTRUCTURE (SPLIT) ---
    # Get the file_uuid of doc2
    mapping_2 = db.get_source_mapping_from_entity(doc2_uuid)
    f2_uuid = mapping_2[0]["file_uuid"]

    # Split doc2 into two parts: [1, 2] and [3, 4] with rotation on page 3
    instructions = [
        {
            "pages": [
                {"file_page_index": 0, "rotation": 0, "file_uuid": f2_uuid},
                {"file_page_index": 1, "rotation": 0, "file_uuid": f2_uuid}
            ]
        },
        {
            "pages": [
                {"file_page_index": 2, "rotation": 90, "file_uuid": f2_uuid},
                {"file_page_index": 3, "rotation": 0, "file_uuid": f2_uuid}
            ]
        }
    ]
    
    new_uuids = pipeline.apply_restructure_instructions(doc2_uuid, instructions)
    assert len(new_uuids) == 2
    
    # Verify original doc2 is gone (soft deleted by restructure)
    assert db.get_document_by_uuid(doc2_uuid) is None
    
    # Verify new entities
    part_a = db.get_document_by_uuid(new_uuids[0])
    part_b = db.get_document_by_uuid(new_uuids[1])
    assert part_a.page_count == 2
    assert part_b.page_count == 2
    
    # Check rotation on part_b
    mapping_b = db.get_source_mapping_from_entity(new_uuids[1])
    assert mapping_b[0]["rotation"] == 90
    
    # --- 4. LOGICAL MERGE ---
    # Merge doc1 and part_a
    merge_uuids = [doc1_uuid, part_a.uuid]
    success = pipeline.merge_documents(merge_uuids)
    assert success
    
    # Find the merged doc
    all_docs = db.get_all_entities_view()
    merged_docs = [d for d in all_docs if "LOGICAL_MERGE" in d.type_tags]
    assert len(merged_docs) == 1
    merged_doc = merged_docs[0]
    
    assert merged_doc.page_count == 3 # 1 + 2
    
    # Verify mapping includes both files
    mapping_m = db.get_source_mapping_from_entity(merged_doc.uuid)
    assert len(mapping_m) >= 2
    
    # --- 5. CLEANUP / ORPHAN PURGE ---
    # Delete doc1, part_a, and merged doc
    # doc2's physical file should still exist because part_b uses it.
    # doc1's physical file should disappear once we delete ALL docs referencing it.
    
    # 5.1 Delete doc1 (Original)
    source_mapping_1 = db.get_source_mapping_from_entity(doc1_uuid)
    phys_uuid_1 = source_mapping_1[0]["file_uuid"]
    
    pipeline.delete_entity(doc1_uuid)
    # merged_doc still uses it!
    assert vault.get_file_path(phys_uuid_1) is not None
    assert os.path.exists(vault.get_file_path(phys_uuid_1))
    
    # 5.2 Delete part_a 
    pipeline.delete_entity(part_a.uuid)
    
    # 5.3 Delete merged doc
    pipeline.delete_entity(merged_doc.uuid)
    # Now NO ONE uses doc1's physical file. 
    assert not os.path.exists(vault.get_file_path(phys_uuid_1))
    
    # 5.4 Verify doc2's physical file is STILL THERE (part_b uses it)
    source_mapping_b = db.get_source_mapping_from_entity(part_b.uuid)
    phys_uuid_2 = source_mapping_b[0]["file_uuid"]
    assert os.path.exists(vault.get_file_path(phys_uuid_2))
    
    # 5.5 Delete part_b -> doc2's physical file should be purged
    pipeline.delete_entity(part_b.uuid)
    assert not os.path.exists(vault.get_file_path(phys_uuid_2))
    
    # --- 6. DATABASE INTEGRITY ---
    # No documents should be left in active view
    assert db.count_entities() == 0
    # physical_files table should be empty
    cursor = db.connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM physical_files")
    assert cursor.fetchone()[0] == 0

    print("\n[SUCCESS] Stage 0 Comprehensive Integration Test passed.")
