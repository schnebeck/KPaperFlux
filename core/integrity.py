
from typing import List, Set
from pathlib import Path
from dataclasses import dataclass
from core.database import DatabaseManager
from core.vault import DocumentVault
from core.document import Document

@dataclass
class IntegrityReport:
    orphans: List[Document] # Documents in DB but missing in Vault
    ghosts: List[Path]      # Files in Vault but missing in DB

class IntegrityManager:
    """
    Checks for consistency between Database and Vault storage.
    """
    def __init__(self, db: DatabaseManager, vault: DocumentVault):
        self.db = db
        self.vault = vault
        
    def check_integrity(self) -> IntegrityReport:
        """
        Scan DB and Vault to find discrepancies.
        """
        # Get all DB documents
        db_docs = self.db.get_all_documents()
        db_uuids = {doc.uuid for doc in db_docs}
        
        # Get all Vault files
        # Only PDF files? Or all files? Spec assumes vault manages PDFs.
        vault_files = list(self.vault.base_path.glob("*.pdf"))
        # Map vault filenames to UUIDs? 
        # Filename convention is {uuid}.pdf
        vault_uuids = set()
        file_map = {}
        
        ghosts = []
        
        for f in vault_files:
            # Name without extension = uuid candidate
            uuid_candidate = f.stem 
            vault_uuids.add(uuid_candidate)
            file_map[uuid_candidate] = f
                 
        orphans = []
        
        # Check Orphans (In DB, not in Vault)
        for doc in db_docs:
            if doc.uuid not in vault_uuids:
                orphans.append(doc)
                
        # Check Ghosts (In Vault, not in DB)
        for uuid in vault_uuids:
            if uuid not in db_uuids:
                ghosts.append(file_map[uuid])
                
        return IntegrityReport(orphans=orphans, ghosts=ghosts)
        
    def resolve_orphan(self, doc: Document):
        """
        Remove orphan entry from DB.
        """
        self.db.delete_document(doc.uuid)
        
    def resolve_ghost(self, path: Path):
        """
        Import ghost file into DB (Recover) OR Delete?
        Usually "resolve" means fix. Import is "Recover". Delete is "Prune".
        We'll provide methods for both used by UI.
        This generic method might just delete? 
        Let's explicitly name them.
        """
        pass
        
    def delete_ghost_file(self, path: Path):
        if path.exists():
            path.unlink()

