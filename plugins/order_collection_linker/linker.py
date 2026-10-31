"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           plugins/order_collection_linker/linker.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Plugin that links documents of one order chain (offer, order,
                invoice) into collections.
------------------------------------------------------------------------------
"""

import re
import uuid
from typing import List, Dict, Set
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMessageBox

from core.plugins.base import KPaperFluxPlugin
from core.models.virtual import VirtualDocument as Document

# Fields and reference types that link documents of one order chain. Customer numbers and
# buyer references stay the same across all invoices of a supplier and would merge unrelated orders.
LINKING_FINANCE_FIELDS = ("invoice_number", "order_number", "project_reference")
NON_LINKING_REFERENCE_TYPES = {"CUSTOMER_ID", "CUSTOMER_NUMBER", "BUYER_REFERENCE", "ACCOUNT_NUMBER",
                               "TAX_ID", "VAT_ID", "IBAN"}
GENERIC_TOKENS = {"NULL", "NONE", "UNKNOWN", "RECHNUNG"}


class OrderCollectionLinker(KPaperFluxPlugin):
    """
    Plugin implementing 'Partner-Verzeigerung' by creating collections.
    This service analyzes technical reference IDs to establish 
    organic document chains (Offer -> Order -> Invoice).
    """
    
    def get_name(self) -> str:
        return self.tr("Order Collection Linker")

    def get_tool_actions(self, parent=None) -> List[QAction]:
        action = QAction(self.tr("Create Order Collections..."), parent)
        action.triggered.connect(lambda: self.run_collection_flow(parent))
        return [action]

    def run_collection_flow(self, parent) -> None:
        """
        Executes the collection discovery logic.
        """
        db = self.api.db
        all_docs = db.get_all_entities_view()
        if not all_docs:
            QMessageBox.information(parent, self.tr("Order Collection"), self.tr("No document data available to build collections."))
            return

        # Track established process_ids
        doc_to_process: Dict[str, str] = {d.uuid: d.process_id for d in all_docs if d.process_id}
        process_clusters = self.find_process_clusters(all_docs)

        # Apply Process Mapping
        updates = 0
        new_processes = 0
        
        with db.transaction():
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
        msg = (self.tr("Order Collection Discovery Complete:") + "\n\n"
               f"• {self.tr('Identified %1 collections').replace('%1', str(len(process_clusters)))}\n"
               f"• {self.tr('Established %1 new organic process IDs').replace('%1', str(new_processes))}\n"
               f"• {self.tr('Linked %1 documents semantically').replace('%1', str(updates))}")
        
        QMessageBox.information(parent, self.tr("Order Collection Linker"), msg)
        
        if updates > 0 and self.api.main_window:
            self.api.main_window.list_widget.refresh_list()

    def find_process_clusters(self, docs: List[Document]) -> List[List[str]]:
        """
        Groups documents that share a linking identifier (directly or through others).

        Returns:
            Lists of document UUIDs with at least two members.
        """
        nexus_map: Dict[str, Set[str]] = {}
        for doc in docs:
            for ident in self._extract_nexus_identifiers(doc):
                nexus_map.setdefault(ident, set()).add(doc.uuid)

        links: Dict[str, Set[str]] = {d.uuid: set() for d in docs}
        for members in nexus_map.values():
            for uid in members:
                links[uid] |= members - {uid}

        visited: Set[str] = set()
        clusters: List[List[str]] = []
        for doc in docs:
            if doc.uuid in visited:
                continue
            cluster, stack = [], [doc.uuid]
            visited.add(doc.uuid)
            while stack:
                current = stack.pop()
                cluster.append(current)
                for neighbor in links[current] - visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
            if len(cluster) > 1:
                clusters.append(cluster)
        return clusters

    def _extract_nexus_identifiers(self, doc: Document) -> Set[str]:
        """
        Gathers technical reference tokens for organic linking.
        Prioritizes high-fidelity extraction fields from Stage 2.
        """
        sd = doc.semantic_data
        if sd is None:
            return set()
        tokens = set()

        # 1. Standard Header identifiers
        if doc.doc_number:
            tokens.add(str(doc.doc_number).strip().upper())

        # 2. Financial Context (EN 16931 BT-fields)
        fb = sd.bodies.get("finance_body")
        if fb:
            for field in LINKING_FINANCE_FIELDS:
                val = getattr(fb, field, None)
                if val:
                    tokens.add(str(val).strip().upper())

        # 3. Dedicated Semantic References list (Neutral IDs)
        if sd.meta_header and sd.meta_header.references:
            for ref in sd.meta_header.references:
                if ref.ref_value and str(ref.ref_type).upper() not in NON_LINKING_REFERENCE_TYPES:
                    tokens.add(str(ref.ref_value).strip().upper())

        # Noise filter: identifiers have at least 4 characters and a digit
        return {t for t in tokens if len(t) >= 4 and re.search(r"\d", t) and t not in GENERIC_TOKENS}

