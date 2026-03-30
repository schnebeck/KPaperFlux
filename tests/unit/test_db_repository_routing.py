"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_db_repository_routing.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Code
Description:    Tests that DatabaseManager routes hydration calls through
                LogicalRepository and PhysicalRepository instead of
                performing direct SQL hydration bypasses.
------------------------------------------------------------------------------
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from core.database import DatabaseManager
from core.models.physical import PhysicalFile
from core.models.virtual import VirtualDocument


@pytest.fixture
def memory_db() -> DatabaseManager:
    db = DatabaseManager(":memory:")
    return db


# ---------------------------------------------------------------------------
# get_document_by_uuid — routed via LogicalRepository
# ---------------------------------------------------------------------------

def test_get_document_routes_through_logical_repo(memory_db: DatabaseManager) -> None:
    """DatabaseManager.get_document_by_uuid must delegate to logical_repo.get_by_uuid."""
    mock_doc = VirtualDocument(uuid=str(uuid.uuid4()), status="NEW")
    with patch.object(memory_db.logical_repo, "get_by_uuid", return_value=mock_doc) as mock_get:
        result = memory_db.get_document_by_uuid(mock_doc.uuid)

    mock_get.assert_called_once_with(mock_doc.uuid)
    assert result is mock_doc


def test_get_document_returns_none_when_not_found(memory_db: DatabaseManager) -> None:
    """get_document_by_uuid returns None when logical_repo finds nothing."""
    with patch.object(memory_db.logical_repo, "get_by_uuid", return_value=None) as mock_get:
        result = memory_db.get_document_by_uuid("missing-uuid")

    mock_get.assert_called_once_with("missing-uuid")
    assert result is None


def test_get_document_returns_none_when_connection_missing(memory_db: DatabaseManager) -> None:
    """get_document_by_uuid short-circuits and returns None if connection is None."""
    memory_db.connection = None
    with patch.object(memory_db.logical_repo, "get_by_uuid") as mock_get:
        result = memory_db.get_document_by_uuid("any-uuid")

    mock_get.assert_not_called()
    assert result is None


# ---------------------------------------------------------------------------
# get_physical_file — routed via PhysicalRepository
# ---------------------------------------------------------------------------

def test_get_physical_file_routes_through_physical_repo(memory_db: DatabaseManager) -> None:
    """DatabaseManager.get_physical_file must delegate to physical_repo.get_as_dict."""
    expected_dict = {
        "uuid": "p-uuid-1",
        "phash": "abc123",
        "file_path": "/vault/p-uuid-1.pdf",
        "original_filename": "invoice.pdf",
        "file_size": 1024,
        "page_count_phys": 2,
        "raw_ocr_data": None,
        "created_at": "2024-01-01T00:00:00",
    }
    with patch.object(memory_db.physical_repo, "get_as_dict", return_value=expected_dict) as mock_get:
        result = memory_db.get_physical_file("p-uuid-1")

    mock_get.assert_called_once_with("p-uuid-1")
    assert result == expected_dict


def test_get_physical_file_returns_none_when_not_found(memory_db: DatabaseManager) -> None:
    """get_physical_file returns None when physical_repo finds nothing."""
    with patch.object(memory_db.physical_repo, "get_as_dict", return_value=None) as mock_get:
        result = memory_db.get_physical_file("missing-physical-uuid")

    mock_get.assert_called_once_with("missing-physical-uuid")
    assert result is None


def test_get_physical_file_returns_none_when_connection_missing(memory_db: DatabaseManager) -> None:
    """get_physical_file short-circuits and returns None if connection is None."""
    memory_db.connection = None
    with patch.object(memory_db.physical_repo, "get_as_dict") as mock_get:
        result = memory_db.get_physical_file("any-uuid")

    mock_get.assert_not_called()
    assert result is None


# ---------------------------------------------------------------------------
# get_virtual_documents_by_source — routed via LogicalRepository
# ---------------------------------------------------------------------------

def test_get_virtual_documents_by_source_routes_through_logical_repo(memory_db: DatabaseManager) -> None:
    """DatabaseManager.get_virtual_documents_by_source must delegate to logical_repo.get_by_source_file."""
    doc_a = VirtualDocument(uuid=str(uuid.uuid4()), status="NEW")
    doc_b = VirtualDocument(uuid=str(uuid.uuid4()), status="PROCESSED")
    with patch.object(memory_db.logical_repo, "get_by_source_file", return_value=[doc_a, doc_b]) as mock_get:
        result = memory_db.get_virtual_documents_by_source("src-uuid-42")

    mock_get.assert_called_once_with("src-uuid-42")
    assert result == [doc_a, doc_b]


def test_get_virtual_documents_by_source_returns_empty_list_when_none_found(memory_db: DatabaseManager) -> None:
    """get_virtual_documents_by_source returns empty list when no documents reference the source."""
    with patch.object(memory_db.logical_repo, "get_by_source_file", return_value=[]) as mock_get:
        result = memory_db.get_virtual_documents_by_source("orphan-src-uuid")

    mock_get.assert_called_once_with("orphan-src-uuid")
    assert result == []


# ---------------------------------------------------------------------------
# Repository attributes exist on DatabaseManager
# ---------------------------------------------------------------------------

def test_database_manager_has_logical_repo_attribute(memory_db: DatabaseManager) -> None:
    """DatabaseManager must expose logical_repo as an instance attribute."""
    from core.repositories.logical_repo import LogicalRepository
    assert hasattr(memory_db, "logical_repo")
    assert isinstance(memory_db.logical_repo, LogicalRepository)


def test_database_manager_has_physical_repo_attribute(memory_db: DatabaseManager) -> None:
    """DatabaseManager must expose physical_repo as an instance attribute."""
    from core.repositories.physical_repo import PhysicalRepository
    assert hasattr(memory_db, "physical_repo")
    assert isinstance(memory_db.physical_repo, PhysicalRepository)
