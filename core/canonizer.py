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
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

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
    map_pages_to_source,
    page_texts_from_result,
    user_message,
)
from core.engines.fluxsense_client import FluxSenseClient, FluxSenseError, create_fluxsense_client
from core.models.identity import IdentityProfile
from core.models.semantic import EngineInfo, SemanticExtraction, WorkflowInfo
from core.models.virtual import SourceReference, VirtualDocument, DocumentStatus
from core.reanalysis import carry_over_user_state
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
# Coding errors stop the background worker instead of being logged per document. ValueError
# (incl. pydantic validation) and TypeError mostly come from data and only hold that document.
CRITICAL_ERRORS: Tuple[type, ...] = (NameError, AttributeError, SyntaxError, ImportError)


@dataclass
class AnalysisJob:
    """A locked document prepared for the engine; carries everything the engine call needs (no DB access)."""

    v_doc: VirtualDocument
    page_refs: List[PageRef]
    physical: Dict[str, Tuple[str, int]]
    resumption: bool
    keep_single: bool


@dataclass
class AnalysisOutcome:
    """Result of the engine call of one job."""

    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None


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
        self.workflow_registry.load_from_directory(str(self.config.get_workflows_dir()))

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
                llm_url=self.config.get_fluxsense_llm_url(),
                hooks=self.config.get_fluxsense_hooks(),
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

    def _lock_pending(self, limit: int) -> List[str]:
        """Atomically locks up to `limit` waiting documents (PROCESSING_S1 / PROCESSING_S2)."""
        # Fetch entities - but only those NOT currently being processed by another worker
        query = """
            SELECT uuid, status
            FROM virtual_documents
            WHERE status IN ('NEW', 'READY_FOR_PIPELINE', 'STAGE2_PENDING') 
              AND deleted = 0
            LIMIT ?
        """
        uuids: List[str] = []
        with self.db.transaction() as conn:
            for uuid_val, current in conn.execute(query, (limit,)).fetchall():
                target = DocumentStatus.PROCESSING_S1 if current in [DocumentStatus.NEW, DocumentStatus.READY_FOR_PIPELINE] else DocumentStatus.PROCESSING_S2
                cursor = conn.execute(
                    "UPDATE virtual_documents SET status = ? WHERE uuid = ? AND status = ?",
                    (target, uuid_val, current),
                )
                if cursor.rowcount > 0:
                    uuids.append(uuid_val)
        if uuids:
            logger.info(f"Locked {len(uuids)} documents for processing.")
        return uuids

    def process_pending_documents(self, limit: int = 10, max_parallel: int = 1) -> int:
        """
        Locks waiting documents and analyzes them.

        With max_parallel > 1 the engine calls of up to max_parallel documents
        run concurrently in worker threads (FluxSense serializes its PyMuPDF
        access with a process-wide lock, KPaperFlux's stitching uses the same
        lock). Locking, preparation and applying the results (all database
        access) stay in the calling thread, one document after the other.

        Args:
            limit: Maximum number of documents to process in this call.
            max_parallel: Maximum number of concurrent engine calls.

        Returns:
            The number of successfully processed documents.

        Raises:
            NameError, AttributeError, SyntaxError, TypeError, ValueError: Coding
                errors are re-raised (after the document was put on hold) to stop the worker.
        """
        jobs: List[AnalysisJob] = []
        processed_count = 0
        for uuid_obj in self._lock_pending(limit):
            v_doc = self.logical_repo.get_by_uuid(uuid_obj)
            if not v_doc:
                continue
            started = self._guarded(v_doc, None, lambda doc=v_doc: self.begin_analysis(doc))
            if isinstance(started, AnalysisJob):
                jobs.append(started)
            elif started:
                processed_count += 1

        if max_parallel <= 1 or len(jobs) <= 1:
            for job in jobs:
                if self._guarded(job.v_doc, job, lambda j=job: self.finish_analysis(j, self.run_analysis(j))):
                    processed_count += 1
            return processed_count

        with ThreadPoolExecutor(max_workers=min(max_parallel, len(jobs)), thread_name_prefix="analysis") as pool:
            futures: List[Tuple[AnalysisJob, Future]] = [(job, pool.submit(self.run_analysis, job)) for job in jobs]
            for job, future in futures:
                if self._guarded(job.v_doc, job, lambda j=job, f=future: self.finish_analysis(j, f.result())):
                    processed_count += 1
        return processed_count

    def _guarded(self, v_doc: VirtualDocument, job: Optional[AnalysisJob], step: Callable[[], Any]) -> Any:
        """
        Runs one processing step of a locked document. Unexpected errors put the
        document on hold (instead of leaving it locked); coding errors are re-raised.
        """
        try:
            return step()
        except CRITICAL_ERRORS as e:
            logger.error(f"CRITICAL ERROR processing {v_doc.uuid}: {e}", exc_info=True)
            self._hold(v_doc, job.resumption if job else False, f"Internal error: {e}", None)
            raise
        except Exception as e:  # any other failure must not leave the document locked
            logger.error(f"ERROR processing {v_doc.uuid}: {e}", exc_info=True)
            self._hold(v_doc, job.resumption if job else False, f"Internal error: {e}", None)
            return False

    def release_interrupted_documents(self) -> int:
        """
        Re-queues documents whose analysis was interrupted (application quit or
        crash while a FluxSense call was running). Their lock state would
        otherwise keep them out of the queue forever. Call once when the
        single background worker starts, before it processes anything.

        Returns:
            Number of re-queued documents.
        """
        released = 0
        with self.db.transaction() as conn:
            for locked, queued in ((DocumentStatus.PROCESSING_S1, DocumentStatus.READY_FOR_PIPELINE),
                                   (DocumentStatus.PROCESSING_S2, DocumentStatus.STAGE2_PENDING)):
                cursor = conn.execute("UPDATE virtual_documents SET status = ? WHERE status = ? AND deleted = 0",
                                      (queued, locked))
                released += cursor.rowcount
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
        placeholders = ",".join(["?"] * len(allowed_old))
        sql = f"UPDATE virtual_documents SET status = ? WHERE uuid = ? AND status IN ({placeholders})"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql, [target_status, v_doc.uuid] + allowed_old)

        if cursor.rowcount > 0:
            v_doc.status = target_status
            return True
        return False

    def _is_trailing_blank(self, v_doc: VirtualDocument) -> bool:
        """
        True if the document consists of the last pages of a single file that has
        other pages before them (the blank back side of an ADF scan).
        """
        if len(v_doc.source_mapping) != 1 or not v_doc.source_mapping[0].pages:
            return False
        ref = v_doc.source_mapping[0]
        pf = self.physical_repo.get_by_uuid(ref.file_uuid)
        return bool(pf and pf.page_count_phys and max(ref.pages) == pf.page_count_phys and min(ref.pages) > 1)

    def _discard_empty(self, v_doc: VirtualDocument) -> None:
        """
        Handles a document without any text: blank trailing pages of a longer file
        are ADF artifacts and are purged; anything else (e.g. a photo or an
        image-only scan) is kept and marked SKIPPED_EMPTY.
        """
        if self._is_trailing_blank(v_doc):
            logger.info(f"No text content resolved for {v_doc.uuid} (end of file). Purging ADF artifact.")
            self.logical_repo.delete_by_uuid(v_doc.uuid)
        else:
            logger.info(f"No text content resolved for {v_doc.uuid}. Marking as SKIPPED_EMPTY.")
            v_doc.status = DocumentStatus.SKIPPED_EMPTY
            self.logical_repo.save(v_doc)

    def _reload_locked(self, v_doc: VirtualDocument) -> Optional[VirtualDocument]:
        """
        Re-reads a document right before an analysis result is written.

        The analysis may run for minutes; meanwhile the user can delete, purge or
        edit the document. Writing the snapshot taken at lock time would undo that.

        Returns:
            The current document if it is still locked for this analysis, else None.
        """
        current = self.logical_repo.get_by_uuid(v_doc.uuid)
        if current is None or current.deleted or current.status != v_doc.status:
            logger.info(f"{v_doc.uuid} changed during analysis "
                        f"({'gone' if current is None else current.status}); result discarded.")
            return None
        return current

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

    def _hold(self, v_doc: VirtualDocument, resumption: bool, message: str, result: Optional[Dict[str, Any]],
              error_code: Optional[str] = None) -> None:
        """
        Puts a document on hold after a failed engine run. Existing semantic
        data is kept; the engine block records FluxSense's error code, a
        generic user-facing message (first error) and the technical details.
        'Reprocess' retries.
        """
        logger.error(f"FluxSense analysis failed for {v_doc.uuid} ({error_code or 'unclassified'}): {message}")
        v_doc = self._reload_locked(v_doc)
        if v_doc is None:
            return
        if v_doc.semantic_data is None:
            v_doc.semantic_data = SemanticExtraction()
        url = self._server_url() if error_code else None
        info = engine_error_info(user_message(error_code, url, message), result, error_code=error_code, server_url=url)
        if message not in info.errors:
            info.errors.insert(1, message)
        v_doc.semantic_data.engine = info
        v_doc.status = DocumentStatus.STAGE2_HOLD if resumption else DocumentStatus.STAGE1_HOLD
        v_doc.last_processed_at = datetime.now().isoformat()
        self.logical_repo.save(v_doc)

    def _server_url(self) -> Optional[str]:
        """Server address of the current engine connection (None if unknown)."""
        try:
            return self.get_engine_client().server_url()
        except (FluxSenseError, ValueError) as e:
            logger.info(f"Server URL unknown: {e}")
            return None

    def _fill_page_texts(self, page_refs: List[PageRef], page_texts: Optional[List[str]]) -> int:
        """
        Stores the engine's page texts as the text of physical pages that have
        none yet (scans: Stage 0 extracts only the native text layer). Existing
        texts (native text layer, explicit OCR) are kept.

        Returns:
            Number of pages filled.
        """
        if not page_texts:
            return 0
        changed: Dict[str, Any] = {}
        filled = 0
        for ref, text in zip(page_refs, page_texts):
            if not text or not text.strip():
                continue
            pf = changed.get(ref.file_uuid) or self.physical_repo.get_by_uuid(ref.file_uuid)
            if not pf:
                continue
            texts = pf.raw_ocr_data if isinstance(pf.raw_ocr_data, dict) else {}
            if str(texts.get(str(ref.page), "")).strip():
                continue
            texts[str(ref.page)] = text.strip()
            pf.raw_ocr_data = texts
            changed[ref.file_uuid] = pf
            filled += 1
        for pf in changed.values():
            self.physical_repo.save(pf)
        if filled:
            logger.info(f"Stored engine text for {filled} page(s) without a text layer.")
        return filled

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
        same_pages = [r.model_dump() for r in target_doc.source_mapping] == [r.model_dump() for r in entity.source_mapping]
        # Workflow progress and confirmed values belong to these pages only
        previous = target_doc.semantic_data if same_pages else None
        target_doc.source_mapping = entity.source_mapping
        target_doc.type_tags = entity.type_tags
        target_doc.semantic_data = carry_over_user_state(previous, entity.semantic)
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

    def begin_analysis(self, v_doc: VirtualDocument) -> Union[AnalysisJob, bool]:
        """
        Locks a document and collects what the engine call needs (database access).

        Args:
            v_doc: The VirtualDocument.

        Returns:
            The job, or the final result if there is nothing to analyze
            (True: handled, e.g. no pages; False: owned by another worker).
        """
        logger.info(f"Processing {v_doc.uuid}...")
        resumption = self._acquire(v_doc)
        if resumption is None:
            return False
        page_refs = flatten_source_mapping(v_doc.source_mapping)
        if not page_refs:
            logger.info(f"{v_doc.uuid} has no pages. Marking as SKIPPED_EMPTY.")
            v_doc.status = DocumentStatus.SKIPPED_EMPTY
            self.logical_repo.save(v_doc)
            return True
        physical = {}
        for ref in page_refs:
            if ref.file_uuid not in physical:
                resolved = self._resolve_physical(ref.file_uuid)
                if resolved:
                    physical[ref.file_uuid] = resolved
        is_manual = "MANUAL_EDIT" in (v_doc.type_tags or [])
        return AnalysisJob(v_doc=v_doc, page_refs=page_refs, physical=physical, resumption=resumption,
                           keep_single=resumption or is_manual or v_doc.is_immutable)

    def run_analysis(self, job: AnalysisJob) -> AnalysisOutcome:
        """
        Runs the engine on the job's pages. No database access: safe in worker threads.

        Args:
            job: Prepared job.

        Returns:
            The engine output, or the error that should put the document on hold.
        """
        try:
            with analysis_pdf(job.page_refs, job.physical.get) as pdf_path:
                return AnalysisOutcome(result=self.get_engine_client().analyze(pdf_path))
        except FluxSenseError as e:
            return AnalysisOutcome(error=str(e), error_code=e.error_code)
        except AnalysisInputError as e:
            return AnalysisOutcome(error=str(e))

    def finish_analysis(self, job: AnalysisJob, outcome: AnalysisOutcome) -> bool:
        """
        Applies an engine outcome (database access): stores page texts, discards
        empty documents, applies the segmentation and extraction, or holds the document.

        Args:
            job: The job.
            outcome: Its engine outcome.

        Returns:
            True if processing completed (status changed), False if the document was put on hold.
        """
        result = outcome.result
        if result is None:
            self._hold(job.v_doc, job.resumption, outcome.error or "FluxSense returned no result", None, outcome.error_code)
            return False
        try:
            entities = adapt_result(result, job.page_refs, keep_single=job.keep_single)
        except FluxSenseResultError as e:
            self._hold(job.v_doc, job.resumption, str(e), result, e.error_code)
            return False
        v_doc = self._reload_locked(job.v_doc)
        if v_doc is None:
            return False
        self._fill_page_texts(job.page_refs, page_texts_from_result(result))

        # Empty-text gate (after the engine, which also reads scans): ADF artifacts and blank pages.
        full_text = v_doc.resolve_content(self._load_physical)
        if not full_text.strip():
            self._discard_empty(v_doc)
            return True

        if not entities:
            logger.info(f"FluxSense found no logical document in {v_doc.uuid}.")
            v_doc.status = DocumentStatus.PROCESSED
            v_doc.last_processed_at = datetime.now().isoformat()
            self.logical_repo.save(v_doc)
            return True

        covered = {page for entity in entities for page in entity.pages}
        # Pages without any text the engine left out are blank (scan back sides) and stay unassigned
        uncovered = [page for page in range(1, len(job.page_refs) + 1)
                     if page not in covered and self._page_has_text(job.page_refs[page - 1])]
        # One transaction: a split is applied completely or not at all
        with self.db.transaction():
            for idx, entity in enumerate(entities):
                target_doc = v_doc if idx == 0 else VirtualDocument(
                    uuid=str(uuid.uuid4()), status=DocumentStatus.NEW, created_at=v_doc.created_at)
                self._apply_entity(target_doc, entity)
            if uncovered:
                self._hold_remainder(v_doc, uncovered, job.page_refs)
        return True

    def _page_has_text(self, ref: PageRef) -> bool:
        """True if the physical page has text (native layer or engine OCR)."""
        pf = self._load_physical(ref.file_uuid)
        texts = pf.raw_ocr_data if pf and isinstance(pf.raw_ocr_data, dict) else {}
        return bool(str(texts.get(str(ref.page), "")).strip())

    def _hold_remainder(self, v_doc: VirtualDocument, pages: List[int], page_refs: List[PageRef]) -> None:
        """
        Keeps pages the engine assigned to no document in a held document of their
        own, so they stay visible; 'Reprocess' analyzes them again.
        """
        message = f"The analysis assigned pages {pages} to no document; they are kept here for review."
        logger.warning(f"{v_doc.uuid}: {message}")
        remainder = VirtualDocument(
            uuid=str(uuid.uuid4()), status=DocumentStatus.STAGE1_HOLD, created_at=v_doc.created_at,
            source_mapping=map_pages_to_source(pages, page_refs),
            semantic_data=SemanticExtraction(engine=EngineInfo(name="fluxsense", status="PARTIAL", errors=[message])),
            last_processed_at=datetime.now().isoformat(),
        )
        self.logical_repo.save(remainder)

    def process_virtual_document(self, v_doc: VirtualDocument) -> bool:
        """
        Analyzes a VirtualDocument with FluxSense (segmentation, classification,
        visual audit, extraction, OCR text) and applies the result.

        A fresh document may be split into several logical documents. Protected,
        manually edited and re-extracted (STAGE2_PENDING) documents keep their
        page range. Engine failures put the document on hold (STAGE1_HOLD, or
        STAGE2_HOLD for a re-extraction); 'Reprocess' retries it.

        Args:
            v_doc: The VirtualDocument to process.

        Returns:
            True if processing completed (status changed), False otherwise.
        """
        job = self.begin_analysis(v_doc)
        if not isinstance(job, AnalysisJob):
            return job
        return self.finish_analysis(job, self.run_analysis(job))

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
