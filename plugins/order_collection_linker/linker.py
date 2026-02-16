
import uuid
from typing import List, Dict, Set, Any
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMessageBox

from core.plugins.base import KPaperFluxPlugin
from core.models.virtual import VirtualDocument as Document

class OrderCollectionLinker(KPaperFluxPlugin):
    """
    Plugin implementing 'Partner-Verzeigerung' by creating collections.
    This service analyzes technical reference IDs to establish 
    organic document chains (Offer -> Order -> Invoice).
    """
    
    def get_name(self) -> str:
        return "Order Collection Linker"

    def get_tool_actions(self, parent=None) -> List[QAction]:
        action = QAction("Create Order Collections...", parent)
        action.triggered.connect(lambda: self.run_collection_flow(parent))
        return [action]

    def run_collection_flow(self, parent):
        """
        Executes the collection discovery logic.
        """
        db = self.api.db
        all_docs = db.get_all_entities_view()
        if not all_docs:
            QMessageBox.information(parent, "Order Collection", "No document data available to build collections.")
            return

        # Map to track which IDs point to which documents
        # Key: Technical ID (e.g. 'PRJ-2024-001'), Value: Set of Document UUIDs
        nexus_map: Dict[str, Set[str]] = {}
        
        # Track established process_ids
        doc_to_process: Dict[str, str] = {d.uuid: d.process_id for d in all_docs if d.process_id}

        for doc in all_docs:
            identifiers = self._extract_nexus_identifiers(doc)
            for ident in identifiers:
                if ident not in nexus_map:
                    nexus_map[ident] = set()
                nexus_map[ident].add(doc.uuid)

        # Build Document Adjacency (Sharing a common nexus ID)
        links: Dict[str, Set[str]] = {d.uuid: set() for d in all_docs}
        for cluster in nexus_map.values():
            for u1 in cluster:
                for u2 in cluster:
                    if u1 != u2:
                        links[u1].add(u2)

        # Connected Components Discovery
        visited = set()
        process_clusters = []
        for doc in all_docs:
            if doc.uuid not in visited:
                cluster = []
                stack = [doc.uuid]
                visited.add(doc.uuid)
                while stack:
                    curr = stack.pop()
                    cluster.append(curr)
                    for neighbor in links[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            stack.append(neighbor)
                if len(cluster) > 1:
                    process_clusters.append(cluster)

        # Apply Process Mapping
        updates = 0
        new_processes = 0
        
        with db.connection:
            for cluster in process_clusters:
                # Does anyone in the cluster have an existing PID?
                active_pid = next((doc_to_process[u] for u in cluster if u in doc_to_process), None)
                
                if not active_pid:
                    active_pid = f"nexus_{str(uuid.uuid4())[:8]}"
                    new_processes += 1
                
                for u in cluster:
                    if doc_to_process.get(u) != active_pid:
                        db.update_document_metadata(u, {"process_id": active_pid})
                        updates += 1

        # Summary
        msg = (f"Order Collection Discovery Complete:\n\n"
               f"• Identified {len(process_clusters)} collections\n"
               f"• Established {new_processes} new organic process IDs\n"
               f"• Linked {updates} documents semantically")
        
        QMessageBox.information(parent, "Order Collection Linker", msg)
        
        if updates > 0 and self.api.main_window:
            self.api.main_window.list_widget.refresh_list()

    def _extract_nexus_identifiers(self, doc: Document) -> Set[str]:
        """
        Gathers technical reference tokens for organic linking.
        Prioritizes high-fidelity extraction fields from Stage 2.
        """
        tokens = set()
        
        # 1. Standard Header identifiers
        if doc.doc_number: tokens.add(str(doc.doc_number).strip().upper())
            
        # 2. Financial Context (EN 16931 BT-fields)
        fb = doc.semantic_data.bodies.get("finance_body")
        if fb:
            for field in ["invoice_number", "order_number", "customer_id", "project_reference", "buyer_reference"]:
                val = getattr(fb, field, None)
                if val: tokens.add(str(val).strip().upper())

        # 3. Dedicated Semantic References list (Neutral IDs)
        if doc.semantic_data.meta_header and doc.semantic_data.meta_header.references:
            for ref in doc.semantic_data.meta_header.references:
                if ref.ref_value:
                    tokens.add(str(ref.ref_value).strip().upper())
                    
        # Noise Filter: min length 3, ignore common generic patterns
        return {t for t in tokens if len(t) > 2 and t not in ["NULL", "NONE", "UNKNOWN", "RECHNUNG"]}

