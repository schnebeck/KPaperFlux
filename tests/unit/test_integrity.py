
import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.database import DatabaseManager
from core.vault import DocumentVault
from core.document import Document
from core.integrity import IntegrityManager

@pytest.fixture
def mock_db():
    db = MagicMock(spec=DatabaseManager)
    db.connection = MagicMock()
    return db

@pytest.fixture
def temp_vault():
    with tempfile.TemporaryDirectory() as d:
        yield DocumentVault(d)

@patch("core.integrity.PhysicalRepository")
@patch("core.integrity.LogicalRepository")
def test_integrity_check_clean(mock_logic, mock_phys, mock_db, temp_vault):
    # Setup: 1 Doc in DB and Vault
    # Use VirtualDocument for logic_repo mock
    from core.models.virtual import SourceReference, VirtualDocument
    from core.models.physical import PhysicalFile

    p1 = PhysicalFile(uuid="uuid-1", original_filename="doc1.pdf", file_path=str(temp_vault.base_path / "uuid-1.pdf"))
    mock_phys.return_value.get_all.return_value = [p1]

    v1 = VirtualDocument(uuid="v1", source_mapping=[SourceReference(file_uuid="uuid-1", pages=[1])])
    mock_logic.return_value.get_all.return_value = [v1]

    # Create file
    path = temp_vault.base_path / "uuid-1.pdf"
    path.write_text("content")

    manager = IntegrityManager(mock_db, temp_vault)
    report = manager.check_integrity()

    assert len(report.orphans) == 0
    assert len(report.ghosts) == 0


@patch("core.integrity.PhysicalRepository")
@patch("core.integrity.LogicalRepository")
def test_integrity_orphans(mock_logic, mock_phys, mock_db, temp_vault):
    # Setup: 2 Docs in DB, 1 in Vault
    from core.models.virtual import SourceReference, VirtualDocument
    from core.models.physical import PhysicalFile

    p1 = PhysicalFile(uuid="uuid-1", original_filename="doc1.pdf", file_path=str(temp_vault.base_path / "uuid-1.pdf"))
    p2 = PhysicalFile(uuid="uuid-2", original_filename="doc2.pdf", file_path=str(temp_vault.base_path / "uuid-2.pdf"))
    mock_phys.return_value.get_all.return_value = [p1, p2]

    v1 = VirtualDocument(uuid="v1", source_mapping=[SourceReference(file_uuid="uuid-1", pages=[1])])
    v2 = VirtualDocument(uuid="v2", source_mapping=[SourceReference(file_uuid="uuid-2", pages=[1])])
    mock_logic.return_value.get_all.return_value = [v1, v2]

    # Create only file 1
    (temp_vault.base_path / "uuid-1.pdf").write_text("content")

    manager = IntegrityManager(mock_db, temp_vault)
    report = manager.check_integrity()

    assert len(report.orphans) == 1
    assert report.orphans[0].uuid == "v2"
    assert len(report.ghosts) == 0


@patch("core.integrity.PhysicalRepository")
@patch("core.integrity.LogicalRepository")
def test_integrity_ghosts(mock_logic, mock_phys, mock_db, temp_vault):
    # Setup: 1 Doc in DB, 2 in Vault
    from core.models.virtual import SourceReference, VirtualDocument
    from core.models.physical import PhysicalFile

    p1 = PhysicalFile(uuid="uuid-1", original_filename="doc1.pdf", file_path=str(temp_vault.base_path / "uuid-1.pdf"))
    mock_phys.return_value.get_all.return_value = [p1]

    v1 = VirtualDocument(uuid="v1", source_mapping=[SourceReference(file_uuid="uuid-1", pages=[1])])
    mock_logic.return_value.get_all.return_value = [v1]

    # Create file 1 and 2
    (temp_vault.base_path / "uuid-1.pdf").write_text("content")
    (temp_vault.base_path / "uuid-ghost.pdf").write_text("boo")

    manager = IntegrityManager(mock_db, temp_vault)
    report = manager.check_integrity()

    assert len(report.orphans) == 0
    assert len(report.ghosts) == 1
    assert report.ghosts[0].name == "uuid-ghost.pdf"
