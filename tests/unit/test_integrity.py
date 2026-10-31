
import pytest
import tempfile
from unittest.mock import MagicMock, patch
from core.database import DatabaseManager
from core.vault import DocumentVault
from core.models.virtual import VirtualDocument as Document
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


# --- Real database and vault -------------------------------------------------

from core.models.physical import PhysicalFile
from core.models.virtual import SourceReference
from core.repositories.logical_repo import LogicalRepository
from core.repositories.physical_repo import PhysicalRepository


@pytest.fixture
def real_setup(tmp_path):
    db = DatabaseManager(str(tmp_path / "integrity.db"))
    db.init_db()
    vault = DocumentVault(str(tmp_path / "vault"))
    return db, vault, PhysicalRepository(db), LogicalRepository(db)


def _add_file(vault, phys_repo, uuid: str, suffix: str, content: bytes, created_at: str) -> None:
    path = vault.base_path / f"{uuid}{suffix}"
    path.write_bytes(content)
    phys_repo.save(PhysicalFile(uuid=uuid, original_filename=f"scan{suffix}", file_path=str(path),
                                file_size=len(content), created_at=created_at))


def _add_doc(logic_repo, uuid: str, file_uuid: str, pages: list) -> None:
    logic_repo.save(Document(uuid=uuid, source_mapping=[SourceReference(file_uuid=file_uuid, pages=pages)]))


def test_check_integrity_counts_non_pdf_originals(real_setup):
    db, vault, phys_repo, logic_repo = real_setup
    _add_file(vault, phys_repo, "img-1", ".png", b"synthetic image", "2026-01-01T00:00:00")
    _add_doc(logic_repo, "doc-img", "img-1", [1])
    (vault.base_path / "derived").mkdir(exist_ok=True)
    (vault.base_path / ".directory").write_text("[Desktop Entry]")

    report = IntegrityManager(db, vault).check_integrity()

    assert report.orphans == []
    assert report.ghosts == []


def test_deduplicate_vault_keeps_documents_of_duplicate_files(real_setup):
    db, vault, phys_repo, logic_repo = real_setup
    _add_file(vault, phys_repo, "file-old", ".pdf", b"%PDF-1.4 same", "2026-01-01T00:00:00")
    _add_file(vault, phys_repo, "file-new", ".pdf", b"%PDF-1.4 same", "2026-02-01T00:00:00")
    _add_file(vault, phys_repo, "img-1", ".png", b"synthetic image", "2026-01-01T00:00:00")
    _add_doc(logic_repo, "doc-old", "file-old", [1])
    _add_doc(logic_repo, "doc-new", "file-new", [2])
    _add_doc(logic_repo, "doc-img", "img-1", [1])

    IntegrityManager(db, vault).deduplicate_vault()

    assert not (vault.base_path / "file-new.pdf").exists()
    assert phys_repo.get_by_uuid("file-new") is None
    assert (vault.base_path / "img-1.png").exists()
    moved = logic_repo.get_by_uuid("doc-new")
    assert moved is not None
    assert [ref.file_uuid for ref in moved.source_mapping] == ["file-old"]
    assert logic_repo.get_by_uuid("doc-old") is not None
    assert logic_repo.get_by_uuid("doc-img") is not None


def test_deduplicate_vault_merges_identical_documents(real_setup):
    db, vault, phys_repo, logic_repo = real_setup
    _add_file(vault, phys_repo, "file-old", ".pdf", b"%PDF-1.4 same", "2026-01-01T00:00:00")
    _add_file(vault, phys_repo, "file-new", ".pdf", b"%PDF-1.4 same", "2026-02-01T00:00:00")
    _add_doc(logic_repo, "doc-old", "file-old", [1])
    _add_doc(logic_repo, "doc-new", "file-new", [1])

    IntegrityManager(db, vault).deduplicate_vault()

    active = [d.uuid for d in logic_repo.get_all() if not d.deleted]
    assert active == ["doc-old"]
    assert logic_repo.get_by_uuid("doc-new").deleted  # in the trash, not purged


