import pytest
import uuid
import datetime
from core.database import DatabaseManager
from core.repositories import LogicalRepository
from core.models.virtual import VirtualDocument, SourceReference
from core.models.semantic import SemanticExtraction

@pytest.fixture
def memory_db():
    db = DatabaseManager(":memory:")
    db.init_db()
    return db

@pytest.fixture
def logical_repo(memory_db):
    return LogicalRepository(memory_db)

def test_init_db(memory_db):
    cursor = memory_db.connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view');")
    items = [row[0] for row in cursor.fetchall()]
    assert "physical_files" in items
    assert "virtual_documents" in items
    assert "virtual_documents_fts" in items
    assert "semantic_entities" not in items
    assert "documents" not in items 

def test_insert_virtual_document(logical_repo):
    v_doc = VirtualDocument(
        uuid=str(uuid.uuid4()),
        status="NEW",
        created_at=datetime.datetime.now().isoformat(),
        semantic_data=SemanticExtraction(
            meta_header={"sender": {"name": "TestSender"}}
        )
    )
    logical_repo.save(v_doc)
    
    retrieved = logical_repo.get_by_uuid(v_doc.uuid)
    assert retrieved is not None
    assert retrieved.semantic_data.meta_header.sender.name == "TestSender"

    
def test_get_document_by_uuid_stage0(memory_db, logical_repo):
    v_uuid = str(uuid.uuid4())
    v_doc = VirtualDocument(
        uuid=v_uuid,
        status="NEW",
        created_at=datetime.datetime.now().isoformat(),
        export_filename="TestExport"
    )
    logical_repo.save(v_doc)
    
    doc = memory_db.get_document_by_uuid(v_uuid)
    
    assert doc is not None
    assert doc.uuid == v_uuid
    assert doc.original_filename == "TestExport"

def test_delete_document_soft(memory_db, logical_repo):
    v_uuid = str(uuid.uuid4())
    v_doc = VirtualDocument(uuid=v_uuid, created_at="2023-01-01")
    logical_repo.save(v_doc)
    
    # Soft Delete manually via Repo Fetch-Save
    v_doc.deleted = True
    logical_repo.save(v_doc)
    
    # Verify
    retrieved = logical_repo.get_by_uuid(v_uuid)
    assert retrieved.deleted is True
    
    # Verify table state directly
    cursor = memory_db.connection.cursor()
    cursor.execute("SELECT deleted FROM virtual_documents WHERE uuid = ?", (v_uuid,))
    assert cursor.fetchone()[0] == 1

def test_pdf_class_persistence(logical_repo):
    v_doc = VirtualDocument(
        uuid=str(uuid.uuid4()),
        pdf_class="AB"
    )
    logical_repo.save(v_doc)
    
    retrieved = logical_repo.get_by_uuid(v_doc.uuid)
    assert retrieved.pdf_class == "AB"


def test_delete_restore_purge_report_unknown_uuid(memory_db, logical_repo):
    """Return values reflect the given document, not earlier changes on the same connection."""
    logical_repo.save(VirtualDocument(uuid="known", source_mapping=[SourceReference(file_uuid="f", pages=[1])]))

    assert memory_db.delete_document("known") is True
    assert memory_db.restore_document("known") is True
    assert memory_db.delete_document("missing") is False
    assert memory_db.restore_document("missing") is False
    assert memory_db.purge_document("missing") is False
    assert memory_db.purge_document("known") is True


def test_list_count_and_sum_agree_on_archived_documents(memory_db, logical_repo):
    from decimal import Decimal
    from core.models.semantic import FinanceBody, MonetarySummation
    for doc_uuid, archived in (("active", False), ("archived", True)):
        logical_repo.save(VirtualDocument(
            uuid=doc_uuid, archived=archived, source_mapping=[SourceReference(file_uuid="f", pages=[1])],
            semantic_data=SemanticExtraction(bodies={"finance_body": FinanceBody(
                monetary_summation=MonetarySummation(grand_total_amount=Decimal("10.00")))})))

    query = {"operator": "AND", "conditions": []}
    listed = memory_db.search_documents_advanced(query)
    assert [d.uuid for d in listed] == ["active"]
    assert memory_db.count_documents_advanced(query) == len(listed)
    assert memory_db.sum_documents_advanced(query) == 10.0

    archive_view = {"field": "archived", "op": "equals", "value": True}
    assert memory_db.count_documents_advanced(archive_view) == 1


def test_nested_transactions_are_atomic(memory_db):
    """An error in an outer transaction also rolls back what a nested one wrote."""
    import pytest as _pytest
    with _pytest.raises(RuntimeError):
        with memory_db.transaction() as conn:
            conn.execute("INSERT INTO virtual_documents (uuid) VALUES ('outer')")
            with memory_db.transaction() as inner:
                inner.execute("INSERT INTO virtual_documents (uuid) VALUES ('inner')")
            raise RuntimeError("abort after the nested block")

    rows = memory_db.connection.execute("SELECT uuid FROM virtual_documents").fetchall()
    assert rows == []


def test_amount_filter_matches_both_save_paths(memory_db, logical_repo):
    """Repository save and update_document_metadata store Decimals alike; numeric filters compare numbers."""
    from decimal import Decimal
    from core.models.semantic import FinanceBody, MonetarySummation

    def sd(total: str) -> SemanticExtraction:
        return SemanticExtraction(bodies={"finance_body": FinanceBody(
            monetary_summation=MonetarySummation(grand_total_amount=Decimal(total)))})
    logical_repo.save(VirtualDocument(uuid="via-repo", semantic_data=sd("120.50"),
                                      source_mapping=[SourceReference(file_uuid="f", pages=[1])]))
    logical_repo.save(VirtualDocument(uuid="via-update", source_mapping=[SourceReference(file_uuid="f", pages=[1])]))
    memory_db.update_document_metadata("via-update", {"semantic_data": sd("130.00")})

    stored = [r[0] for r in memory_db.connection.execute(
        "SELECT json_type(semantic_data, '$.bodies.finance_body.monetary_summation.grand_total_amount') "
        "FROM virtual_documents ORDER BY uuid")]
    assert stored[0] == stored[1]

    query = {"field": "semantic:bodies.finance_body.monetary_summation.grand_total_amount", "op": "lt", "value": 1000}
    assert sorted(d.uuid for d in memory_db.search_documents_advanced(query)) == ["via-repo", "via-update"]
