"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/engines/fluxsense_adapter.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Pure mapping of a FluxSense AnalysisResult (JSON dict) onto
                KPaperFlux objects: page ranges -> SourceReferences, type /
                direction / tenant -> type_tags, fields -> SemanticExtraction,
                trust -> ai_confidence, evidence / plausibility / review ->
                semantic_data.engine (per-field review state).
------------------------------------------------------------------------------
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError

from core.models.semantic import (
    EngineInfo,
    FieldReviewState,
    FinanceBody,
    LegalBody,
    MetaHeader,
    SemanticExtraction,
    StatementBody,
    SubscriptionInfo,
    VisualAuditResult,
)
from core.models.virtual import SourceReference

ENGINE_NAME: str = "fluxsense"
RESULT_STATUS_ERROR: str = "ERROR"
ERROR_AI_SERVER_UNREACHABLE: str = "AI_SERVER_UNREACHABLE"
# FluxSense marks transport failures of an AI call with this prefix (CallRecord.error).
_UNREACHABLE_PREFIX: str = "Backend unreachable"
UNKNOWN: str = "UNKNOWN"

# Bodies that KPaperFlux hydrates into typed models (see SemanticExtraction.parse_bodies).
TYPED_BODIES: Dict[str, Type[BaseModel]] = {
    "finance_body": FinanceBody,
    "legal_body": LegalBody,
    "subscription_info": SubscriptionInfo,
    "statement_body": StatementBody,
}

# FluxSense evidence keys copied into FieldReviewState (others stay engine-internal).
_EVIDENCE_KEYS: Tuple[str, ...] = (
    "path", "value", "kind", "bbox", "evidence", "critical", "status", "action",
    "original_value", "provenance", "auto_accepted", "review_reasons",
)


@dataclass(frozen=True)
class PageRef:
    """One page of the analyzed PDF, resolved to its physical origin."""

    file_uuid: str
    page: int
    rotation: int = 0


@dataclass
class AdaptedEntity:
    """One logical document of a FluxSense result, mapped to KPaperFlux objects."""

    pages: List[int]
    source_mapping: List[SourceReference]
    type_tags: List[str]
    semantic: SemanticExtraction
    ai_confidence: float
    failed: bool = False
    errors: List[str] = field(default_factory=list)


class FluxSenseResultError(ValueError):
    """Raised when a FluxSense result is unusable as a whole (engine status ERROR or malformed)."""


# --------------------------------------------------------------------- pages

def flatten_source_mapping(source_mapping: List[SourceReference]) -> List[PageRef]:
    """
    Expands a source mapping into the page sequence of the PDF that is analyzed.

    Args:
        source_mapping: The VirtualDocument's source mapping.

    Returns:
        One PageRef per analyzed page; index i holds page i + 1 of the analyzed PDF.
    """
    return [PageRef(ref.file_uuid, page, ref.rotation) for ref in source_mapping for page in ref.pages]


def is_whole_file(page_refs: List[PageRef], page_count: int) -> bool:
    """
    Checks whether the page sequence is exactly one physical file, unrotated and complete.

    Args:
        page_refs: Flattened page sequence.
        page_count: Number of pages of the (single) physical file.

    Returns:
        True if the vault file itself can be analyzed without stitching a copy.
    """
    if not page_refs or len({ref.file_uuid for ref in page_refs}) != 1:
        return False
    if any(ref.rotation for ref in page_refs):
        return False
    return [ref.page for ref in page_refs] == list(range(1, page_count + 1))


