
import uuid
from typing import List, Dict, Set, Any
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMessageBox

from core.plugins.base import KPaperFluxPlugin
from core.models.virtual import VirtualDocument as Document

class ReferenceLinkerPlugin(KPaperFluxPlugin):
    """
    Background-Agent logic for semantic linking ('Partner-Verzeigerung').
    Groups documents into logical processes based on shared reference IDs.
    """
    
    def get_name(self) -> str:
        return "Semantic Reference Linker"

    def get_tool_actions(self, parent=None) -> List[QAction]:
        action = QAction("Run Reference Linking (DMS Global)...", parent)
        action.triggered.connect(lambda: self.run_linker_process(parent))
        return [action]

    def run_linker_process(self, parent):
        """
        Main entry point for the linking process.
        """
        # 1. Fetch all non-deleted documents
        db = self.api.db
        all_docs = db.get_all_entities_view()
        if not all_docs:
            QMessageBox.information(parent, "Reference Linker", "No documents found to analyze.")
            return

        # 2. Build adjacency list for ID matching
        # Key: ID string (e.g. "PRJ-101"), Value: Set of Document UUIDs
        id_to_uuids: Dict[str, Set[str]] = {}
        
        # Keep track of existing process IDs to potentially merge them
        uuid_to_process: Dict[str, str] = {}

        for doc in all_docs:
            if doc.process_id:
                uuid_to_process[doc.uuid] = doc.process_id
            
            # Collect all technical IDs from this document
            ids = self._collect_identifiers(doc)
            for id_val in ids:
                if id_val not in id_to_uuids:
                    id_to_uuids[id_val] = set()
                id_to_uuids[id_val].add(doc.uuid)

        # 3. Find Connected Components
        # Every document is a node. If two documents share an ID, there is an edge.
        adj: Dict[str, Set[str]] = {doc.uuid: set() for doc in all_docs}
        for uuids in id_to_uuids.values():
            for u1 in uuids:
                for u2 in uuids:
                    if u1 != u2:
                        adj[u1].add(u2)

        visited = set()
        groups = []
        for doc in all_docs:
            if doc.uuid not in visited:
                group = []
                stack = [doc.uuid]
                visited.add(doc.uuid)
                while stack:
                    curr = stack.pop()
                    group.append(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            stack.append(neighbor)
                if len(group) > 1:
                    groups.append(group)

        # 4. Assign Process IDs
        count_updated = 0
        processes_created = 0
        
        with db.connection: # Batch update in one transaction
            for group in groups:
                # Decide on a process_id for the group
                target_pid = None
                
                # Check if any member already has a process_id
                for u in group:
                    if u in uuid_to_process:
                        target_pid = uuid_to_process[u]
                        break
                
                if not target_pid:
                    target_pid = f"proc_{str(uuid.uuid4())[:8]}"
                    processes_created += 1
                
                # Apply to all
                for u in group:
                    if uuid_to_process.get(u) != target_pid:
                        db.update_document_metadata(u, {"process_id": target_pid})
                        count_updated += 1

        # 5. UI Feedback
        msg = (f"Linking process finished.\n\n"
               f"- Groups identified: {len(groups)}\n"
               f"- New processes created: {processes_created}\n"
               f"- Document links updated: {count_updated}")
        
        QMessageBox.information(parent, "Reference Linker", msg)
        
        if count_updated > 0 and self.api.main_window:
            self.api.main_window.list_widget.refresh_list()

    def _collect_identifiers(self, doc: Document) -> Set[str]:
        """
        Extracts all technical identifiers from a document's semantic data.
        """
        ids = set()
        
        # 1. Direct Properties
        if doc.doc_number:
            ids.add(str(doc.doc_number).strip())
            
        # 2. Finance Body Specifics (ZUGFeRD)
        fb = doc.semantic_data.bodies.get("finance_body")
        if fb:
            if hasattr(fb, "invoice_number") and fb.invoice_number: ids.add(str(fb.invoice_number).strip())
            if hasattr(fb, "order_number") and fb.order_number: ids.add(str(fb.order_number).strip())
            if hasattr(fb, "customer_id") and fb.customer_id: ids.add(str(fb.customer_id).strip())
            if hasattr(fb, "project_reference") and fb.project_reference: ids.add(str(fb.project_reference).strip())
            if hasattr(fb, "buyer_reference") and fb.buyer_reference: ids.add(str(fb.buyer_reference).strip())

        # 3. Explicit References (Linker-Agent Target)
        if doc.semantic_data.meta_header and doc.semantic_data.meta_header.references:
            for ref in doc.semantic_data.meta_header.references:
                if ref.ref_value:
                    ids.add(str(ref.ref_value).strip())
                    
        # Remove empty or whitespace-only matches
        return {i for i in ids if len(i) > 2} # Ignore extremely short IDs (noise)

