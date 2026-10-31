"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_tag_operations.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Rename, delete and merge of user tags against a real database.
------------------------------------------------------------------------------
"""
import pytest

from core.database import DatabaseManager
from core.models.virtual import VirtualDocument as Document


@pytest.fixture
def db() -> DatabaseManager:
    db = DatabaseManager(":memory:")
    db.init_db()
    db.insert_document(Document(uuid="a", tags=["tax", "2025", 'say "hi"']))
    db.insert_document(Document(uuid="b", tags=["taxes", "50%_off"]))
    db.insert_document(Document(uuid="c", tags=[]))
    return db


def _tags(db: DatabaseManager, uuid: str) -> list:
    return db.get_document_by_uuid(uuid).tags


def test_rename_tag_matches_exactly(db):
    assert db.rename_tag("tax", "Steuer") == 1
    assert _tags(db, "a") == ["Steuer", "2025", 'say "hi"']
    assert _tags(db, "b") == ["taxes", "50%_off"]


def test_rename_tag_with_quotes_and_wildcards(db):
    assert db.rename_tag('say "hi"', "greeting") == 1
    assert db.rename_tag("50%_off", "sale") == 1
    assert _tags(db, "a")[-1] == "greeting"
    assert _tags(db, "b") == ["taxes", "sale"]


def test_rename_into_existing_tag_does_not_duplicate(db):
    assert db.rename_tag("2025", "tax") == 1
    assert _tags(db, "a") == ["tax", 'say "hi"']


def test_delete_tag(db):
    assert db.delete_tag("tax") == 1
    assert _tags(db, "a") == ["2025", 'say "hi"']
    assert db.delete_tag("unknown") == 0


def test_merge_tags(db):
    assert db.merge_tags(["tax", "taxes"], "Steuer") == 2
    assert _tags(db, "a") == ["2025", 'say "hi"', "Steuer"]
    assert _tags(db, "b") == ["50%_off", "Steuer"]
    assert _tags(db, "c") == []


def test_invalid_tag_json_is_skipped(db):
    db.connection.execute("UPDATE virtual_documents SET tags = 'not json' WHERE uuid = 'c'")
    db.connection.commit()
    assert db.rename_tag("tax", "Steuer") == 1
