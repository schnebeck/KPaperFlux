"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/canonizer.py
Version:        3.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Canonization service: runs the FluxSense analysis engine on
                logical documents after Stage 0, applies the detected
                segmentation (1 logical -> N logical), stores the semantic
                extraction with its per-field review state and assigns
                workflows and auto-tags. Also handles manual split and
                restructure operations.
------------------------------------------------------------------------------
"""

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from core.config import AppConfig
from core.database import DatabaseManager
from core.engines.analysis_input import AnalysisInputError, analysis_pdf
from core.engines.fluxsense_adapter import (
    AdaptedEntity,
    FluxSenseResultError,
    PageRef,
    adapt_result,
    engine_error_info,
    flatten_source_mapping,
)
from core.engines.fluxsense_client import FluxSenseClient, FluxSenseError, create_fluxsense_client
from core.models.identity import IdentityProfile
from core.models.semantic import SemanticExtraction, WorkflowInfo
from core.models.virtual import SourceReference, VirtualDocument, DocumentStatus
from core.repositories.logical_repo import LogicalRepository
from core.repositories.physical_repo import PhysicalRepository
from core.rules_engine import RulesEngine
from core.workflow import WorkflowRuleRegistry, get_initial_state

if TYPE_CHECKING:
    from core.filter_tree import FilterTree

from core.logger import get_logger
logger = get_logger("canonizer")

# Re-extraction of an already classified document: keep its page range (no re-segmentation).
RESUMPTION_STATES: Tuple[str, ...] = (DocumentStatus.STAGE2_PENDING, DocumentStatus.PROCESSING_S2)
FRESH_STATES: Tuple[str, ...] = (DocumentStatus.NEW, DocumentStatus.READY_FOR_PIPELINE)


def generate_smart_filename(semantic_data: Optional[SemanticExtraction], entity_types: List[str]) -> str:
    """
    Builds the export filename '<date>__<sender>__<TYPE>.pdf'.

    Args:
        semantic_data: The semantic extraction (may be None).
        entity_types: type_tags; the first one names the type.

    Returns:
        The filename.
    """
    if semantic_data is None:
        return "0000-00-00__Unknown__DOC.pdf"
    meta = semantic_data.meta_header
    doc_date = (meta.doc_date if meta else None) or "0000-00-00"
    sender = meta.sender if meta else None
    entity_name = (sender.company or sender.name if sender else None) or "Unknown"
    entity_name = re.sub(r"[^\w\s]", "", str(entity_name)).replace(" ", "_")[:30]
    doc_type = entity_types[0].upper() if entity_types else "DOC"
    return f"{doc_date}__{entity_name}__{doc_type}.pdf"


class CanonizerService:
    """
    Scans logical entities waiting for analysis (NEW, READY_FOR_PIPELINE,
    STAGE2_PENDING), analyzes them with FluxSense and applies the result.
    """

    def __init__(
        self,
        db: DatabaseManager,
        engine_client: Optional[FluxSenseClient] = None,
        physical_repo: Optional[PhysicalRepository] = None,
        logical_repo: Optional[LogicalRepository] = None,
        filter_tree: Optional["FilterTree"] = None,
    ) -> None:
        """
        Initializes the CanonizerService.

        Args:
            db: The DatabaseManager instance.
            engine_client: Optional FluxSense client (default: created from the settings on first use).
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

        self._engine_client: Optional[FluxSenseClient] = engine_client
        self.rules_engine = RulesEngine(db, filter_tree) if filter_tree else None

        self.workflow_registry = WorkflowRuleRegistry()
        # Note: In production, the path might be different, but for now we use relative
        self.workflow_registry.load_from_directory("resources/workflows")

    # ------------------------------------------------------------------ engine

    def _load_identity(self, raw_json: Optional[str]) -> Optional[IdentityProfile]:
        """Parses a stored identity profile (None if not configured)."""
        return IdentityProfile.model_validate_json(raw_json) if raw_json else None

    def get_engine_client(self) -> FluxSenseClient:
        """Returns the FluxSense client, creating it from the current settings if needed."""
        if self._engine_client is None:
            self._engine_client = create_fluxsense_client(
                self.config.get_fluxsense_mode(),
                self.config.get_fluxsense_url(),
                self.config.get_fluxsense_timeout(),
                private_id=self._load_identity(self.config.get_private_profile_json()),
                business_id=self._load_identity(self.config.get_business_profile_json()),
            )
        return self._engine_client

    def reset_engine_client(self) -> None:
        """Drops the cached client so changed settings take effect on the next document."""
        self._engine_client = None

    def _resolve_physical(self, file_uuid: str) -> Optional[Tuple[str, int]]:
        """Resolves a physical file UUID to (vault path, page count)."""
        pf = self.physical_repo.get_by_uuid(file_uuid)
        if not pf or not pf.file_path:
            return None
        return pf.file_path, int(pf.page_count_phys or 0)

    # ------------------------------------------------------------------ pipeline

    def _load_physical(self, fid: str) -> Optional[Any]:
        """Resolves a physical file UUID to its PhysicalFile record."""
        return self.physical_repo.get_by_uuid(fid)

    def reconstruct_document_text(self, v_doc: VirtualDocument) -> str:
        """
        Public helper to refresh the cached_full_text of a logical document
        based on its current source mapping.
        """
        return v_doc.resolve_content(self._load_physical)

    def process_pending_documents(self, limit: int = 10) -> int:
        """
        Scans for Logical Entities waiting for analysis and processes them.

        Args:
            limit: Maximum number of documents to process in one batch.

        Returns:
            The number of successfully processed documents.
        """
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
            target = DocumentStatus.PROCESSING_S1 if current in [DocumentStatus.NEW, DocumentStatus.READY_FOR_PIPELINE] else DocumentStatus.PROCESSING_S2

            # Atomic update to lock this document
            cursor.execute(
                "UPDATE virtual_documents SET status = ? WHERE uuid = ? AND status = ?",
                (target, uuid_val, current),
            )
            if cursor.rowcount > 0:
                uuids.append(uuid_val)

        self.db.connection.commit()
        if uuids:
            logger.info(f"Locked {len(uuids)} documents for processing.")

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
                    logger.error(f"CRITICAL ERROR processing {uuid_obj}: {e}", exc_info=True)
                    raise e  # Propagate critical coding/logic errors to stop the worker
                except Exception as e:
                    logger.error(f"ERROR processing {uuid_obj}: {e}", exc_info=True)

        return processed_count

    def release_interrupted_documents(self) -> int:
        """
        Re-queues documents whose analysis was interrupted (application quit or
        crash while a FluxSense call was running). Their lock state would
        otherwise keep them out of the queue forever. Call once when the
        single background worker starts, before it processes anything.

        Returns:
            Number of re-queued documents.
        """
        cursor = self.db.connection.cursor()
        released = 0
        for locked, queued in ((DocumentStatus.PROCESSING_S1, DocumentStatus.READY_FOR_PIPELINE),
                               (DocumentStatus.PROCESSING_S2, DocumentStatus.STAGE2_PENDING)):
            cursor.execute("UPDATE virtual_documents SET status = ? WHERE status = ? AND deleted = 0", (queued, locked))
            released += cursor.rowcount
        self.db.connection.commit()
        if released:
            logger.warning(f"Re-queued {released} document(s) whose analysis was interrupted.")
        return released

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

    def _discard_empty(self, v_doc: VirtualDocument) -> None:
        """
        Handles a document without any text: trailing pages of a file are ADF
        artifacts and are purged, others are marked SKIPPED_EMPTY.
        """
        is_at_end = False
        if v_doc.source_mapping:
            last_ref = v_doc.source_mapping[-1]
            pf = self.physical_repo.get_by_uuid(last_ref.file_uuid)
            if pf and pf.page_count_phys and max(last_ref.pages) == pf.page_count_phys:
                is_at_end = True

        if is_at_end:
            logger.info(f"No text content resolved for {v_doc.uuid} (End-of-File). Purging ADF artifact.")
            self.logical_repo.delete_by_uuid(v_doc.uuid)
        else:
            logger.info(f"No text content resolved for {v_doc.uuid} (Mid-File). Marking as SKIPPED_EMPTY.")
            v_doc.status = DocumentStatus.SKIPPED_EMPTY
            self.logical_repo.save(v_doc)

    def _acquire(self, v_doc: VirtualDocument) -> Optional[bool]:
        """
        Locks the document for analysis.

        Returns:
            True for a re-extraction (keep page range), False for a fresh
            analysis, None if another worker owns the document.
        """
        status = v_doc.status
        if status in RESUMPTION_STATES:
            if status == DocumentStatus.STAGE2_PENDING and not self._atomic_transition(
                    v_doc, [DocumentStatus.STAGE2_PENDING], DocumentStatus.PROCESSING_S2):
                logger.info("Failed atomic lock for re-extraction. Skipping.")
                return None
            return True
        if status in FRESH_STATES:
            if not self._atomic_transition(v_doc, list(FRESH_STATES), DocumentStatus.PROCESSING_S1):
                logger.info("Failed atomic lock for analysis. Skipping.")
                return None
        elif status != DocumentStatus.PROCESSING_S1 and status.startswith("PROCESSING_"):
            logger.info(f"Document {v_doc.uuid[:8]} is already {status}. Skipping to avoid overlap.")
            return None
        return False

    def _hold(self, v_doc: VirtualDocument, resumption: bool, message: str, result: Optional[Dict[str, Any]]) -> None:
        """
        Puts a document on hold after a failed engine run. Existing semantic
        data is kept; the engine block records the error. 'Reprocess' retries.
        """
        logger.error(f"FluxSense analysis failed for {v_doc.uuid}: {message}")
        if v_doc.semantic_data is None:
            v_doc.semantic_data = SemanticExtraction()
        v_doc.semantic_data.engine = engine_error_info(message, result)
        v_doc.status = DocumentStatus.STAGE2_HOLD if resumption else DocumentStatus.STAGE1_HOLD
        v_doc.last_processed_at = datetime.now().isoformat()
        self.logical_repo.save(v_doc)

    def _analyze_pages(self, page_refs: List[PageRef]) -> Dict[str, Any]:
        """Runs FluxSense on the PDF formed by the document's pages."""
        with analysis_pdf(page_refs, self._resolve_physical) as pdf_path:
            return self.get_engine_client().analyze(pdf_path)

    def _assign_workflows(self, target_doc: VirtualDocument) -> None:
        """Assigns all workflow rules triggered by the document's type tags."""
        if not target_doc.semantic_data:
            return
        for rule in self.workflow_registry.find_rules_for_tags(target_doc.type_tags):
            if rule.id not in target_doc.semantic_data.workflows:
                target_doc.semantic_data.workflows[rule.id] = WorkflowInfo(
                    rule_id=rule.id,
                    current_step=get_initial_state(rule) or "NEW",
                )
                logger.info(f"Assigned rule '{rule.id}' to {target_doc.uuid}")

    def _apply_entity(self, target_doc: VirtualDocument, entity: AdaptedEntity) -> None:
        """Writes one adapted logical document into its VirtualDocument and persists it."""
        target_doc.source_mapping = entity.source_mapping
        target_doc.type_tags = entity.type_tags
        target_doc.semantic_data = entity.semantic
        target_doc.ai_confidence = entity.ai_confidence
        target_doc.cached_full_text = target_doc.resolve_content(self._load_physical)
        target_doc.export_filename = generate_smart_filename(target_doc.semantic_data, target_doc.type_tags)
        target_doc.last_processed_at = datetime.now().isoformat()
        if entity.failed:
            logger.error(f"FluxSense could not extract {target_doc.uuid} (pages {entity.pages}): {entity.errors}")
            target_doc.status = DocumentStatus.STAGE2_HOLD
            self.logical_repo.save(target_doc)
            return
        self._assign_workflows(target_doc)
        target_doc.status = DocumentStatus.PROCESSED
        self.logical_repo.save(target_doc)
        logger.info(f"Saved Entity {target_doc.uuid} ({', '.join(target_doc.type_tags)})")

        # Auto-Tagging
        if self.rules_engine and self.rules_engine.apply_rules_to_entity(target_doc, only_auto=True):
            self.logical_repo.save(target_doc)

    def process_virtual_document(self, v_doc: VirtualDocument) -> bool:
        """
        Analyzes a VirtualDocument with FluxSense (segmentation, classification,
        visual audit, extraction) and applies the result.

        A fresh document may be split into several logical documents. Protected,
        manually edited and re-extracted (STAGE2_PENDING) documents keep their
        page range. Engine failures put the document on hold (STAGE1_HOLD, or
        STAGE2_HOLD for a re-extraction); 'Reprocess' retries it.

        Args:
            v_doc: The VirtualDocument to process.

        Returns:
            True if processing completed (status changed), False otherwise.
        """
        logger.info(f"Processing {v_doc.uuid}...")
        is_manual = "MANUAL_EDIT" in (v_doc.type_tags or [])

        # Stage 0 text gate: documents without any text are ADF artifacts or empty pages.
        full_text = v_doc.resolve_content(self._load_physical)
        if not full_text:
            self._discard_empty(v_doc)
            return True
        v_doc.cached_full_text = full_text

        resumption = self._acquire(v_doc)
        if resumption is None:
            return False
        page_refs = flatten_source_mapping(v_doc.source_mapping)
        if not page_refs:
            return False

        keep_single = resumption or is_manual or v_doc.is_immutable
        result: Optional[Dict[str, Any]] = None
        try:
            result = self._analyze_pages(page_refs)
            entities = adapt_result(result, page_refs, keep_single=keep_single)
        except (FluxSenseError, FluxSenseResultError, AnalysisInputError) as e:
            self._hold(v_doc, resumption, str(e), result)
            return False

        if not entities:
            logger.info(f"FluxSense found no logical document in {v_doc.uuid}.")
            v_doc.status = DocumentStatus.PROCESSED
            v_doc.last_processed_at = datetime.now().isoformat()
            self.logical_repo.save(v_doc)
            return True

        for idx, entity in enumerate(entities):
            target_doc = v_doc if idx == 0 else VirtualDocument(
                uuid=str(uuid.uuid4()), status=DocumentStatus.NEW, created_at=v_doc.created_at)
            self._apply_entity(target_doc, entity)
        return True

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
        doc.status = DocumentStatus.NEW
        self.logical_repo.save(doc)

        new_doc = VirtualDocument(
            uuid=str(uuid.uuid4()),  # Canonical Entity UUID is now uuid field
            created_at=doc.created_at,
            status=DocumentStatus.NEW,
            type_tags=["SPLIT_RESULT"],
        )
        new_doc.source_mapping = regroup(pages_b)
        self.logical_repo.save(new_doc)

        logger.info(f"Split {entity_uuid} at idx {split_after_page_index}. New parts: {doc.uuid}, {new_doc.uuid}")
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
            logger.warning(f"No existing entities found for file {file_uuid}. Treating as fresh split.")

        logger.info(f"RESTRUCTURE TRANSACTION: Deleting {len(existing_docs)} old entities for {file_uuid}...")

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
                status=DocumentStatus.READY_FOR_PIPELINE,
                created_at=created_at_ts,
                type_tags=["MANUAL_STRUCTURE"],
            )
            self.logical_repo.save(new_doc)
            new_uuids.append(new_id)

        logger.info(f"RESTRUCTURE COMMIT: Created {len(new_uuids)} new entities.")
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



