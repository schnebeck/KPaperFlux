"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/utils/docling_extractor.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Text extraction via a docling-serve instance (REST API v1).
                Uploads a PDF (read-only, the source file is never modified)
                and converts the returned DoclingDocument into per-page
                Markdown: {"1": markdown, "2": ...}.
------------------------------------------------------------------------------
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from core.logger import get_logger

logger = get_logger("docling")

# --- docling-serve v1 API contract (kept in one place) ---------------------
ENDPOINT_CONVERT_FILE: str = "/v1/convert/file"
FIELD_FILES: str = "files"
FIELD_TO_FORMATS: str = "to_formats"
FIELD_PIPELINE: str = "pipeline"
FIELD_DO_OCR: str = "do_ocr"
FIELD_FORCE_OCR: str = "force_ocr"
FIELD_OCR_LANG: str = "ocr_lang"
FIELD_IMAGE_EXPORT_MODE: str = "image_export_mode"
FIELD_VLM_MODEL: str = "vlm_pipeline_model"
FIELD_PAGE_BREAK: str = "md_page_break_placeholder"
FIELD_ABORT_ON_ERROR: str = "abort_on_error"

RESP_DOCUMENT: str = "document"
RESP_MD: str = "md_content"
RESP_JSON: str = "json_content"
RESP_STATUS: str = "status"
RESP_ERRORS: str = "errors"
RESP_PROCESSING_TIME: str = "processing_time"

OK_STATUSES: Tuple[str, ...] = ("success", "partial_success")
PIPELINES: Tuple[str, ...] = ("standard", "vlm")
DEFAULT_VLM_MODEL: str = "granite_docling"
DEFAULT_OCR_LANG: Tuple[str, ...] = ("de", "en")
PAGE_BREAK_MARKER: str = "<!-- KPF_PAGE_BREAK -->"
CONNECT_TIMEOUT_S: float = 10.0

_SKIP_LABELS: frozenset = frozenset({"picture", "chart"})


class DoclingError(Exception):
    """Raised when docling-serve cannot be reached or reports a failed conversion."""


def _bool_str(value: bool) -> str:
    """Encodes a boolean as multipart form value."""
    return "true" if value else "false"


def _render_text_item(item: Dict[str, Any]) -> str:
    """
    Renders a DoclingDocument text item as Markdown.

    Args:
        item: Entry of ``texts``.

    Returns:
        Markdown fragment (may be empty).
    """
    text = str(item.get("text") or "").strip()
    if not text:
        return ""
    label = item.get("label", "text")
    if label == "title":
        return f"# {text}"
    if label == "section_header":
        level = int(item.get("level") or 1)
        return f"{'#' * min(6, level + 1)} {text}"
    if label == "list_item":
        marker = str(item.get("marker") or "-").strip() or "-"
        return f"{marker} {text}"
    if label in ("code", "formula"):
        return f"```\n{text}\n```"
    return text


def _render_table_item(item: Dict[str, Any]) -> str:
    """
    Renders a DoclingDocument table item as a Markdown table.

    Args:
        item: Entry of ``tables``.

    Returns:
        Markdown table (may be empty).
    """
    data = item.get("data") or {}
    grid: List[List[Dict[str, Any]]] = data.get("grid") or []
    if not grid:
        # Reconstruct grid from flat cell list
        n_rows = int(data.get("num_rows") or 0)
        n_cols = int(data.get("num_cols") or 0)
        if n_rows <= 0 or n_cols <= 0:
            return ""
        grid = [[{} for _ in range(n_cols)] for _ in range(n_rows)]
        for cell in data.get("table_cells") or []:
            r = cell.get("start_row_offset_idx", 0)
            c = cell.get("start_col_offset_idx", 0)
            if 0 <= r < n_rows and 0 <= c < n_cols:
                grid[r][c] = cell

    rows: List[str] = []
    for r_idx, row in enumerate(grid):
        cells = [str((cell or {}).get("text") or "").replace("|", "\\|").replace("\n", " ").strip() for cell in row]
        rows.append("| " + " | ".join(cells) + " |")
        if r_idx == 0:
            rows.append("|" + "|".join(" --- " for _ in cells) + "|")
    return "\n".join(rows)


