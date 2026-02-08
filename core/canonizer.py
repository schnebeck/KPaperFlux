"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/canonizer.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Canonization service that orchestrates the document processing
                pipeline, including splitting, visual auditing, and extraction.
                Handles the lifecycle from raw logical entities to fully
                extracted canonical data.
------------------------------------------------------------------------------
"""

import json
import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING, Union

from core.ai_analyzer import AIAnalyzer
from core.config import AppConfig
from core.database import DatabaseManager
from core.models.semantic import SemanticExtraction
from core.models.virtual import VirtualDocument as Document
from core.models.canonical_entity import CanonicalEntity, DocType
from core.models.identity import IdentityProfile
from core.models.virtual import SourceReference, VirtualDocument
from core.repositories.logical_repo import LogicalRepository
from core.repositories.physical_repo import PhysicalRepository
from core.rules_engine import RulesEngine
from core.visual_auditor import VisualAuditor
from core.workflow import WorkflowRegistry

if TYPE_CHECKING:
    from core.filter_tree import FilterTree


class CanonizerService:
    """
    Phase 2 Canonizer:
    Scans 'semantic_entities' (Logical Entities) with status='NEW'.
    Resolves text via VirtualDocument -> PhysicalFile.
    Handles Splitting (1 Logical -> N Logical).
    """

    def __init__(
        self,
        db: DatabaseManager,
        analyzer: Optional[AIAnalyzer] = None,
        physical_repo: Optional[PhysicalRepository] = None,
        logical_repo: Optional[LogicalRepository] = None,
        filter_tree: Optional["FilterTree"] = None,
    ) -> None:
        """
        Initializes the CanonizerService.

        Args:
            db: The DatabaseManager instance.
            analyzer: Optional existing AIAnalyzer instance.
            physical_repo: Optional existing PhysicalRepository instance.
            logical_repo: Optional existing LogicalRepository instance.
            filter_tree: Optional existing FilterTree instance.
        """
        self.db = db
        self.config = AppConfig()
        self.filter_tree = filter_tree

        # Repositories (Lazy init or passed)
        self.physical_repo = physical_repo if physical_repo else PhysicalRepository(db)
        self.logical_repo = logical_repo if logical_repo else LogicalRepository(db)

        # Core Components
        if analyzer:
            self.analyzer = analyzer
        else:
            self.analyzer = AIAnalyzer(self.config.get_api_key(), self.config.get_gemini_model())

        self.visual_auditor = VisualAuditor(self.analyzer)
        self.rules_engine = RulesEngine(db, filter_tree) if filter_tree else None
        
        # Phase 3: Workflow Engine
        self.workflow_registry = WorkflowRegistry()
        # Note: In production, the path might be different, but for now we use relative
        self.workflow_registry.load_from_directory("resources/workflows")

    def process_pending_documents(self, limit: int = 10) -> int:
        """
        Scans for Logical Entities with status='NEW' and starts processing them.

        Args:
            limit: Maximum number of documents to process in one batch.

        Returns:
            The number of successfully processed documents.
        """
        if not self.analyzer:
            print("[Canonizer] No AI Analyzer available.")
            return 0

        cursor = self.db.connection.cursor()
        # Fetch entities - but only those NOT currently being processed by another worker
        query = """
            SELECT uuid, status
            FROM virtual_documents
            WHERE status IN ('NEW', 'READY_FOR_PIPELINE', 'STAGE2_PENDING') 
              AND deleted = 0
            LIMIT ?
        """
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()

        # Atomic locking of all candidates
        uuids: List[str] = []
        for row in rows:
            uuid_val, current = row
            target = "PROCESSING_S1" if current in ["NEW", "READY_FOR_PIPELINE"] else "PROCESSING_S2"

            # Atomic update to lock this document
            cursor.execute(
                "UPDATE virtual_documents SET status = ? WHERE uuid = ? AND status = ?",
                (target, uuid_val, current),
            )
            if cursor.rowcount > 0:
                uuids.append(uuid_val)

        self.db.connection.commit()
        if uuids:
            print(f"[Canonizer] Locked {len(uuids)} documents for processing.")

        processed_count = 0
        for uuid_obj in uuids:
            v_doc = self.logical_repo.get_by_uuid(uuid_obj)
            if v_doc:
                # The document is already locked to PROCESSING_S1 or S2 at this point
                try:
                    success = self.process_virtual_document(v_doc)
                    if success:
                        processed_count += 1
                except (NameError, AttributeError, SyntaxError, TypeError, ValueError) as e:
                    print(f"[Canonizer] CRITICAL ERROR processing {uuid_obj}: {e}")
                    traceback.print_exc()
                    raise e  # Propagate critical coding/logic errors to stop the worker
                except Exception as e:
                    print(f"[Canonizer] ERROR processing {uuid_obj}: {e}")
                    traceback.print_exc()
                    # For non-critical exceptions, we might want to release the lock or set a failure status
                    # v_doc.status = 'FAILED'
                    # self.logical_repo.save(v_doc)

        return processed_count

    def _atomic_transition(self, v_doc: VirtualDocument, allowed_old: List[str], target_status: str) -> bool:
        """
        Atomically transitions the document status in the DB.
        Prevents race conditions between background and GUI threads.

        Args:
            v_doc: The VirtualDocument to transition.
            allowed_old: List of allowed old statuses.
            target_status: The target status to transition to.

        Returns:
            True if the transition was successful.
        """
        cursor = self.db.connection.cursor()
        placeholders = ",".join(["?"] * len(allowed_old))
        sql = f"UPDATE virtual_documents SET status = ? WHERE uuid = ? AND status IN ({placeholders})"
        cursor.execute(sql, [target_status, v_doc.uuid] + allowed_old)
        self.db.connection.commit()

        if cursor.rowcount > 0:
            v_doc.status = target_status
            return True
        return False

    def process_virtual_document(self, v_doc: VirtualDocument) -> bool:
        """
        Processes a specific VirtualDocument through the multi-stage pipeline.

        Args:
            v_doc: The VirtualDocument to process.

        Returns:
            True if processing completed successfully (status changed), False otherwise.
        """
        if not self.analyzer:
            return False

        print(f"[Canonizer] Processing {v_doc.uuid}...")

        # Capture original tags to detect manual intervention
        original_tags = getattr(v_doc, "type_tags", [])
        is_manual = "MANUAL_EDIT" in original_tags

        # 1. Resolve Text Content (Lazy Load)
        def loader(fid: str) -> Optional[Any]:
            return self.physical_repo.get_by_uuid(fid)

        full_text = v_doc.resolve_content(loader)
        if not full_text:
            print(f"[Canonizer] No text content resolved for {v_doc.uuid}. Skipping.")
            return False

        v_doc.cached_full_text = full_text
        print(f"[DEBUG] Canonizer Resolved text ({len(full_text)} chars) for {v_doc.uuid}")

        # Reconstruct page list from source_mapping
        pages_text: List[str] = []
        for src in v_doc.source_mapping:
            pf = self.physical_repo.get_by_uuid(src.file_uuid)
            if pf and pf.raw_ocr_data:
                raw = pf.raw_ocr_data
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except json.JSONDecodeError:
                        raw = {}
                if isinstance(raw, dict):
                    for p in src.pages:
                        pages_text.append(raw.get(str(p), ""))

        if not pages_text:
            pages_text = [full_text]

        # Entrance Gate for Resumption / Start
        status = v_doc.status
        is_stage2_resumption = status in ["STAGE2_PENDING", "PROCESSING_S1_5", "PROCESSING_S2"]
        detected_entities: List[Dict[str, Any]] = []
        # is_hybrid = False # Not used later in same scope if commented? No, it's used.
        # split_candidates = [] # Define scope

        if is_stage2_resumption:
            print(f"[AI] Pipeline [RESUME] -> Stage 2 (Status: {status})")
            split_candidates = [
                {
                    "types": v_doc.type_tags or ["OTHER"],
                    "pages": list(range(1, len(pages_text) + 1)),
                    "confidence": 1.0,
                    "direction": v_doc.semantic_data.direction if v_doc.semantic_data else None,
                    "tenant_context": v_doc.semantic_data.tenant_context if v_doc.semantic_data else None,

                }
            ]
            # Restore detected_entities for context in Stage 2
            detected_entities = [{"entity_types": split_candidates[0]["types"]}]
        else:
            # --- START STAGE 1 ---
            print(f"[AI] Stage 1.1 (Classification) [START] -> Pages: {len(pages_text)}")
            # Gate: Only ONE thread can start the process.
            if status in ["NEW", "READY_FOR_PIPELINE"]:
                if not self._atomic_transition(v_doc, ["NEW", "READY_FOR_PIPELINE"], "PROCESSING_S1"):
                    print("[Canonizer] Failed atomic lock for S1. Skipping.")
                    return False
            elif status == "PROCESSING_S1":
                # Already locked by process_pending_documents
                pass
            elif status.startswith("PROCESSING_"):
                # Another worker is already handling this.
                print(f"[Canonizer] Document {v_doc.uuid[:8]} is already {status}. Skipping to avoid overlap.")
                return False

            # 2. AI Analysis (Stage 1: Classification & Split)
            priv_json = self.config.get_private_profile_json()
            bus_json = self.config.get_business_profile_json()
            priv_id = IdentityProfile.model_validate_json(priv_json) if priv_json else None
            bus_id = IdentityProfile.model_validate_json(bus_json) if bus_json else None

            struct_res = self.analyzer.run_stage_1_adaptive(pages_text, priv_id, bus_id)
            print("[AI] Stage 1.1 (Classification) [DONE]")

            if struct_res is None:
                print(f"[Canonizer] Stage 1.1 AI Analysis failed after all retries. Setting STAGE1_HOLD for {v_doc.uuid}.")
                v_doc.status = "STAGE1_HOLD"
                self.logical_repo.save(v_doc)
                return False

            detected_entities = struct_res.get("detected_entities", [])
            is_hybrid = struct_res.get("source_file_summary", {}).get("is_hybrid_document", False)

            if not detected_entities:
                print(f"[Canonizer] Stage 1.1: No entities detected for {v_doc.uuid}.")
                v_doc.status = "PROCESSED"
                v_doc.last_processed_at = datetime.now().isoformat()
                self.logical_repo.save(v_doc)
                return True

            all_tags: List[str] = []
            for ent in detected_entities:
                # Strictly use type_tags from AI response
                types = ent.get("type_tags") or []
                for t in types:
                    if t and t not in all_tags:
                        all_tags.append(t)
            v_doc.type_tags = all_tags

            if is_manual:
                print(f"[Canonizer] Manually edited doc {v_doc.uuid} detected. Skipping auto-split.")
                # We still need to proceed to Stage 2 for this manual document.
                # So we simply set split_candidates to a single entry representing the whole doc.
                split_candidates = [
                    {
                        "types": v_doc.type_tags or ["OTHER"],
                        "pages": list(range(1, len(pages_text) + 1)),
                        "confidence": 1.0,
                    }
                ]
            else:
                has_clear_boundaries = all(ent.get("page_indices") for ent in detected_entities)
                if is_hybrid and not has_clear_boundaries:
                    print("[Canonizer] Stage 1.1 found hybrid but no clear boundaries. Triggering Stage 1.2.")
                    split_candidates = self.analyzer.identify_entities(full_text, detected_entities=detected_entities)

                    if split_candidates is None:
                        print("[Canonizer] Stage 1.2 AI Analysis returned None. Aborting.")
                        return False
                else:
                    split_candidates = []
                    for ent in detected_entities:
                        c_types = ent.get("type_tags") or ["OTHER"]
                        split_candidates.append(
                            {
                                "types": c_types,
                                "pages": ent.get("page_indices", list(range(1, len(pages_text) + 1))),
                                "confidence": ent.get("confidence", 1.0),
                                "direction": ent.get("direction"),
                                "tenant_context": ent.get("tenant_context"),
                            }
                        )

        # 4. Apply Splits
        original_source_map = v_doc.source_mapping
        if not original_source_map:
            return False

        base_ref = original_source_map[0]

        for idx, candidate in enumerate(split_candidates):
            c_types = candidate.get("types", ["OTHER"])
            c_pages = candidate.get("pages", [])

            new_source_pages: List[int] = []
            for lp in c_pages:
                if 0 <= lp - 1 < len(base_ref.pages):
                    new_source_pages.append(base_ref.pages[lp - 1])

            if not new_source_pages:
                continue

            # Target Document
            if idx == 0:
                target_doc = v_doc  # Reuse existing
            else:
                # Create NEW Split Entity
                target_doc = VirtualDocument(uuid=str(uuid.uuid4()), status="NEW", created_at=v_doc.created_at, semantic_data=SemanticExtraction())


            candidate_types = candidate.get("types", [])
            final_tags = list(candidate_types)

            direction = candidate.get("direction", "UNKNOWN")
            if direction != "UNKNOWN" and direction not in final_tags:
                final_tags.append(direction)

            context = candidate.get("tenant_context", "UNKNOWN")
            if context != "UNKNOWN" and f"CTX_{context}" not in final_tags:
                final_tags.append(f"CTX_{context}")

            target_doc.type_tags = final_tags
            target_doc.source_mapping = [SourceReference(file_uuid=base_ref.file_uuid, pages=new_source_pages, rotation=base_ref.rotation)]

            if idx < len(detected_entities):
                # detected_entities are dicts from Stage 1.1 JSON
                if target_doc.semantic_data is None:
                    target_doc.semantic_data = SemanticExtraction()
                
                ent_data = detected_entities[idx]
                target_doc.semantic_data.direction = ent_data.get("direction", "INBOUND")
                target_doc.semantic_data.tenant_context = ent_data.get("tenant_context", "PRIVATE")
                target_doc.semantic_data.type_tags = ent_data.get("type_tags") or []


            # Transition to Stage 2 Readiness
            target_doc.status = "STAGE2_PENDING"
            self.logical_repo.save(target_doc)

            entity_pages = [pages_text[p - 1] for p in c_pages if 0 <= p - 1 < len(pages_text)]
            entity_text = "\n\n".join(entity_pages)

            # [STAGE 1.5] Visual Audit
            audit_res: Optional[Dict[str, Any]] = None
            pf = self.physical_repo.get_by_uuid(base_ref.file_uuid)
            if pf:
                audit_res = self.visual_auditor.run_stage_1_5(
                    pdf_path=pf.file_path,
                    doc_uuid=target_doc.uuid,
                    stage_1_result={"detected_entities": [{"entity_type": t} for t in c_types]},
                    text_content=entity_text,
                    target_pages=new_source_pages,
                )

                if audit_res is None and self.visual_auditor.is_ai_enabled():
                    print(f"[Canonizer] Stage 1.5 AI Failed. Setting STAGE1_5_HOLD for {target_doc.uuid}.")
                    target_doc.status = "STAGE1_5_HOLD"
                    self.logical_repo.save(target_doc)
                    return False

                if audit_res:
                    if target_doc.semantic_data is None:
                        target_doc.semantic_data = SemanticExtraction()
                    target_doc.semantic_data.visual_audit = audit_res


                    target_doc.status = "PROCESSING_S1_5"
                    self.logical_repo.save(target_doc)

                    # Arbiter Logic
                    integrity = audit_res.get("integrity", {})
                    if integrity.get("is_type_match") is False:
                        new_types = integrity.get("suggested_types", [])
                        if new_types:
                            target_doc.type_tags = list(set(new_types + target_doc.type_tags))

                    # Note: We NO LONGER replace entity_text with clean_text from Stage 1.5
                    # because Stage 2 handles text repair comprehensively across all pages.

            # [STAGE 2] Semantic Extraction
            # Gate: Only transition to PROCESSING_S2 if we are currently in a valid preceding state
            if target_doc.status in ["STAGE2_PENDING", "PROCESSING_S1_5", "PROCESSING_S1"]:
                if not self._atomic_transition(target_doc, ["STAGE2_PENDING", "PROCESSING_S1_5", "PROCESSING_S1"], "PROCESSING_S2"):
                    print("[Canonizer] Failed atomic lock for S2. Skipping.")
                    continue

            s1_context = {"type_tags": c_types}

            semantic_extraction = self.analyzer.run_stage_2(
                raw_ocr_pages=entity_pages, stage_1_result=s1_context, stage_1_5_result=audit_res, pdf_path=pf.file_path if pf else None
            )

            if semantic_extraction is None:
                print(f"[Canonizer] Stage 2 FAILED for {target_doc.uuid}. Aborting hydration.")
                target_doc.status = "STAGE2_PENDING" # Re-queue for later
                self.logical_repo.save(target_doc)
                continue

            # Stage 2 result is a Dict from run_stage_2
            # We need to hydrate it into our model
            try:
                new_semantic = SemanticExtraction(**semantic_extraction)
                if target_doc.semantic_data:
                    # 1. Merge existing fields from Stage 1.5 (Visual Audit)
                    new_semantic.visual_audit = target_doc.semantic_data.visual_audit
                    
                    # 2. Merge classification context from Stage 1.1
                    # Only overwrite if Stage 2 explicitly provided a non-empty/non-default value
                    if not semantic_extraction.get("direction") and target_doc.semantic_data.direction:
                        new_semantic.direction = target_doc.semantic_data.direction
                    
                    if not semantic_extraction.get("tenant_context") and target_doc.semantic_data.tenant_context:
                        new_semantic.tenant_context = target_doc.semantic_data.tenant_context
                        
                    if not semantic_extraction.get("type_tags") and target_doc.semantic_data.type_tags:
                        new_semantic.type_tags = target_doc.semantic_data.type_tags

                target_doc.semantic_data = new_semantic
            except Exception as e:
                print(f"[Canonizer] Error hydrating Stage 2 result: {e}")
                # Fallback: keep partial data if possible
                if target_doc.semantic_data is None:
                    target_doc.semantic_data = SemanticExtraction()

            # Generate Filename using hydrated data
            smart_name = self.analyzer.generate_smart_filename(target_doc.semantic_data, target_doc.type_tags)

            target_doc.export_filename = smart_name
            target_doc.cached_full_text = semantic_extraction.get("repaired_text") or entity_text
            
            # Phase 3: Workflow Assignment
            if target_doc.semantic_data and not target_doc.semantic_data.workflow.playbook_id:
                pb = self.workflow_registry.find_playbook_for_tags(target_doc.type_tags)
                if pb:
                    target_doc.semantic_data.workflow.playbook_id = pb.id
                    print(f"[Workflow] Assigned playbook '{pb.id}' to {target_doc.uuid}")

            target_doc.status = "PROCESSED"
            target_doc.last_processed_at = datetime.now().isoformat()

            self.logical_repo.save(target_doc)
            safe_types = [str(t) for t in c_types if t is not None]
            print(f"[Canonizer] Saved Entity {target_doc.uuid} ({', '.join(safe_types)})")

            # [STAGE 1.6] Auto-Tagging
            if self.rules_engine and self.rules_engine.apply_rules_to_entity(target_doc, only_auto=True):
                self.logical_repo.save(target_doc)

        return True

    def _extract_range_text(self, pages_text: List[str], target_indices: List[int]) -> str:
        """Helper to join specific pages (simple join)."""
        out = []
        for i in target_indices:
            if 0 <= i-1 < len(pages_text):
                out.append(pages_text[i-1])
        return "\n\n".join(out)

    def split_entity(self, entity_uuid: str, split_after_page_index: int) -> Tuple[str, str]:
        """
        Splits an existing entity into two separate ones.

        Args:
            entity_uuid: The UUID of the original entity.
            split_after_page_index: 0-based index of the last page to keep in the first part.

        Returns:
            A tuple containing the UUIDs of the two resulting entities.

        Raises:
            ValueError: If the entity is not found or split index is invalid.
        """
        # 1. Fetch Original
        doc = self.logical_repo.get_by_uuid(entity_uuid)
        if not doc:
            raise ValueError(f"Entity {entity_uuid} not found")

        # 2. Flatten Pages logic
        flat_pages: List[Dict[str, Any]] = []
        if doc.source_mapping:
            for src in doc.source_mapping:
                for p in src.pages:
                    flat_pages.append({"file_uuid": src.file_uuid, "page": p, "rotation": src.rotation})

        total_pages = len(flat_pages)
        if split_after_page_index < 0 or split_after_page_index >= total_pages - 1:
            raise ValueError(f"Invalid split index {split_after_page_index}. Total pages: {total_pages}")

        pages_a = flat_pages[: split_after_page_index + 1]
        pages_b = flat_pages[split_after_page_index + 1 :]

        def regroup(pages_list: List[Dict[str, Any]]) -> List[SourceReference]:
            mappings: List[SourceReference] = []
            if not pages_list:
                return mappings

            current_uuid = pages_list[0]["file_uuid"]
            current_rot = pages_list[0]["rotation"]
            current_batch = [pages_list[0]["page"]]

            for item in pages_list[1:]:
                if item["file_uuid"] == current_uuid and item["rotation"] == current_rot:
                    current_batch.append(item["page"])
                else:
                    mappings.append(SourceReference(file_uuid=current_uuid, pages=current_batch, rotation=current_rot))
                    current_uuid = item["file_uuid"]
                    current_rot = item["rotation"]
                    current_batch = [item["page"]]

            if current_batch:
                mappings.append(SourceReference(file_uuid=current_uuid, pages=current_batch, rotation=current_rot))
            return mappings

        doc.source_mapping = regroup(pages_a)
        doc.type_tags = ["UNKNOWN"]
        doc.semantic_data = {}
        doc.status = "NEW"
        self.logical_repo.save(doc)

        new_doc = VirtualDocument(
            uuid=str(uuid.uuid4()),  # Canonical Entity UUID is now uuid field
            created_at=doc.created_at,
            status="NEW",
            type_tags=["SPLIT_RESULT"],
        )
        new_doc.source_mapping = regroup(pages_b)
        self.logical_repo.save(new_doc)

        print(f"[Canonizer] Split {entity_uuid} at idx {split_after_page_index}. New parts: {doc.uuid}, {new_doc.uuid}")
        return (doc.uuid, new_doc.uuid)

    def restructure_file_entities(self, file_uuid: str, new_mappings: List[List[Dict[str, Any]]]) -> List[str]:
        """
        Completely redfines the logical entities for a physical file.
        Deletes existing entities and creates new ones.

        Args:
            file_uuid: The UUID of the physical file.
            new_mappings: List of page groups for the new entities.

        Returns:
            A list of new entity UUIDs.
        """
        existing_docs = self.logical_repo.get_by_source_file(file_uuid)

        if not existing_docs:
            print(f"[Canonizer] Warning: No existing entities found for file {file_uuid}. Treating as fresh split.")

        print(f"[Canonizer] RESTRUCTURE TRANSACTION: Deleting {len(existing_docs)} old entities for {file_uuid}...")

        for old_doc in existing_docs:
            self.logical_repo.delete_by_uuid(old_doc.uuid)

        new_uuids: List[str] = []
        created_at_ts = None
        if existing_docs:
            created_at_ts = existing_docs[0].created_at

        for group in new_mappings:
            current_rot = 0
            current_pages: List[int] = []
            refs: List[SourceReference] = []

            for item in group:
                p = item["page"]
                r = item.get("rotation", 0)

                if not current_pages:
                    current_rot = r
                    current_pages = [p]
                else:
                    if r == current_rot:
                        current_pages.append(p)
                    else:
                        refs.append(SourceReference(file_uuid, current_pages, current_rot))
                        current_rot = r
                        current_pages = [p]

            if current_pages:
                refs.append(SourceReference(file_uuid, current_pages, current_rot))

            new_id = str(uuid.uuid4())
            new_doc = VirtualDocument(
                uuid=new_id,
                source_mapping=refs,
                semantic_data={},
                status="READY_FOR_PIPELINE",
                created_at=created_at_ts,
                type_tags=["MANUAL_STRUCTURE"],
            )
            self.logical_repo.save(new_doc)
            new_uuids.append(new_id)

        print(f"[Canonizer] RESTRUCTURE COMMIT: Created {len(new_uuids)} new entities.")
        return new_uuids

    # ... Helper methods like _fuzzy_identity_match etc. (Unchanged)
    def _fuzzy_identity_match(self, party_name: Optional[str], party_address: Optional[str], profile: IdentityProfile) -> bool:
        """
        Performs a fuzzy match to determine if a party (sender/recipient) matches an identity profile.

        Args:
            party_name: Name of the party.
            party_address: Address of the party.
            profile: The identity profile to match against.

        Returns:
            True if a match is found.
        """
        if not party_name and not party_address:
            return False

        text_lower = f"{party_name or ''} {party_address or ''}".lower()

        # Check for postcode match (high signal)
        for kw in profile.address_keywords:
            if kw.isdigit() and len(kw) == 5:
                if kw in text_lower:
                    return True

        score = 0.0
        threshold = 0.8

        search_terms: List[str] = []
        if profile.name:
            search_terms.append(profile.name)
        if profile.company_name:
            search_terms.append(profile.company_name)
        search_terms += profile.aliases
        search_terms += profile.company_aliases
        search_terms += [k for k in profile.address_keywords if not k.isdigit()]

        for term in set(search_terms):
            if not term or len(term) < 3:
                continue
            clean_term = term.lower()
            if clean_term in text_lower:
                score += 1.0
            elif len(clean_term) >= 5:
                prefix = clean_term[:5]
                if prefix in text_lower:
                    score += 0.5
                parts = clean_term.split()
                for part in parts:
                    if len(part) > 3 and part in text_lower:
                        score += 0.3

        return score >= threshold

    def _classify_direction(self, entity: CanonicalEntity) -> None:
        """
        Determines the document direction (INCOMING/OUTGOING) based on identity profiles.

        Args:
            entity: The CanonicalEntity to classify.
        """
        priv_json = self.config.get_private_profile_json()
        bus_json = self.config.get_business_profile_json()

        identities: List[IdentityProfile] = []
        try:
            if priv_json:
                identities.append(IdentityProfile.model_validate_json(priv_json))
            if bus_json:
                identities.append(IdentityProfile.model_validate_json(bus_json))
        except Exception as e:
            print(f"[Canonizer] Profile Load Error: {e}")

        # Check Sender
        sender_name = entity.parties.sender.name
        sender_addr = entity.parties.sender.address
        for prof in identities:
            if self._fuzzy_identity_match(sender_name, sender_addr, prof):
                entity.direction = "OUTGOING"
                return

        # Check Recipient
        recipient_name = entity.parties.recipient.name
        recipient_addr = entity.parties.recipient.address
        for prof in identities:
            if self._fuzzy_identity_match(recipient_name, recipient_addr, prof):
                entity.direction = "INCOMING"
                return