def test_deduplicate_keeps_the_active_copy_over_a_trashed_older_one(real_setup):
    db, vault, phys_repo, logic_repo = real_setup
    _add_file(vault, phys_repo, "file-1", ".pdf", b"%PDF-1.4 same", "2026-01-01T00:00:00")
    logic_repo.save(Document(uuid="old-trashed", created_at="2026-01-01T00:00:00", deleted=True,
                             source_mapping=[SourceReference(file_uuid="file-1", pages=[1])]))
    logic_repo.save(Document(uuid="new-active", created_at="2026-02-01T00:00:00",
                             source_mapping=[SourceReference(file_uuid="file-1", pages=[1])]))

    IntegrityManager(db, vault).deduplicate_vault()

    assert not logic_repo.get_by_uuid("new-active").deleted


def test_locked_duplicate_is_never_touched(real_setup):
    db, vault, phys_repo, logic_repo = real_setup
    _add_file(vault, phys_repo, "file-1", ".pdf", b"%PDF-1.4 same", "2026-01-01T00:00:00")
    for uuid, created in (("a", "2026-01-01T00:00:00"), ("b", "2026-02-01T00:00:00")):
        logic_repo.save(Document(uuid=uuid, created_at=created, is_immutable=True,
                                 source_mapping=[SourceReference(file_uuid="file-1", pages=[1])]))

    IntegrityManager(db, vault).deduplicate_vault()

    assert not logic_repo.get_by_uuid("a").deleted and not logic_repo.get_by_uuid("b").deleted


def test_prune_refuses_when_vault_is_empty(real_setup):
    from core.integrity import IntegrityCheckRefused
    db, vault, phys_repo, logic_repo = real_setup
    phys_repo.save(PhysicalFile(uuid="file-1", original_filename="a.pdf",
                                file_path=str(vault.base_path / "file-1.pdf")))
    _add_doc(logic_repo, "doc-1", "file-1", [1])

    with pytest.raises(IntegrityCheckRefused):
        IntegrityManager(db, vault).prune_broken_entity_references()
    with pytest.raises(IntegrityCheckRefused):
        IntegrityManager(db, vault).deduplicate_vault()
    assert not logic_repo.get_by_uuid("doc-1").deleted


def test_prune_refuses_mass_changes(real_setup):
    from core.integrity import IntegrityCheckRefused
    db, vault, phys_repo, logic_repo = real_setup
    _add_file(vault, phys_repo, "kept", ".pdf", b"%PDF-1.4 kept", "2026-01-01T00:00:00")
    _add_doc(logic_repo, "doc-kept", "kept", [1])
    for i in range(6):  # vault files of another profile or a wrong database
        (vault.base_path / f"foreign-{i}.pdf").write_bytes(b"%PDF-1.4 foreign")
        _add_doc(logic_repo, f"doc-missing-{i}", f"missing-{i}", [1])

    manager = IntegrityManager(db, vault)
    with pytest.raises(IntegrityCheckRefused):
        manager.prune_broken_entity_references()
    with pytest.raises(IntegrityCheckRefused):
        manager.prune_orphaned_vault_files()
    assert len(list(vault.base_path.glob("foreign-*.pdf"))) == 6


def test_prune_moves_broken_entities_to_trash(real_setup):
    db, vault, phys_repo, logic_repo = real_setup
    for i in range(4):
        _add_file(vault, phys_repo, f"file-{i}", ".pdf", f"%PDF-1.4 {i}".encode(), "2026-01-01T00:00:00")
        _add_doc(logic_repo, f"doc-{i}", f"file-{i}", [1])
    _add_doc(logic_repo, "doc-broken", "missing", [1])

    assert IntegrityManager(db, vault).prune_broken_entity_references() == 1
    assert logic_repo.get_by_uuid("doc-broken").deleted


def test_intact_second_file_of_a_broken_entity_is_no_ghost(real_setup):
    db, vault, phys_repo, logic_repo = real_setup
    _add_file(vault, phys_repo, "intact", ".pdf", b"%PDF-1.4 intact", "2026-01-01T00:00:00")
    logic_repo.save(Document(uuid="doc-mixed", source_mapping=[SourceReference(file_uuid="missing", pages=[1]),
                                                               SourceReference(file_uuid="intact", pages=[1])]))

    report = IntegrityManager(db, vault).check_integrity()

    assert [o.uuid for o in report.orphans] == ["doc-mixed"]
    assert report.ghosts == []