def _item_page(item: Dict[str, Any]) -> Optional[int]:
    """Returns the first provenance page number of a document item."""
    for prov in item.get("prov") or []:
        page_no = prov.get("page_no")
        if isinstance(page_no, int):
            return page_no
    return None


def _resolve_ref(doc: Dict[str, Any], ref: str) -> Optional[Dict[str, Any]]:
    """Resolves a JSON pointer like '#/texts/3' inside a DoclingDocument."""
    parts = ref.lstrip("#/").split("/")
    if len(parts) != 2:
        return None
    collection = doc.get(parts[0])
    try:
        idx = int(parts[1])
    except ValueError:
        logger.debug(f"Unresolvable docling reference: {ref}")
        return None
    if isinstance(collection, list) and 0 <= idx < len(collection):
        return collection[idx]
    return None


def _iter_reading_order(doc: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Returns (collection, item) pairs in reading order by walking ``body``.
    Falls back to texts followed by tables if the tree is missing.
    """
    ordered: List[Tuple[str, Dict[str, Any]]] = []
    seen: set = set()

    def walk(node: Dict[str, Any]) -> None:
        for child in node.get("children") or []:
            ref = child.get("$ref") or child.get("cref")
            if not ref or ref in seen:
                continue
            seen.add(ref)
            item = _resolve_ref(doc, ref)
            if item is None:
                continue
            collection = ref.lstrip("#/").split("/")[0]
            if collection in ("texts", "tables", "pictures"):
                ordered.append((collection, item))
            walk(item)

    body = doc.get("body")
    if isinstance(body, dict):
        walk(body)
    if not ordered:
        ordered = [("texts", t) for t in doc.get("texts") or []] + [("tables", t) for t in doc.get("tables") or []]
    return ordered


def pages_from_docling_json(doc: Dict[str, Any]) -> Dict[str, str]:
    """
    Builds per-page Markdown from a DoclingDocument JSON export.

    Args:
        doc: The DoclingDocument dictionary (``json_content``).

    Returns:
        Mapping of 1-based page number (as string) to Markdown. Empty if the
        document carries no provenance page information.
    """
    pages: Dict[int, List[str]] = {}
    for collection, item in _iter_reading_order(doc):
        if item.get("label") in _SKIP_LABELS or collection == "pictures":
            continue
        page_no = _item_page(item)
        if page_no is None:
            continue
        fragment = _render_table_item(item) if collection == "tables" else _render_text_item(item)
        if fragment:
            pages.setdefault(page_no, []).append(fragment)
    return {str(p): "\n\n".join(parts) for p, parts in sorted(pages.items())}


def pages_from_response(response: Dict[str, Any]) -> Dict[str, str]:
    """
    Converts a docling-serve convert response into per-page text.

    Strategy: DoclingDocument JSON provenance -> Markdown page-break markers ->
    whole Markdown on page 1.

    Args:
        response: Decoded JSON body of /v1/convert/file.

    Returns:
        Mapping of 1-based page number (as string) to Markdown.

    Raises:
        DoclingError: If the conversion failed.
    """
    status = response.get(RESP_STATUS)
    if status not in OK_STATUSES:
        raise DoclingError(f"Conversion status '{status}': {response.get(RESP_ERRORS)}")
    if status != "success":
        logger.warning(f"Docling partial conversion: {response.get(RESP_ERRORS)}")

    document = response.get(RESP_DOCUMENT) or {}
    doc_json = document.get(RESP_JSON)
    if isinstance(doc_json, str):
        try:
            doc_json = json.loads(doc_json)
        except json.JSONDecodeError as e:
            logger.warning(f"Docling json_content not decodable: {e}")
            doc_json = None
    if isinstance(doc_json, dict):
        pages = pages_from_docling_json(doc_json)
        if pages:
            return pages

    markdown = str(document.get(RESP_MD) or "")
    if PAGE_BREAK_MARKER in markdown:
        chunks = markdown.split(PAGE_BREAK_MARKER)
        return {str(i + 1): chunk.strip() for i, chunk in enumerate(chunks) if chunk.strip()}
    markdown = markdown.strip()
    return {"1": markdown} if markdown else {}


class DoclingExtractor:
    """Client for docling-serve's synchronous file conversion endpoint."""

    def __init__(
        self,
        base_url: str,
        pipeline: str = "standard",
        timeout: int = 900,
        ocr_lang: Sequence[str] = DEFAULT_OCR_LANG,
        vlm_model: str = DEFAULT_VLM_MODEL,
    ) -> None:
        """
        Initializes the extractor.

        Args:
            base_url: docling-serve base URL (e.g. http://host:5001).
            pipeline: 'standard' (layout + OCR) or 'vlm' (e.g. granite-docling).
            timeout: Read timeout for one conversion in seconds.
            ocr_lang: OCR languages (codes as expected by the server's OCR engine).
            vlm_model: VLM preset used when pipeline == 'vlm'.
        """
        if pipeline not in PIPELINES:
            raise ValueError(f"Unknown docling pipeline: {pipeline}")
        self.base_url: str = base_url.rstrip("/")
        self.pipeline: str = pipeline
        self.timeout: int = int(timeout)
        self.ocr_lang: List[str] = list(ocr_lang)
        self.vlm_model: str = vlm_model

    def build_form_data(self, force_ocr: bool = False) -> List[Tuple[str, str]]:
        """
        Builds the multipart form fields (list values are repeated keys).

        Args:
            force_ocr: Ignore an existing text layer and OCR every page.

        Returns:
            List of (field, value) tuples.
        """
        fields: List[Tuple[str, str]] = [
            (FIELD_TO_FORMATS, "md"),
            (FIELD_TO_FORMATS, "json"),
            (FIELD_PIPELINE, self.pipeline),
            (FIELD_DO_OCR, _bool_str(True)),
            (FIELD_FORCE_OCR, _bool_str(force_ocr)),
            (FIELD_IMAGE_EXPORT_MODE, "placeholder"),
            (FIELD_PAGE_BREAK, PAGE_BREAK_MARKER),
            (FIELD_ABORT_ON_ERROR, _bool_str(False)),
        ]
        fields.extend((FIELD_OCR_LANG, lang) for lang in self.ocr_lang)
        if self.pipeline == "vlm":
            fields.append((FIELD_VLM_MODEL, self.vlm_model))
        return fields

    def convert(self, pdf_path: Path, force_ocr: bool = False) -> Dict[str, Any]:
        """
        Uploads a PDF for conversion. The file is opened read-only.

        Args:
            pdf_path: Source PDF.
            force_ocr: Ignore an existing text layer.

        Returns:
            The decoded response body.

        Raises:
            DoclingError: On transport errors or non-200 responses.
        """
        url = f"{self.base_url}{ENDPOINT_CONVERT_FILE}"
        path = Path(pdf_path)
        try:
            with path.open("rb") as fh:
                files = {FIELD_FILES: (path.name, fh, "application/pdf")}
                resp = requests.post(url, files=files, data=self.build_form_data(force_ocr), timeout=(CONNECT_TIMEOUT_S, self.timeout))
        except requests.RequestException as e:
            raise DoclingError(f"docling-serve request to {url} failed: {e}") from e
        except OSError as e:
            raise DoclingError(f"Cannot read {path}: {e}") from e

        if resp.status_code != 200:
            raise DoclingError(f"docling-serve HTTP {resp.status_code}: {(resp.text or '')[:500]}")
        try:
            body = resp.json()
        except ValueError as e:
            raise DoclingError(f"docling-serve returned non-JSON body: {e}") from e
        if not isinstance(body, dict):
            raise DoclingError(f"Unexpected docling-serve body type: {type(body).__name__}")
        return body

    def extract_pages(self, pdf_path: Path, force_ocr: bool = False) -> Dict[str, str]:
        """
        Converts a PDF and returns per-page Markdown.

        Args:
            pdf_path: Source PDF (never modified).
            force_ocr: Ignore an existing text layer.

        Returns:
            Mapping of 1-based page number (as string) to Markdown.

        Raises:
            DoclingError: If the conversion failed.
        """
        response = self.convert(pdf_path, force_ocr=force_ocr)
        pages = pages_from_response(response)
        logger.info(
            f"Docling ({self.pipeline}) extracted {len(pages)} page(s) from {Path(pdf_path).name} "
            f"in {response.get(RESP_PROCESSING_TIME)}s"
        )
        return pages