def map_pages_to_source(pages: List[int], page_refs: List[PageRef]) -> List[SourceReference]:
    """
    Converts 1-based pages of the analyzed PDF into a KPaperFlux source mapping.

    Consecutive pages from the same file with the same rotation are merged
    into one SourceReference (same grouping as instruction-based Stage 0).
    Pages outside the analyzed PDF are ignored.

    Args:
        pages: 1-based pages of the analyzed PDF (FluxSense ``pages``).
        page_refs: Flattened page sequence of the analyzed PDF.

    Returns:
        The source mapping of the logical document.
    """
    mapping: List[SourceReference] = []
    for page in pages:
        if not 1 <= page <= len(page_refs):
            continue
        ref = page_refs[page - 1]
        last = mapping[-1] if mapping else None
        if last and last.file_uuid == ref.file_uuid and last.rotation == ref.rotation:
            last.pages.append(ref.page)
        else:
            mapping.append(SourceReference(file_uuid=ref.file_uuid, pages=[ref.page], rotation=ref.rotation))
    return mapping


def _local_page(page: Optional[int], doc_pages: List[int]) -> Optional[int]:
    """Translates a page of the analyzed PDF into the 1-based page within the logical document."""
    if page is None or page not in doc_pages:
        return None
    return doc_pages.index(page) + 1


# --------------------------------------------------------------------- tags

def build_type_tags(primary: Optional[str], type_tags: List[str], direction: Optional[str],
                    tenant_context: Optional[str]) -> List[str]:
    """
    Builds the KPaperFlux type_tags of a logical document.

    Mirrors the classic composition: document types first (primary type
    leading), then the direction and ``CTX_<tenant>`` unless unknown.

    Args:
        primary: FluxSense primary ``type``.
        type_tags: FluxSense ``type_tags``.
        direction: INBOUND | OUTBOUND | INTERNAL | UNKNOWN.
        tenant_context: PRIVATE | BUSINESS | UNKNOWN.

    Returns:
        Ordered, de-duplicated tag list.
    """
    tags: List[str] = []
    for tag in [primary, *type_tags]:
        if tag and tag not in tags:
            tags.append(str(tag))
    if not tags:
        tags.append("OTHER")
    if direction and direction != UNKNOWN and direction not in tags:
        tags.append(direction)
    if tenant_context and tenant_context != UNKNOWN and f"CTX_{tenant_context}" not in tags:
        tags.append(f"CTX_{tenant_context}")
    return tags


def doc_type_tags(doc: Dict[str, Any]) -> List[str]:
    """Document types only (primary first), as stored in ``semantic_data.type_tags``."""
    return build_type_tags(doc.get("type"), list(doc.get("type_tags") or []), None, None)


# --------------------------------------------------------------------- engine info

def build_field_states(evidence: List[Dict[str, Any]], doc_pages: List[int]) -> List[FieldReviewState]:
    """
    Converts FluxSense evidence records into per-field review states.

    Args:
        evidence: ``logical_documents[].evidence``.
        doc_pages: Pages of the analyzed PDF that form the logical document.

    Returns:
        One FieldReviewState per evidence record; ``page`` is document-local.
    """
    states: List[FieldReviewState] = []
    for record in evidence:
        if not isinstance(record, dict) or not record.get("path"):
            continue
        data = {key: record.get(key) for key in _EVIDENCE_KEYS if record.get(key) is not None}
        data["page"] = _local_page(record.get("matched_page") or record.get("page"), doc_pages)
        states.append(FieldReviewState.model_validate(data))
    return states


