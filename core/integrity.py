"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/integrity.py
Version:        1.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Integrity management service for coordinating Database and Vault
                consistency. Handles orphan detection, ghost files, and
                de-duplication logic.
------------------------------------------------------------------------------
"""

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from core.database import DatabaseManager
from core.document import Document
from core.models.virtual import VirtualDocument
from core.repositories.logical_repo import LogicalRepository
from core.repositories.physical_repo import PhysicalRepository
from core.vault import DocumentVault


@dataclass
class IntegrityReport:
    """
    Data container for integrity discrepancies.
    """

    orphans: List[Document]  # Entities pointing to missing physical files/entries
    ghosts: List[Path]  # Files in Vault not used by any Entity


class IntegrityManager:
    """
    Checks for consistency between Database and Vault storage.
    Enhanced for Stage 0/1 Architecture and Maintenance tasks.
    """

    def __init__(self, db: DatabaseManager, vault: DocumentVault) -> None:
        """
        Initializes the IntegrityManager.

        Args:
            db: The DatabaseManager instance.
            vault: The DocumentVault instance.
        """
        self.db = db
        self.vault = vault
        self.phys_repo = PhysicalRepository(self.db)
        self.logic_repo = LogicalRepository(self.db)

    def _compute_sha256(self, path: Path) -> str:
        """
        Helper to calculate SHA256 of a file.

        Args:
            path: Path to the file.

        Returns:
            The SHA256 hash string.

        Raises:
            IOError: If the file cannot be read.
        """
        sha256_hash = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            print(f"Error hashing {path}: {e}")
            raise

    def check_integrity(self) -> IntegrityReport:
        """
        Scans DB and Vault to find discrepancies.

        Returns:
            An IntegrityReport containing found orphans and ghosts.
        """
        # 1. Get all logical entities
        all_entities = self.logic_repo.get_all()

        # 2. Get all Vault files
        vault_path = Path(self.vault.base_path)
        vault_files = list(vault_path.glob("*.pdf"))
        # Phase 2.0: Physical files might have other extensions, but vault stores as .pdf usually
        vault_basenames = {f.name for f in vault_files}

        # Map basename to path for ghosts
        file_map = {f.name: f for f in vault_files}

        # Identify Orphans (Entity exists but referenced physical file missing on disk or DB)
        orphans: List[Document] = []
        used_filenames: Set[str] = set()

        all_phys = {pf.uuid: pf for pf in self.phys_repo.get_all()}

        for ent in all_entities:
            ent_broken = False
            if not ent.source_mapping:
                ent_broken = True
            else:
                for ref in ent.source_mapping:
                    pf = all_phys.get(ref.file_uuid)
                    if not pf or not pf.file_path:
                        ent_broken = True
                        break

                    fname = os.path.basename(pf.file_path)
                    if fname not in vault_basenames:
                        ent_broken = True
                        break
                    else:
                        used_filenames.add(fname)

            if ent_broken:
                legacy_doc = Document(uuid=ent.uuid, original_filename=ent.export_filename or f"Entity {ent.uuid[:8]}", status=ent.status)
                orphans.append(legacy_doc)

        # Identify Ghosts (File on disk but not referenced by any Entity)
        ghosts: List[Path] = []
        for fname in vault_basenames:
            if fname not in used_filenames:
                ghosts.append(file_map[fname])

        return IntegrityReport(orphans=orphans, ghosts=ghosts)

    # --- ACTION METHODS ---

    def prune_orphaned_vault_files(self) -> int:
        """
        Deletes all files in the vault that have no logical reference.

        Returns:
            The number of files deleted.
        """
        print("\n=== PRUNE: Orphaned Vault Files ===")
        report = self.check_integrity()
        count = 0
        for g in report.ghosts:
            try:
                print(f"Deleting ghost file: {g.name}")
                g.unlink()
                count += 1
            except Exception as e:
                print(f"Error deleting {g.name}: {e}")

        print(f"Finished. Removed {count} files.")
        print("===================================\n")
        return count

    def prune_broken_entity_references(self) -> int:
        """
        Deletes all entities that point to non-existent vault files.

        Returns:
            The number of entities deleted.
        """
        print("\n=== PRUNE: Broken Entity References ===")
        report = self.check_integrity()
        count = 0
        for o in report.orphans:
            try:
                print(f"Deleting broken entity: {o.uuid}")
                self.logic_repo.delete_by_uuid(o.uuid)
                count += 1
            except Exception as e:
                print(f"Error deleting entity {o.uuid}: {e}")

        print(f"Finished. Removed {count} entities.")
        print("=======================================\n")
        return count

    def deduplicate_vault(self) -> None:
        """
        Performs content-based deduplication in the vault (live hashing).
        1. Computes hash for every physical file.
        2. Deletes newer physical duplicates.
        3. Prunes broken entities.
        4. Identifies and deletes logical entities with identical source mappings.
        """
        print("\n=== ACTION: Deduplicate Vault (LIVE Hash/Size) ===")

        # 1. Physical Deduplication
        all_phys = self.phys_repo.get_all()
        hash_groups: Dict[str, List] = {}

        print(f"Phase 1: Analyzing {len(all_phys)} physical records for duplicates...")

        for pf in all_phys:
            if not pf.file_path:
                continue
            path = Path(pf.file_path)

            if not path.exists():
                continue

            live_size = path.stat().st_size
            live_hash = self._compute_sha256(path)

            if not live_hash:
                continue

            key = f"{live_hash}_{live_size}"
            if key not in hash_groups:
                hash_groups[key] = []
            hash_groups[key].append(pf)

        phys_deleted = 0
        for key, files in hash_groups.items():
            if len(files) < 2:
                continue

            files.sort(key=lambda x: x.created_at if x.created_at else "")
            keep = files[0]
            redundant = files[1:]

            print(f"  [Match] Keep oldest: {keep.uuid} ({key[:10]}...)")
            for red in redundant:
                print(f"    -> Deleting physical duplicate: {red.uuid}")
                if red.file_path and os.path.exists(red.file_path):
                    try:
                        os.remove(red.file_path)
                    except Exception:
                        pass
                self.phys_repo.delete(red.uuid)
                phys_deleted += 1

        # 2. Prune Broken Entities
        print("\nPhase 2: Pruning entities with broken references...")
        logic_broken_deleted = self.prune_broken_entity_references()

        # 3. Logical Deduplication (Identical Mappings)
        print("\nPhase 3: Finding logical duplicates (identical document content references)...")
        all_entities = self.logic_repo.get_all()
        mapping_groups: Dict[str, List] = {}
        for ent in all_entities:
            # We use the JSON representation of the mapping as the key
            m_key = ent.get_mapping_json()
            if m_key not in mapping_groups:
                mapping_groups[m_key] = []
            mapping_groups[m_key].append(ent)

        logic_redundant_deleted = 0
        for mkey, ents in mapping_groups.items():
            if len(ents) < 2:
                continue
            ents.sort(key=lambda x: x.created_at if x.created_at else "")
            redundant = ents[1:]
            print(f"  [Match] Keeping oldest entity: {ents[0].uuid}. Found {len(redundant)} redundant entries.")
            for red in redundant:
                print(f"    -> Deleting redundant entity: {red.uuid}")
                self.logic_repo.delete_by_uuid(red.uuid)
                logic_redundant_deleted += 1

        print("\nDeduplication complete.")
        print(f"- Physical Duplicates removed: {phys_deleted}")
        print(f"- Broken Entities removed: {logic_broken_deleted}")
        print(f"- Redundant Logical Entities removed: {logic_redundant_deleted}")
        print("========================================================\n")

    # --- LEGACY METHODS (Required by UI) ---
    def resolve_orphan(self, doc: Document) -> None:
        """Legacy helper to resolve an orphan by deleting the entity."""
        self.logic_repo.delete_by_uuid(doc.uuid)

    def delete_ghost_file(self, path: Path) -> None:
        """Legacy helper to delete a ghost file."""
        if path.exists():
            path.unlink()

    def show_orphaned_vault_files(self) -> None:
        """Debug print of orphaned files."""
        report = self.check_integrity()
        print("\n=== DEBUG: Orphaned Vault Files ===")
        if not report.ghosts:
            print("No orphaned files found.")
        else:
            for g in report.ghosts:
                print(f"  - {g.name}")
        print("====================================\n")

    def show_broken_entity_references(self) -> None:
        """Debug print of broken entities."""
        report = self.check_integrity()
        print("\n=== DEBUG: Broken Entity References ===")
        if not report.orphans:
            print("No broken entities found.")
        else:
            for o in report.orphans:
                print(f"  - Entity {o.uuid}")
        print("=======================================\n")
