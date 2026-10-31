"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_search.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Tests: search.
------------------------------------------------------------------------------
"""

import pytest
import uuid
import datetime
from core.database import DatabaseManager
from core.repositories import LogicalRepository
from core.models.virtual import VirtualDocument

@pytest.fixture
def db_manager():
    db = DatabaseManager(":memory:")
    db.init_db()
    return db

@pytest.fixture
def repo(db_manager):
    return LogicalRepository(db_manager)

def test_search_text(db_manager, repo):
    """Test searching by text content."""
    
    cursor = db_manager.connection.cursor()
    
    doc2_uuid = str(uuid.uuid4())
    v_doc2 = VirtualDocument(
        uuid=doc2_uuid,
        cached_full_text="Grocery list: apples, bananas.",
        created_at=datetime.datetime.now().isoformat()
    )
    
    print("Pre-save check...")
    repo.save(v_doc2)
    print("Post-save check...")
    
    f_rows = cursor.execute("SELECT rowid, * FROM virtual_documents_fts").fetchall()
    print(f"DEBUG: FTS Row count: {len(f_rows)}")
    for r in f_rows:
        print(f"DEBUG: FTS Row: {list(r)}")

    results = db_manager.search_documents(search_text="apples")
    assert len(results) == 1


@pytest.fixture
def searchable(db_manager, repo):
    repo.save(VirtualDocument(uuid="doc-1", cached_full_text="Invoice foo-bar for order: 4711 (paid)"))
    repo.save(VirtualDocument(uuid="doc-2", cached_full_text="Delivery note for order 4712"))
    return db_manager


@pytest.mark.parametrize("text", ["foo-bar", "order:", "(paid", '"unbalanced', "NOT", "AND OR", "^", "*"])
def test_search_with_fts_syntax_characters_does_not_raise(searchable, text):
    searchable.search_documents(search_text=text)


def test_search_hyphenated_word_matches_phrase(searchable):
    assert [d.uuid for d in searchable.search_documents(search_text="foo-bar")] == ["doc-1"]


def test_search_requires_all_words(searchable):
    assert [d.uuid for d in searchable.search_documents(search_text="order paid")] == ["doc-1"]
    assert {d.uuid for d in searchable.search_documents(search_text="order")} == {"doc-1", "doc-2"}


def test_search_keeps_prefix_wildcard(searchable):
    assert [d.uuid for d in searchable.search_documents(search_text="deliv*")] == ["doc-2"]


def test_search_with_only_wildcards_lists_all(searchable):
    assert len(searchable.search_documents(search_text="**")) == 2


def test_hit_counts_and_deep_search_handle_umlauts(db_manager, repo):
    import json as _json
    from core.models.physical import PhysicalFile
    from core.models.virtual import SourceReference
    from core.repositories import PhysicalRepository

    repo.save(VirtualDocument(uuid="doc-u", cached_full_text="Ärger mit Ärger und ärger",
                              source_mapping=[SourceReference(file_uuid="f-old", pages=[1])]))
    assert db_manager.get_hit_counts_for_documents(["doc-u"], "Ärger") == {"doc-u": 3}

    # An older row stored its OCR text ASCII-escaped
    PhysicalRepository(db_manager).save(PhysicalFile(uuid="f-old", original_filename="o.pdf", file_path="/v/o.pdf"))
    db_manager.connection.execute("UPDATE physical_files SET raw_ocr_data = ? WHERE uuid = 'f-old'",
                                  (_json.dumps({"1": "Herr Müller"}),))
    db_manager.connection.commit()
    assert "doc-u" in db_manager.get_virtual_uuids_with_text_content("Müller")


def test_like_wildcards_in_search_text_match_literally(db_manager, repo):
    repo.save(VirtualDocument(uuid="doc-p", cached_full_text="discount 50% off"))
    repo.save(VirtualDocument(uuid="doc-q", cached_full_text="discount 50 percent"))
    assert set(db_manager.get_virtual_uuids_with_text_content("50%")) == {"doc-p"}