def build_table_infos(tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Keeps table metadata without duplicating the rows (they live in the bodies).

    ``row_pages`` preserves the per-row source page, which has no home in the
    KPaperFlux line item model.

    Args:
        tables: ``logical_documents[].tables``.

    Returns:
        Table metadata dicts.
    """
    infos: List[Dict[str, Any]] = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        rows = table.get("rows") or []
        infos.append({
            "name": table.get("name"),
            "path": table.get("path"),
            "columns": list(table.get("columns") or []),
            "source_pages": list(table.get("source_pages") or []),
            "strategy": table.get("strategy"),
            "row_count": len(rows),
            "row_pages": [row.get("source_page") if isinstance(row, dict) else None for row in rows],
        })
    return infos


def build_engine_info(result: Dict[str, Any], doc: Dict[str, Any], warnings: Optional[List[str]] = None) -> EngineInfo:
    """
    Builds the engine metadata block stored in ``semantic_data.engine``.

    Args:
        result: The complete FluxSense AnalysisResult.
        doc: One entry of ``result["logical_documents"]``.
        warnings: Adapter warnings to record.

    Returns:
        The EngineInfo.
    """
    pages = [int(p) for p in doc.get("pages") or []]
    fields = doc.get("fields") or {}
    errors = [str(e) for e in (result.get("errors") or [])] + [str(e) for e in (doc.get("errors") or [])]
    return EngineInfo(
        name=ENGINE_NAME,
        version=result.get("fluxsense_version"),
        schema_version=result.get("schema_version"),
        prompt_version=result.get("prompt_version"),
        status=str(result.get("status") or "OK"),
        subtype=doc.get("subtype"),
        classification_confidence=doc.get("confidence"),
        model_confidence=fields.get("ai_confidence"),
        analyzed_pages=pages,
        fields=build_field_states(list(doc.get("evidence") or []), pages),
        plausibility=dict(doc.get("plausibility") or {}),
        review=doc.get("review"),
        trust=dict(doc.get("trust") or {}),
        zugferd_comparison=doc.get("zugferd_comparison"),
        tables=build_table_infos(list(doc.get("tables") or [])),
        timings={k: float(v) for k, v in (result.get("timings") or {}).items() if isinstance(v, (int, float))},
        errors=errors,
        warnings=list(warnings or []),
    )


def failure_causes(result: Dict[str, Any], limit: int = 3) -> List[str]:
    """
    Distinct low-level causes of a failed run: AI call errors (e.g. 'Backend
    unreachable: ...') and text layer warnings. FluxSense reports these only
    per call, not in the result's error list.

    Args:
        result: The FluxSense AnalysisResult.
        limit: Maximum number of causes.

    Returns:
        Causes in order of first occurrence.
    """
    causes: List[str] = []
    for call in result.get("ai_calls") or []:
        error = call.get("error") if isinstance(call, dict) else None
        if error and not call.get("ok", False) and str(error) not in causes:
            causes.append(str(error))
    for warning in (result.get("text_layer") or {}).get("warnings") or []:
        if str(warning) not in causes:
            causes.append(str(warning))
    return causes[:limit]


def backend_unreachable(result: Optional[Dict[str, Any]]) -> bool:
    """
    Tells whether a failed FluxSense run could not reach its AI server.

    Args:
        result: The FluxSense AnalysisResult (or None).

    Returns:
        True if any failed AI call reports an unreachable backend.
    """
    for call in (result or {}).get("ai_calls") or []:
        if isinstance(call, dict) and not call.get("ok", False) and str(call.get("error") or "").startswith(_UNREACHABLE_PREFIX):
            return True
    return False


def unreachable_message(server_url: Optional[str]) -> str:
    """
    Generic, user-facing text for an unreachable AI server (stored with the held document).

    Args:
        server_url: The server address, if known.

    Returns:
        The message.
    """
    where = server_url or "the configured address"
    return f"AI server not reachable at {where}. Please check the AI server settings."


def engine_error_info(message: str, result: Optional[Dict[str, Any]] = None, error_code: Optional[str] = None,
                      server_url: Optional[str] = None) -> EngineInfo:
    """
    Builds the engine metadata of a failed run (document stays retryable).

    Args:
        message: Error description (first entry of errors).
        result: The FluxSense result, if one was returned.
        error_code: Machine-readable reason (e.g. ERROR_AI_SERVER_UNREACHABLE).
        server_url: The server the run depended on.

    Returns:
        EngineInfo with status ERROR.
    """
    result = result or {}
    errors = [message]
    for error in [*(result.get("errors") or []), *failure_causes(result)]:
        if str(error) not in errors:
            errors.append(str(error))
    for doc in result.get("logical_documents") or []:
        errors += [str(e) for e in (doc.get("errors") or []) if str(e) not in errors]
    return EngineInfo(
        name=ENGINE_NAME,
        version=result.get("fluxsense_version"),
        schema_version=result.get("schema_version"),
        prompt_version=result.get("prompt_version"),
        status=RESULT_STATUS_ERROR,
        errors=errors,
        error_code=error_code,
        server_url=server_url,
    )


# --------------------------------------------------------------------- semantic

def _validation_summary(error: ValidationError) -> str:
    """Short, single-line description of a pydantic validation error."""
    first = error.errors()[0] if error.errors() else {}
    location = ".".join(str(part) for part in first.get("loc", ()))
    return f"{error.error_count()} errors, first at '{location}': {first.get('msg', '')}"


def _validate_piecewise(payload: Dict[str, Any], warnings: List[str], unvalidated: Dict[str, Any]) -> SemanticExtraction:
    """
    Validates the extraction section by section after the full validation failed.

    Sections that fail are kept verbatim in ``unvalidated`` so nothing is lost.
    """
    semantic = SemanticExtraction(bodies=payload.get("bodies") or {})
    for key, model in (("meta_header", MetaHeader), ("visual_audit", VisualAuditResult)):
        raw = payload.get(key)
        if raw is None:
            continue
        try:
            setattr(semantic, key, model.model_validate(raw))
        except ValidationError as e:
            warnings.append(f"{key} failed validation and was kept unvalidated ({_validation_summary(e)})")
            unvalidated[key] = raw
    for key in ("repaired_text", "extraction_source"):
        if payload.get(key) is not None:
            setattr(semantic, key, payload[key])
    return semantic


def _check_typed_bodies(raw_bodies: Dict[str, Any], semantic: SemanticExtraction, warnings: List[str]) -> None:
    """Records bodies that stayed untyped because they did not match the KPaperFlux model."""
    for key, model in TYPED_BODIES.items():
        if key in raw_bodies and isinstance(semantic.bodies.get(key), dict):
            try:
                model.model_validate(raw_bodies[key])
                reason = "unknown reason"
            except ValidationError as e:
                reason = _validation_summary(e)
            warnings.append(f"bodies.{key} kept as untyped dict ({reason})")


def build_semantic(doc: Dict[str, Any], engine: EngineInfo) -> Tuple[SemanticExtraction, List[str]]:
    """
    Validates FluxSense ``fields`` through the KPaperFlux SemanticExtraction model.

    Overrides the classification context with the logical document's values,
    sets ``ai_confidence`` from the trust score and attaches the engine block.

    Args:
        doc: One entry of ``result["logical_documents"]``.
        engine: Engine metadata to attach (its warnings are extended).

    Returns:
        Tuple (semantic extraction, adapter warnings).
    """
    fields = doc.get("fields") or {}
    warnings: List[str] = []
    payload: Dict[str, Any] = {key: fields[key] for key in ("meta_header", "bodies", "repaired_text", "extraction_source")
                               if fields.get(key) is not None}
    visual_audit = doc.get("visual_audit") or fields.get("visual_audit")
    if visual_audit is not None:
        payload["visual_audit"] = visual_audit
    try:
        semantic = SemanticExtraction.model_validate(payload)
    except ValidationError as e:
        warnings.append(f"fields failed full validation ({_validation_summary(e)}); validated section by section")
        semantic = _validate_piecewise(payload, warnings, engine.unvalidated)
    _check_typed_bodies(payload.get("bodies") or {}, semantic, warnings)

    semantic.type_tags = doc_type_tags(doc)
    if doc.get("direction"):
        semantic.direction = doc["direction"]
    if doc.get("tenant_context"):
        semantic.tenant_context = doc["tenant_context"]
    semantic.ai_confidence = trust_confidence(doc)
    if not semantic.extraction_source:
        semantic.extraction_source = "AI"
    engine.warnings.extend(warnings)
    semantic.engine = engine
    return semantic, warnings


def trust_confidence(doc: Dict[str, Any]) -> float:
    """
    Document confidence for KPaperFlux: the FluxSense trust score, clamped to 0..1.

    Args:
        doc: One entry of ``result["logical_documents"]``.

    Returns:
        Confidence (0.0 for failed documents).
    """
    if is_failed_document(doc):
        return 0.0
    score = (doc.get("trust") or {}).get("score")
    if not isinstance(score, (int, float)):
        return 0.0
    return max(0.0, min(1.0, float(score)))


def is_failed_document(doc: Dict[str, Any]) -> bool:
    """FluxSense marks a logical document as failed when it has errors and no fields."""
    return bool(doc.get("errors")) and not doc.get("fields")


# --------------------------------------------------------------------- result

def _adapt_document(result: Dict[str, Any], doc: Dict[str, Any], pages: List[int], page_refs: List[PageRef],
                    warnings: List[str]) -> AdaptedEntity:
    """Maps one logical document onto the given analyzed pages."""
    engine = build_engine_info(result, doc, warnings)
    semantic, _ = build_semantic(doc, engine)
    return AdaptedEntity(
        pages=pages,
        source_mapping=map_pages_to_source(pages, page_refs),
        type_tags=build_type_tags(doc.get("type"), list(doc.get("type_tags") or []),
                                  doc.get("direction"), doc.get("tenant_context")),
        semantic=semantic,
        ai_confidence=trust_confidence(doc),
        failed=is_failed_document(doc),
        errors=[str(e) for e in (doc.get("errors") or [])],
    )


def adapt_result(result: Dict[str, Any], page_refs: List[PageRef], keep_single: bool = False) -> List[AdaptedEntity]:
    """
    Maps a FluxSense AnalysisResult onto KPaperFlux logical documents.

    Args:
        result: The AnalysisResult as JSON dict.
        page_refs: Flattened page sequence of the analyzed PDF.
        keep_single: Do not split (protected, manually edited or re-extracted
            documents): one entity covering all pages, built from the first
            usable logical document.

    Returns:
        Adapted entities in FluxSense order (first page ascending). Empty if
        FluxSense found no logical document.

    Raises:
        FluxSenseResultError: If the engine reported status ERROR or the result is malformed.
    """
    if not isinstance(result, dict) or not isinstance(result.get("logical_documents"), list):
        raise FluxSenseResultError("FluxSense result has no logical_documents list")
    if result.get("status") == RESULT_STATUS_ERROR:
        causes = failure_causes(result, limit=1)
        raise FluxSenseResultError("FluxSense reported status ERROR" + (f": {causes[0]}" if causes else ""))
    docs = [d for d in result["logical_documents"] if isinstance(d, dict)]
    if not docs:
        return []

    if keep_single:
        usable = [d for d in docs if not is_failed_document(d)]
        chosen = (usable or docs)[0]
        warnings: List[str] = []
        if len(docs) > 1:
            warnings.append(f"split into {len(docs)} documents suppressed (protected); "
                            f"fields taken from the document on pages {chosen.get('pages')}")
        all_pages = list(range(1, len(page_refs) + 1))
        return [_adapt_document(result, chosen, all_pages, page_refs, warnings)]

    entities: List[AdaptedEntity] = []
    for doc in docs:
        pages = [int(p) for p in doc.get("pages") or []]
        entity = _adapt_document(result, doc, pages, page_refs, [])
        if entity.source_mapping:
            entities.append(entity)
    return entities


def resolve_field_path(data: Any, path: str) -> Any:
    """
    Resolves a dotted FluxSense evidence path against semantic data.

    Numeric segments index lists (``meta_header.references.0.ref_value``).

    Args:
        data: A SemanticExtraction, model or (nested) dict.
        path: Dotted path.

    Returns:
        The value, or None if the path does not exist.
    """
    node: Any = data
    for part in path.split("."):
        if node is None:
            return None
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                return None
            node = node[int(part)]
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            node = getattr(node, part, None)
    return node
