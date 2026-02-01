"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai_analyzer.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Intelligence Layer for semantic document analysis and extraction.
                Handles Google Gemini API interaction, adaptive scan modes,
                and structured data extraction using Pydantic schemas.
------------------------------------------------------------------------------
"""

import base64
import datetime
import json
import random
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import fitz  # PyMuPDF
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from core.config import AppConfig
from core.models.canonical_entity import (
    BankStatementData,
    ContractData,
    DocType,
    ExpenseData,
    InsuranceData,
    InvoiceData,
    LegalMetaData,
    LogisticsData,
    MedicalData,
    TaxAssessmentData,
    UtilityData,
    VehicleData,
)
from core.models.identity import IdentityProfile


class AIAnalysisResult(BaseModel):
    """
    Data container for AI analysis results.
    
    Attributes:
        sender: Name of the sender.
        doc_date: Date of the document.
        amount: Net amount.
        gross_amount: Gross amount.
        postage: Postage costs.
        packaging: Packaging costs.
        tax_rate: Tax rate percentage.
        currency: Currency code (e.g., EUR).
        doc_type: Document type.
        sender_address: Full address of the sender.
        iban: IBAN found in the document.
        phone: Phone number found in the document.
        tags: Suggested tags.
        recipient_company: Name of the recipient company.
        recipient_name: Name of the recipient person.
        recipient_street: Recipient street address.
        recipient_zip: Recipient ZIP code.
        recipient_city: Recipient city.
        recipient_country: Recipient country.
        sender_company: Name of the sender company.
        sender_name: Name of the sender person.
        sender_street: Sender street address.
        sender_zip: Sender ZIP code.
        sender_city: Sender city.
        sender_country: Sender country.
        extra_data: Additional raw data.
        semantic_data: Full structured semantic data tree.
    """

    sender: Optional[str] = None
    doc_date: Optional[datetime.date] = None
    amount: Optional[Decimal] = None

    # Financial Details
    gross_amount: Optional[Decimal] = None
    postage: Optional[Decimal] = None
    packaging: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    currency: Optional[str] = None

    doc_type: Optional[str] = None
    sender_address: Optional[str] = None
    iban: Optional[str] = None
    phone: Optional[str] = None
    tags: Optional[str] = None

    # Structured Details
    recipient_company: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_street: Optional[str] = None
    recipient_zip: Optional[str] = None
    recipient_city: Optional[str] = None
    recipient_country: Optional[str] = None

    sender_company: Optional[str] = None
    sender_name: Optional[str] = None
    sender_street: Optional[str] = None
    sender_zip: Optional[str] = None
    sender_city: Optional[str] = None
    sender_country: Optional[str] = None

    # Metadata & Semantic Data
    extra_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    semantic_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AIAnalyzer:
    """
    Analyzes document text using Google Gemini to extract structured data.
    
    Provides high-level methods for document classification, semantic extraction,
    and adaptive scan strategies.
    """

    MAX_RETRIES: int = 5
    _cooldown_until: Optional[datetime.datetime] = None  # Shared cooldown state
    _adaptive_delay: float = 0.0  # Adaptive delay in seconds
    _printed_prompts: Set[str] = set()  # Debug tracking

    def _print_debug_prompt(self, title: str, prompt: str) -> None:
        """
        Prints the AI prompt to the console for debugging purposes (only once per unique prompt).

        Args:
            title: The debug section title.
            prompt: The full prompt string.
        """
        if prompt not in self._printed_prompts:
            # Uncomment for verbose prompt debugging
            # print(f"\n=== [{title}] ===\n{prompt}\n==============================\n")
            self._printed_prompts.add(prompt)

    @classmethod
    def get_adaptive_delay(cls) -> float:
        """
        Retrieves the current adaptive delay value.

        Returns:
            The delay in seconds.
        """
        return cls._adaptive_delay

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash") -> None:
        """
        Initializes the AIAnalyzer with Gemini API credentials.

        Args:
            api_key: The Google GenAI API key.
            model_name: The target Gemini model name.
        """
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model_name
        self.config = AppConfig()

        # Dynamic Model Limits
        self.max_output_tokens: int = 65536
        self._fetch_model_limits()

    def _fetch_model_limits(self) -> None:
        """
        Queries the API for model limits and applies safety overrides for Flash models.
        """
        try:
            m = self.client.models.get(model=self.model_name)
            self.max_output_tokens = getattr(m, "output_token_limit", 8192)

            # Safety Override for Flash Models:
            # Even if API reports 8k, Flash models usually support 64k or more.
            if "flash" in self.model_name.lower():
                if self.max_output_tokens < 65536:
                    print(f"[AI] Model Info: {self.model_name} (API Limit: {self.max_output_tokens}). Applying 64k Flash Strategy.")
                    self.max_output_tokens = 65536
                else:
                    print(f"[AI] Model Info: {self.model_name} (API Limit: {self.max_output_tokens}). Using official limit.")
            else:
                print(f"[AI] Model Info: {self.model_name} (API Limit: {self.max_output_tokens})")
        except Exception as e:
            print(f"[AI] Warning: Could not fetch limits for {self.model_name}: {e}. Falling back to 64k.")
            self.max_output_tokens = 65536

    def list_models(self) -> List[str]:
        """
        Fetches available models from the Google GenAI API and filters for those supporting generateContent.

        Returns:
            A sorted list of available model names.
        """
        models = []
        for m in self.client.models.list():
            if hasattr(m, "supported_actions") and "generateContent" in m.supported_actions:
                name = m.name
                if name.startswith("models/"):
                    name = name[7:]
                models.append(name)
        return sorted(models)

    @staticmethod
    def extract_headers_footers(ocr_pages: List[str], header_ratio: float = 0.15, footer_ratio: float = 0.10) -> List[str]:
        """
        Reduces the text of each page to the top and bottom regions to save tokens.

        Args:
            ocr_pages: List of strings containing OCR text for each page.
            header_ratio: The ratio of the top area to keep.
            footer_ratio: The ratio of the bottom area to keep.

        Returns:
            A list of optimized strings for each page.
        """
        optimized_pages = []
        for text in ocr_pages:
            lines = text.split("\n")
            total_lines = len(lines)
            if total_lines < 10:
                optimized_pages.append(text)
                continue

            cut_top = int(total_lines * header_ratio)
            cut_bottom = int(total_lines * footer_ratio)

            if cut_top + cut_bottom >= total_lines:
                optimized_pages.append(text)
            else:
                header = "\n".join(lines[:cut_top])
                footer = "\n".join(lines[-cut_bottom:])
                optimized_pages.append(f"[HEADER AREA]\n{header}\n...\n[FOOTER AREA]\n{footer}")

        return optimized_pages

    def ask_type_check(self, pre_flight_pages: List[str]) -> dict:
        """
        Phase A: Pre-Flight. Quick check of first few pages to determine strategy.
        """
        content = "\n".join([f"--- PAGE {i+1} ---\n{p}" for i, p in enumerate(pre_flight_pages)])
        prompt = f"""
        Analyze the following document start and determine its nature.

        ### INPUT TEXT
        {content}

        ### TASK
        Return a JSON object:
        {{
          "primary_type": "MANUAL | DATASHEET | BOOK | CATALOG | INVOICE | LETTER | OTHER",
          "is_hybrid_suspicion": true | false, // True if first page suggests multiple roles (e.g. 'Invoice & Delivery Note')
          "looks_like_stack": true | false, // True if multiple different documents seem stuck together
          "confidence": 0.0-1.0
        }}
        """
        result = self._generate_json(prompt, stage_label="Stage 1.0 (Pre-Flight)")
        return result or {}

    def run_stage_1_adaptive(self, pages_text: List[str], private_id: Optional[IdentityProfile], business_id: Optional[IdentityProfile]) -> dict:
        """
        Intelligent Controller for Stage 1.
        Selects optimal scan strategy based on content.
        """
        total_pages = len(pages_text)
        if total_pages == 0: return {}

        # --- PHASE A: PRE-FLIGHT ---
        print(f"[AI] Stage 1.0 (Pre-Flight) [START] -> Analyzing {total_pages} pages...")
        pre_flight_pages = pages_text[:3]
        pre_flight_res = self.ask_type_check(pre_flight_pages)
        print(f"[AI] Stage 1.0 (Pre-Flight) [DONE]")

        primary_type = pre_flight_res.get("primary_type", "OTHER")
        is_stack_suspicion = pre_flight_res.get("looks_like_stack", False)

        print(f"[AI] Stage 1.0 (Pre-Flight) -> {total_pages} Pages. Type: {primary_type}. Stack: {is_stack_suspicion}")

        # --- PHASE B: ROUTING ---
        scan_strategy = "FULL_READ_MODE"
        final_pages_to_scan = []

        # 1. Manual/Book detection
        if primary_type in ["MANUAL", "DATASHEET", "BOOK", "CATALOG"]:
            scan_strategy = "SANDWICH_MODE"
            indices = [0, 1, 2, total_pages - 1]
            indices = sorted(list(set(i for i in indices if i < total_pages)))
            for i in indices:
                final_pages_to_scan.append(pages_text[i])

        # 2. Large Stack detection
        elif total_pages > 10 or is_stack_suspicion:
            scan_strategy = "HEADER_SCAN_MODE"
            # Extract headers/footers for ALL pages
            final_pages_to_scan = self.extract_headers_footers(pages_text)

        # 3. Default (Short docs)
        else:
            scan_strategy = "FULL_READ_MODE"
            final_pages_to_scan = pages_text

        # print(f"[AI] Selected Strategy: {scan_strategy} ({len(final_pages_to_scan)} pages prepared)")

        # --- PHASE C: EXECUTION ---
        return self.classify_structure(final_pages_to_scan, private_id, business_id, mode=scan_strategy)

    def _wait_for_cooldown(self):
        """Check shared cooldown and sleep if necessary."""
        if AIAnalyzer._cooldown_until:
            now = datetime.datetime.now()
            if AIAnalyzer._cooldown_until > now:
                wait_time = (AIAnalyzer._cooldown_until - now).total_seconds()
                if wait_time > 0:
                    print(f"AI Rate Limit Active. Sleeping for {wait_time:.1f}s...")
                    time.sleep(wait_time)

            # Clear cooldown after waiting or if expired
            AIAnalyzer._cooldown_until = None


    def _generate_with_retry(self, contents: Any) -> Optional[Any]:
        """
        Executes the content generation with robust 429 handling and adaptive delay.

        Args:
            contents: The contents to send to the Gemini model (can be a list or a dict with config).

        Returns:
            The response object from the API or None if all retries fail.
        """
        # 0. Adaptive Delay
        if self._adaptive_delay > 0:
            print(f"AI Adaptive Delay: Sleeping {self._adaptive_delay:.2f}s...")
            time.sleep(self._adaptive_delay)

        response = None
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            if attempt > 0:
                print(f"AI Retrying... (Attempt {attempt+1}/{self.MAX_RETRIES})")

            self._wait_for_cooldown()

            try:
                # Handle dictionary input with config
                req_config = None
                call_contents = contents
                if isinstance(contents, dict) and "config" in contents:
                    req_config = contents["config"]
                    call_contents = contents["contents"]

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=call_contents,
                    config=req_config
                )

                # Success: Decrease Adaptive Delay
                if self._adaptive_delay > 0:
                    old_delay = self._adaptive_delay
                    self._adaptive_delay = max(0.0, self._adaptive_delay * 0.5)
                    if self._adaptive_delay < 0.1:
                        self._adaptive_delay = 0.0
                    print(f"AI Success (Attempt {attempt+1}/{self.MAX_RETRIES}). Decreasing Delay: {old_delay:.2f}s -> {self._adaptive_delay:.2f}s")
                elif attempt > 0:
                    print(f"AI Success after {attempt+1} attempts.")

                return response

            except Exception as e:
                last_error = e
                is_429 = False

                if hasattr(e, "code") and e.code == 429:
                    is_429 = True
                if hasattr(e, "status") and "RESOURCE_EXHAUSTED" in str(e.status):
                    is_429 = True
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    is_429 = True

                if is_429:
                    old_delay = self._adaptive_delay
                    new_delay = max(2.0, self._adaptive_delay * 2.0)
                    self._adaptive_delay = min(256.0, new_delay)

                    if self._adaptive_delay != old_delay:
                        print(f"AI Rate Limit Hit! Increasing Delay: {old_delay:.2f}s -> {self._adaptive_delay:.2f}s")

                    backoff = 2 * (2 ** attempt) + random.uniform(0, 1)
                    delay = max(backoff, self._adaptive_delay)
                    print(f"[{attempt+1}/{self.MAX_RETRIES}] AI 429. Backing off for {delay:.1f}s")

                    AIAnalyzer._cooldown_until = datetime.datetime.now() + datetime.timedelta(seconds=delay)
                    continue
                else:
                    print(f"AI Error (Attempt {attempt+1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(1)

        print(f"ABORT: AI Analysis failed after {self.MAX_RETRIES} attempts. Last error: {last_error}")
        return None

    def analyze_text(self, text: str, image: Optional[Any] = None) -> AIAnalysisResult:
        """
        Analyzes the document text using Gemini and extracts semantic data.

        Args:
            text: The text content of the document.
            image: Optional image data (first page).

        Returns:
            An AIAnalysisResult object containing extracted data.
        """
        # document_schema used by legacy analyze_text.
        # Inlined for portability (GitHub Safe).
        doc_schema = {
          "type": "object",
          "properties": {
             "summary": { "type": "object", "properties": { "doc_type": { "type": "array", "items": { "type": "string" } }, "main_date": { "type": "string" } } },
             "pages": { "type": "array", "items": { "type": "object" } }
          }
        }

        # Create a simplified One-Shot Example to guide the model away from Schema copying
        example_json = """
        {
          "summary": { "doc_type": ["Invoice"], "main_date": "2025-01-01", "language": "de" },
          "pages": [
            {
              "page_number": 1,
              "regions": [
                {
                   "role": "header",
                   "blocks": [ { "type": "text", "content": "Header Text..." } ]
                },
                {
                   "role": "body",
                   "blocks": [
                      { "type": "key_value", "pairs": [ { "key": "Date", "value": "2025-01-01" } ] }
                   ]
                }
              ]
            }
          ]
        }
        """

        prompt = f"""
        You are a generic document data extraction engine.

        ### 1. THE SCHEMA (TYPE DEFINITION)
        Use this JSON Schema to understand the allowed structure and types.
        {json.dumps(doc_schema, indent=2)}

        ### 2. THE GOAL
        EXTRACT data from the text below and FORMAT it as a valid JSON INSTANCE of the schema above.
        - DO NOT return the schema definition itself.
        - DO NOT return the "properties" or "type" keywords in your data.
        - Return ONLY the data.

        ### 3. ADVANCED EXTRACTION RULES
        - **Visual Columns**: If you see Keys (left) and Values (right), merge them into `KeyValueBlock` pairs.
        - **Composite Splitting**: Split composite keys "Date/No" -> "Date", "No".
        - **Header Decomposition**: Break headers into structured KeyValue/Address blocks where possible.
        - **Composite Types**: "Rechnung & AB" -> `["Invoice", "Order Confirmation"]`.
        - **Stamps**: Detect ink stamps (e.g. "Received", date stamps) as `StampBlock`. Extract text and date if legible.

        ### 4. EXAMPLE OUTPUT (for format reference)
        {example_json}

        ### 5. INPUT TEXT TO PROCESS
        {text}

        ### 6. YOUR JSON OUTPUT
        """

        self._print_debug_prompt("STAGE 2 AI REQUEST", prompt)

        contents = [prompt]
        if image:
            contents.append(image)

        response = self._generate_with_retry(contents)

        if not response:
            return AIAnalysisResult()

        response_text = response.text

        # Clean up markdown code blocks if present
        if "```json" in response_text:
            response_text = response_text.replace("```json", "").replace("```", "")
        elif "```" in response_text:
            response_text = response_text.replace("```", "")

        try:
            semantic_data = json.loads(response_text)
            print(f"\n=== [STAGE 2 AI RESPONSE] ===\n{json.dumps(semantic_data, indent=2)}\n===========================\n")

            # Hybrid Extraction: Flatten Semantic Data to SQL Columns
            # We need to traverse the tree to find best candidates for:
            # - doc_date (Main Date)
            # - amount (Total Net)
            # - gross_amount (Total Gross)
            # - sender

            # Helper to recursively find key/values
            extracted = {
                "doc_date": None,
                "amount": None,
                "gross_amount": None,
                "sender": None,
                "doc_type": None
            }

            # 1. Check Summary (Quick Path)
            if "summary" in semantic_data:
                summ = semantic_data["summary"]
                extracted["doc_date"] = summ.get("main_date")
                extracted["doc_type"] = summ.get("doc_type")

            # 2. Traverse Blocks for Financials if missing
            # A simple heuristic: Look for KeyValueBlocks with keys like "amount", "total", "net", "brutto"

            def traverse(node):
                if isinstance(node, dict):
                    # Check for KeyValueBlock
                    if node.get("type") == "key_value" and "pairs" in node:
                        for pair in node["pairs"]:
                            k = pair.get("key", "").lower()
                            v = pair.get("value")

                            # Heuristics
                            if not extracted["amount"] and any(x in k for x in ["net", "netto", "total_net", "amount"]):
                                extracted["amount"] = v
                            if not extracted["gross_amount"] and any(x in k for x in ["gross", "brutto", "total_gross"]):
                                extracted["gross_amount"] = v

                    # Check for AddressBlock (Sender)
                    if node.get("type") == "address" and node.get("role") == "sender":
                        if "structured" in node and node["structured"].get("name"):
                             extracted["sender"] = node["structured"]["name"]
                        elif "raw_text" in node and not extracted["sender"]:
                             extracted["sender"] = node["raw_text"].split("\n")[0] # First line?

                    for _, val in node.items():
                        traverse(val)
                elif isinstance(node, list):
                    for item in node:
                        traverse(item)

            traverse(semantic_data)

            # Parse Date
            doc_date = None
            if extracted["doc_date"]:
                try: doc_date = datetime.date.fromisoformat(extracted["doc_date"])
                except: pass

            # Parse Amounts
            def to_decimal(val: Any) -> Optional[Decimal]:
                """Safe conversion to Decimal."""
                if val is not None:
                    try:
                        return Decimal(str(val))
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pass
                return None

            # 2. Build Result Object
            result = AIAnalysisResult(
                doc_date=doc_date,
                amount=to_decimal(extracted["amount"]),
                gross_amount=to_decimal(extracted["gross_amount"]),
                sender=extracted["sender"],
                doc_type=str(extracted["doc_type"]) if extracted["doc_type"] else None,
                semantic_data=semantic_data
            )

            # Phase 80: Backfill Summary for Indexing
            if "summary" not in semantic_data:
                semantic_data["summary"] = {}

            summ = semantic_data["summary"]
            if extracted["amount"]:
                summ["amount"] = str(extracted["amount"])
            if extracted["gross_amount"]:
                summ["gross_amount"] = str(extracted["gross_amount"])
            if extracted["sender"]:
                summ["sender_name"] = extracted["sender"]

            return result

        except Exception as e:
            print(f"CRITICAL AI Analysis Error (Logic): {e}")
            import traceback
            traceback.print_exc()
            return AIAnalysisResult()
    def identify_entities(self, text: str, semantic_data: Optional[Dict[str, Any]] = None, detected_entities: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Phase 1.2 of Canonization: Identifies distinct documents within a file.
        Uses semantic_data if available for refinement, otherwise falls back to text analysis.

        Args:
            text: The full text of the document.
            semantic_data: Optional previous semantic analysis data.
            detected_entities: Optional list of previously detected entities.

        Returns:
            A list of dictionaries representing identified logical entities.
        """
        if semantic_data and isinstance(semantic_data, dict) and "pages" in semantic_data:
            print("[AIAnalyzer] Using Semantic JSON for Entity Identification (Refinement Mode)")
            return self.refine_semantic_entities(semantic_data)

        # Legacy / Fallback Mode (Raw Text)
        return self._identify_entities_legacy(text, semantic_data, detected_entities)

    def refine_semantic_entities(self, semantic_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Analyzes the Semantic JSON structure to identify Logical Entities.

        Args:
            semantic_data: The semantic analysis dictionary.

        Returns:
            A list of dictionaries representing logical entities.
        """
        # 1. Extract Existing Type Hints
        existing_types_str = "OTHER"
        summary = semantic_data.get("summary", {})
        if "doc_type" in summary:
            dt = summary["doc_type"]
            if isinstance(dt, list):
                existing_types_str = ", ".join(dt)
            else:
                existing_types_str = str(dt)

        # 2. Serialize semantic_data
        json_str = json.dumps(semantic_data, ensure_ascii=False)

        prompt = f"""
        You are a Semantic Document Architect.
        Transform Physical Page Structure into Logical Document Structure.

        ### EXISTING ANALYSIS
        Detected Types: {existing_types_str}.

        ### INPUT (Physical Structure)
        {json_str}

        ### TASK
        1. Identify Logical Document Boundaries (Start/End Pages).
        2. MERGE content that spans multiple pages.

        ### OUTPUT
        Return a JSON LIST of Logical Entities:
        [
          {{
            "type": "INVOICE",
            "pages": [1, 2, 3],
            "confidence": 0.99,
            "hints": "..."
          }}
        ]
        """

        try:
            result = self._generate_json(prompt, stage_label="STAGE 1.2 REFINEMENT")
            self._print_debug_prompt("REFINEMENT REQUEST", prompt)

            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "entities" in result:
                return result["entities"]
            return []
        except Exception as e:
            print(f"[Refinement] Failed: {e}")
            return []

    def _identify_entities_legacy(self, text: str, semantic_data: dict = None, detected_entities: List[dict] = None) -> List[dict]:
        # ... (Original identify_entities logic mooved here) ...
        if not text: return []

        # Build hints from semantic data or previous stage
        structural_hints = ""
        if detected_entities:
             doc_types = [str(t) for t in (ent.get("doc_type") for ent in detected_entities) if t]
             structural_hints = f"\n### PREVIOUS ANALYSIS HINTS\nThe classification stage (Stage 1.1) already identified these types: {', '.join(doc_types)}.\n"
             structural_hints += "Ensure the output contains boundaries for these documents.\n"
        elif semantic_data:
             summary = semantic_data.get("summary", {})
             doc_types = summary.get("doc_type", [])
             if isinstance(doc_types, list) and doc_types:
                 doc_types = [str(t) for t in doc_types if t]
                 structural_hints = f"\n### PREVIOUS ANALYSIS HINTS\nThe system previously detected the following Semantic Types: {', '.join(doc_types)}.\nUse this to guide your splitting."

        # Strict List allowed by system (Hybrid DMS)
        allowed_types = [
            "QUOTE", "ORDER", "ORDER_CONFIRMATION", "DELIVERY_NOTE", "INVOICE", "CREDIT_NOTE", "RECEIPT", "DUNNING",
            "BANK_STATEMENT", "TAX_ASSESSMENT", "EXPENSE_REPORT", "UTILITY_BILL",
            "CONTRACT", "INSURANCE_POLICY", "PAYSLIP", "LEGAL_CORRESPONDENCE", "OFFICIAL_LETTER",
            "CERTIFICATE", "MEDICAL_DOCUMENT", "VEHICLE_REGISTRATION", "APPLICATION", "NOTE", "OTHER"
        ]

        prompt = f"""
        You are a Document Structure Analyzer.
        Your goal is to split a file into logical documents (Entities) based on content and layout structure.

        ### INPUT TEXT
        (The text may cover multiple pages. Page markers look like '--- Page X ---' if present, or implied stream.)
        {structural_hints}

        ### TASK
        Analyze the text structure to identify distinct documents.
        1. Identify the boundaries (start/end pages) of each logical document.
        2. Assign one of the ALLOWED TYPES to each document.

        ### ALLOWED TYPES
        {", ".join(allowed_types)}
        (If uncertain, use OFFICIAL_CORRESPONDENCE or OTHER only as last resort)

        ### OUTPUT
        Return a JSON LIST of objects:
        [
          {{
            "type": "INVOICE", // Must be one of the allowed types
            "pages": [1, 2],
            "confidence": 0.95
          }}
        ]
        """

        # Append Text (Truncate if huge? Gemini 2.0 Flash has 1M context, usually fine)
        prompt += f"\n\n### TEXT CONTENT:\n{text[:100000]}"

        try:
            result = self._generate_json(prompt, stage_label="STAGE 1.2 SPLIT REQUEST")
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "entities" in result:
                return result["entities"]
            return []
        except Exception as e:
            print(f"Entity ID Failed: {e}")
            return []

    def extract_canonical_data(self, doc_type: Any, text: str) -> Dict[str, Any]:
        """
        Phase 2 of Canonization: Extract strict CDM for a specific Entity Type.
        Dynamically builds the target schema based on the Pydantic model.

        Args:
            doc_type: The document type (string or DocType enum).
            text: The text content of the entity.

        Returns:
            A dictionary containing the extracted canonical data.
        """
        # Ensure DocType Enum
        if isinstance(doc_type, str):
            try:
                doc_type = DocType(doc_type)
            except (ValueError, KeyError):
                pass  # Keep as string if custom, but mapping won't work

        # 1. Select the appropriate Specific Data Model
        model_map = {
            # Trade
            DocType.INVOICE: InvoiceData,
            DocType.CREDIT_NOTE: InvoiceData,
            DocType.ORDER: InvoiceData,
            DocType.QUOTE: InvoiceData,
            DocType.ORDER_CONFIRMATION: InvoiceData,
            DocType.DELIVERY_NOTE: LogisticsData,
            DocType.RECEIPT: InvoiceData,
            DocType.DUNNING: InvoiceData,

            # Finance
            DocType.BANK_STATEMENT: BankStatementData,
            DocType.TAX_ASSESSMENT: TaxAssessmentData,
            DocType.EXPENSE_REPORT: ExpenseData,
            DocType.UTILITY_BILL: UtilityData,

            # Legal & HR
            DocType.CONTRACT: ContractData,
            DocType.INSURANCE_POLICY: InsuranceData,
            DocType.OFFICIAL_LETTER: LegalMetaData,
            DocType.LEGAL_CORRESPONDENCE: LegalMetaData,

            # Misc
            DocType.VEHICLE_REGISTRATION: VehicleData,
            DocType.MEDICAL_DOCUMENT: MedicalData,
            # FALLBACK
            DocType.OTHER: None
        }

        target_model = model_map.get(doc_type)
        val = doc_type.value if hasattr(doc_type, 'value') else str(doc_type)

        # Build Schema Strings
        specific_schema_hint = ""
        if target_model:
            # Generate JSON Schema for the specific block
            try:
                schema = target_model.model_json_schema()
                props = schema.get("properties", {})
                # Format clearly for LLM
                field_list = []
                for k, v in props.items():
                    ftype = v.get("type", "string")
                    desc = v.get("title", "") # Pydantic uses title/desc
                    field_list.append(f'"{k}": "{ftype}"')

                joined_fields = ",\n               ".join(field_list)
                specific_schema_hint = f"""
          "specific_data": {{
               // Fields for {val}:
               {joined_fields}
          }},"""
            except Exception as e:
                print(f"[AI] Error generating schema hint for {val}: {e}")

        prompt = f"""
        You are a Specialized Data Extractor for: {val}.

        ### TARGET SCHEMA (Canonical Data Model)
        Extract data into this exact JSON structure:

        {{
          "doc_type": "{val}",
          "doc_date": "YYYY-MM-DD",
          "parties": {{
            "sender": {{ "name": "...", "address": "...", "id": "...", "company": "...", "street": "...", "zip_code": "...", "city": "...", "country": "..." }},
            "recipient": {{ "name": "...", "address": "...", "id": "..." }}
          }},
          "tags_and_flags": ["String"],
          {specific_schema_hint}

          "list_data": [
             // Any recurring items (Line Items, Transactions, etc.)
             {{ "pos": 1, "description": "...", "amount": 0.0, "quantity": 0, "date": "..." }}
          ]
        }}

        ### RULES
        - Use ISO Dates (YYYY-MM-DD). Format: "2023-12-31".
        - Use Floats for money (e.g. 10.50), NOT strings.
        - Null handling: Use null for missing fields, do NOT use "n/a" or "unknown".
        - Extract ALL line items if possible.
        - Strict JSON: Do not include comments or "..." placeholders in the final output.

        ### TEXT CONTENT
        {text[:100000]}
        """

        self._print_debug_prompt("STAGE 2 EXTRACTION REQUEST", prompt)

        try:
            raw_data = self._generate_json(prompt) or {}

            # Phase 94 Validation Logic
            if target_model and "specific_data" in raw_data:
                # Merge top-level fields into specific_data if model implies flat structure?
                # Actually CanonicalEntity separates `specific_data`.
                # Let's try to validate the SPECIFIC part using target_model
                try:
                    # target_model expects the full structure?
                    # No, target_model (e.g. InvoiceData) is the Specific Data block or the Full Entity?
                    # Looking at canonical_entity.py: `class InvoiceData(BaseModel)`
                    # `class CanonicalEntity(BaseModel): ... specific_data: Optional[Union[InvoiceData...]]`

                    # So we should validate the inner part?
                    spec_data = raw_data.get("specific_data", {})
                    if spec_data:
                         validated_spec = target_model(**spec_data)
                         raw_data["specific_data"] = validated_spec.model_dump()
                except Exception as e:
                    print(f"Validation Warning (Specific): {e}")
                    # Fallback: keep raw or clear? Keep raw for now.

            # TODO: Validate the outer `CanonicalEntity` too?
            # Creating a transient CanonicalEntity to coerce top-level fields (doc_date, etc.)
            try:
                # We need to handle 'doc_type' conversion string -> Enum
                if "doc_type" in raw_data and isinstance(raw_data["doc_type"], str):
                     # If it matches enum
                     try:
                         # Ensure it's uppercase
                         raw_data["doc_type"] = raw_data["doc_type"].upper()
                     except: pass

                # Attempt full validation if possible, or just coercion of known fields
                # For now, let's minimally coerce 'total_amount' if it sits in specific_data or root?
                # The prompt asks for `specific_data`.
                pass
            except Exception as e:
                print(f"[AI] Post-processing of CDM failed: {e}")

            return raw_data
        except Exception as e:
            print(f"CDM Extraction Failed: {e}")
            return {}

    def parse_identity_signature(self, text: str) -> Optional[IdentityProfile]:
        """
        Phase 101: Analyze signature text to extract structured IdentityProfile.
        """
        prompt = f"""
        You are a Settings Assistant.
        Extract user identity data from the provided signature/imprint text.

        ### TARGET JSON SCHEMA
        {{
          "name": "String (Official Person Name or Main Entity Name)",
          "aliases": ["String", "String"], // Variations of the name

          "company_name": "String (Official Company Name, e.g. 'ACME GmbH')",
          "company_aliases": ["String"], // e.g. 'ACME', 'ACME Germany'

          "address_keywords": ["String", "String"], // City, Street, Zip (atomic parts)
          "vat_id": "String (or null)",
          "iban": ["String"] // List of IBANs found
        }}

        ### RULES
        - **Company:** If a company is mentioned (e.g. 'GmbH', 'Inc'), extract it specifically into `company_name`.
        - **Aliases:** Generate plausible variations if not explicitly stated (e.g. if Name is "Thomas Müller", Alias could be "T. Müller").
        - **Address Keywords:** Do NOT return the full address string. Return the unique parts (Streetname, Zip, City) as a list for fuzzy matching later.
        - **VAT/IBAN:** Extract strictly.

        ### INPUT TEXT
        {text}
        """

        try:
            result = self._generate_json(prompt, stage_label="IDENTITY PARSE REQUEST")
            if not result:
                return None

            # Convert to Pydantic Model
            return IdentityProfile(
                name=result.get("name"),
                aliases=result.get("aliases", []),
                company_name=result.get("company_name"),
                company_aliases=result.get("company_aliases", []),
                address_keywords=result.get("address_keywords", []),
                vat_id=result.get("vat_id"),
                iban=result.get("iban", [])
            )
        except Exception as e:
            print(f"Identity Parsing Failed: {e}")
            return None

    def classify_structure(self, pages_text: List[str],
                          private_id: Optional[IdentityProfile],
                          business_id: Optional[IdentityProfile],
                          mode: str = "FULL_READ_MODE") -> Dict[str, Any]:
        """
        Phase 102: Master Classification Step.
        Uses 'Sandwich' input (First/Last Page) or full page list based on mode.
        """
        if not pages_text:
            print("[DEBUG] classify_structure called with empty pages_text!")
            return {}

        print(f"[DEBUG] classify_structure scanning {len(pages_text)} pages...")

        # 1. Build Analysis Text (Based on Mode and available pages)
        analysis_parts = []
        for i, text in enumerate(pages_text):
            # If in SANDWICH_MODE, the input pages_text is already pruned.
            # But the labels might be wrong if we don't know the original indices.
            # For simplicity, if mode is SANDWICH_MODE, we assume pages_text[0-2] are start, and pages_text[-1] is end.

            p_num = i + 1
            if mode == "SANDWICH_MODE" and i == len(pages_text) - 1 and len(pages_text) > 3:
                 # It's the last page of a large document
                 analysis_parts.append("\n... (INTERMEDIATE PAGES OMITTED) ...\n")

            analysis_parts.append(f"--- PAGE {p_num} ---")
            analysis_parts.append(text)

        analysis_text = "\n".join(analysis_parts)

        # 2. Build Prompt Context
        def fmt_id(p: Optional[IdentityProfile]):
            if not p: return "None"
            return f"Name: {p.name}, Aliases: {p.aliases}, Company: {p.company_name}, VAT: {p.vat_id}, Address: {p.address_keywords}"

        # 3. Construct System Prompt
        # 3. Construct System Prompt
        # Prepare Identity JSON for prompt
        identity_json = {
            "PRIVATE_IDENTITY": private_id.model_dump() if private_id else {},
            "BUSINESS_IDENTITY": business_id.model_dump() if business_id else {}
        }
        identity_json_str = json.dumps(identity_json, indent=2)

        prompt = f"""
=== [SYSTEM INSTRUCTION] ===

You are an expert Document Structure Analyzer & Splitter for a hybrid DMS.
Your task is to analyze the input text and identify ALL distinct logical document types contained within it.

### 1. CONTEXT: USER IDENTITIES
Use the following JSON to determine the `direction` (INBOUND/OUTBOUND) and `tenant_context` for EACH detected document.

{identity_json_str}

### 2. SCAN MODE CONTEXT
Current Scan Mode: {mode}
(If 'SANDWICH_MODE': Assume missing pages belong to the same entity. If 'HEADER_SCAN_MODE': Rely on headers/logos.)

### 3. CRITICAL ANALYSIS RULES
1. **Segmentation (Full Coverage):**
   - Identify the exact `page_indices` for each logical document based on the `--- PAGE X ---` markers.
   - **Do NOT orphan pages:** If a document says "Page 1 of 3", you MUST include pages 1, 2, and 3.

2. **Identity Disambiguation (BILLING vs. DELIVERY):**
   - **HIERARCHY RULE:** The **BILLING ADDRESS** (usually top-left or under "Invoice to") is the SOLE decider for the `tenant_context`.
   - **IGNORE** the Delivery Address (Lieferadresse) for context determination.
   - **Scenario:** Invoice billed to "Private Person" (Home Address) but delivered to "Company Office" (Work Address) -> Context is **PRIVATE**.
   - **Scenario:** Invoice billed to "Company Corp" -> Context is **BUSINESS**.

3. **Hybrid Documents (Tagging):**
   - If a single logical document serves multiple purposes (e.g. "Invoice & Delivery Note" or "Invoice & Certificate of Compliance"), assign **MULTIPLE** tags to that entity. 
   - **BE EAGLE-EYED:** Check the absolute end of the document text for secondary titles like "Certificate", "Compliance Statement", or "Anhang".

4. **Differentiation: INVOICE vs. DELIVERY_NOTE:**
   - **Rule:** Do NOT apply the tag "DELIVERY_NOTE" merely because items are listed.
   - **Condition:** Only apply "DELIVERY_NOTE" if the title explicitly says "Lieferschein" OR if it is a pure packing list without prices.

5. **Direction Logic:**
   - **INBOUND:** User Identity is in the **RECIPIENT** area OR sender is a third party.
   - **OUTBOUND:** User Identity is in the **SENDER/HEADER** area.
   - **INTERNAL:** User Identity is both Sender and Recipient.

### 4. ALLOWED DOCTYPES
[
  "QUOTE", "ORDER", "ORDER_CONFIRMATION", "DELIVERY_NOTE", "INVOICE", "CREDIT_NOTE", "RECEIPT",
  "DUNNING", "PAYSLIP", "SICK_NOTE", "EXPENSE_REPORT", "BANK_STATEMENT", "TAX_ASSESSMENT",
  "CONTRACT", "INSURANCE_POLICY", "OFFICIAL_LETTER", "TECHNICAL_DOC", "CERTIFICATE",
  "APPLICATION", "NOTE", "OTHER"
]

### 5. OUTPUT SCHEMA (JSON)
Return ONLY a valid JSON object.

{{
  "source_file_summary": {{
    "primary_language": "en | de | ..."
  }},
  "detected_entities": [
    {{
      "doc_types": ["INVOICE"],
      "page_indices": [1],
      "direction": "INBOUND | OUTBOUND | INTERNAL | UNKNOWN",
      "tenant_context": "PRIVATE | BUSINESS | UNKNOWN",
      "confidence": 0.99
    }}
  ]
}}

=== [USER INPUT] ===

### DOCUMENT CONTENT (with Page Markers):
{analysis_text}
"""

        try:
            # --- START VALIDATOR LOOP ---
            max_retries = 2
            attempt = 0
            chat_history = []

            # Initial Call
            result = self._generate_json(prompt, stage_label="Stage 1.1 (Classification)")

            while attempt < max_retries:
                if not result: break

                # Validation
                errors = self.validate_classification(result, pages_text, private_id, business_id)
                if not errors:
                    return result

                # Correction Required
                print(f"[AIAnalyzer] Stage 1.1 Validation Failed (Attempt {attempt+1}): {errors}")
                attempt += 1

                error_msg = "\n".join(f"- {e}" for e in errors)
                correction_prompt = f"""
### ⚠️ VALIDATION FAILED ⚠️
Your previous analysis contained logical errors:
{error_msg}

TASK:
1. Review the Input Text again strictly.
2. Fix the errors mentioned above (ensure all pages are covered and context is correct).
3. Return the COMPLETE corrected JSON.
"""
                # We use chat history for correction if the API supports it,
                # or just append the correction to a new prompt if stateless.
                # Since _generate_json is stateless per call, we append.
                # Actually, for Gemini we can pass contents.

                # Simple stateless approach: append correction to original prompt
                # (since _generate_json doesn't handle history yet)
                prompt_with_history = prompt + f"\n\n### PREVIOUS ATTEMPT ###\n{json.dumps(result)}\n\n{correction_prompt}"
                result = self._generate_json(prompt_with_history, stage_label=f"STAGE 1.1 CORRECTION {attempt}")

            return result or {}
        except Exception as e:
            print(f"Classification Failed: {e}")
            return {}

    def validate_classification(self, result: dict, ocr_pages: List[str], priv_id=None, bus_id=None) -> List[str]:
        """Validates AI response for logical errors (Orphan pages, Context insanity)."""
        from core.validators import validate_ai_structure_response

        errors = []
        entities = result.get("detected_entities", [])
        total_pages = len(ocr_pages)

        # 1. Orphan Page Check
        claimed_pages = set()
        for ent in entities:
             claimed_pages.update(ent.get("page_indices", []))

        if len(claimed_pages) < total_pages:
             missing = set(range(1, total_pages + 1)) - claimed_pages
             errors.append(f"SEGMENTATION_ERROR: Missing pages {sorted(list(missing))}. Every page must be assigned to an entity.")

        # 2. Context Sanity Check (Fuzzy)
        fuzzy_errors = validate_ai_structure_response(result, ocr_pages, priv_id, bus_id)
        errors.extend(fuzzy_errors)

        return errors

    def _generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        """
        High-level helper that handles both API retries and logical JSON retries.
        If JSON is malformed or truncated, it tries a second time with a hint.

        Args:
            prompt: The text prompt.
            stage_label: A label for debugging purposes.
            images: Optional images to include in the request.

        Returns:
            The parsed JSON result or None if it fails.
        """
        max_logical_retries = 5
        current_attempt = 1
        last_error = None
        working_prompt = prompt

        while current_attempt <= max_logical_retries:
            if last_error:
                # Strengthen prompt on retry
                working_prompt = prompt + f"\n\n### PREVIOUS ATTEMPT FAILED WITH ERROR:\n{last_error}\n\nPLEASE FIX THE JSON STRUCTURE! Ensure all braces are closed, no trailing commas, and strictly follow the schema."
                self._print_debug_prompt(f"{stage_label} RETRY {current_attempt}", working_prompt)

            res, error_msg = self._generate_json_raw(working_prompt, stage_label, images)
            if res is not None:
                return res
            
            last_error = error_msg

            if current_attempt < max_logical_retries:
                print(f"[AI] Logical Retry {current_attempt}/{max_logical_retries} for {stage_label} due to JSON/Validation Error.")
                current_attempt += 1
                time.sleep(1)
            else:
                break

        return None

    def _generate_json_raw(self, prompt: str, stage_label: str = "AI REQUEST", images=None) -> Tuple[Optional[Any], Optional[str]]:
        """Internal helper to call Gemini and perform repair-based parsing."""
        # self._print_debug_prompt(stage_label, prompt) # Moved to high level if needed

        contents = [prompt]
        if images:
            if isinstance(images, list):
                contents.extend(images)
            else:
                contents.append(images)

        # Force JSON via API if supported
        full_payload = {
            'contents': contents,
            'config': types.GenerateContentConfig(
                response_mime_type='application/json',
                max_output_tokens=self.max_output_tokens,
                temperature=0.1 # Low temperature for strict extraction
            )
        }

        response = self._generate_with_retry(full_payload)

        if not response or not response.candidates:
            return None, "No response from API"
            
        candidate = response.candidates[0]
        is_truncated = candidate.finish_reason == "MAX_TOKENS"
        
        if is_truncated:
            print(f"⚠️ [AI] WARNING: Response for {stage_label} was TRUNCATED due to output token limit!")
        elif candidate.finish_reason != "STOP" and candidate.finish_reason is not None:
             print(f"⚠️ [AI] WARNING: Response for {stage_label} finished with reason: {candidate.finish_reason}")

        try:
            txt = response.text
        except Exception as e:
            print(f"[AI] Error: Could not access response text: {e}")
            return None, f"Could not access response text: {e}"

        # Clean control characters (null bytes, etc.) that break JSON
        txt = txt.replace("\x00", "") 

        # Robust JSON extraction: Find the first '{' 
        start = txt.find('{')
        if start == -1: return None, "No JSON object found (missing '{')"

        def attempt_repair(s: str) -> str:
            """Heuristic JSON repair for common AI mistakes."""
            # 1. Remove trailing commas before closing braces/brackets
            s = re.sub(r',\s*([\]}])', r'\1', s)
            # 2. Fix missing commas between fields: "}\s*\n\s*\"" -> "},\n\""
            s = re.sub(r'}\s*\n\s*"', r'},\n"', s)
            s = re.sub(r'\]\s*\n\s*"', r'],\n"', s)
            return s

        try:
            res_json = None
            current_json = None
            
            # Tiered Parse Attempt
            for step in range(4):
                try:
                    if step == 0:
                        # Attempt 0: Find last '}'
                        end = txt.rfind('}')
                        if end == -1: continue
                        current_json = txt[start:end+1]
                    elif step == 1:
                        # Attempt 1: Balanced Braces (Ignore trailing text)
                        depth = 0
                        balanced_end = -1
                        for idx, char in enumerate(txt[start:]):
                            if char == '{': depth += 1
                            elif char == '}': 
                                depth -= 1
                                if depth == 0:
                                    balanced_end = start + idx
                                    break
                        if balanced_end != -1:
                            current_json = txt[start:balanced_end+1]
                        else: continue
                    elif step == 2:
                        # Attempt 2: Heuristic Repair
                        if not current_json: continue
                        current_json = attempt_repair(current_json)
                    elif step == 3:
                        # Attempt 3: Try to fix truncated JSON by adding closing braces
                        if not current_json: continue
                        depth = 0
                        for char in current_json:
                            if char == '{': depth += 1
                            elif char == '}': depth -= 1
                        if depth > 0:
                             current_json += ("}" * depth)
                        else: continue

                    if not current_json: continue
                    res_json = json.loads(current_json, strict=False)
                    break 
                except json.JSONDecodeError as e:
                    if step < 3: continue 
                    
                    line_no = getattr(e, 'lineno', 0)
                    col_no = getattr(e, 'colno', 0)
                    print(f"[AI] JSON Syntax Error at L{line_no},C{col_no} for {stage_label}")
                    raise e
            
            if res_json is not None:
                # NEW: Debug Output for AI Response (Requested for Stage 1.5+)
                print(f"\n=== [AI RESPONSE: {stage_label}] ===\n{json.dumps(res_json, indent=2, ensure_ascii=False)}\n==============================\n")
                
                # Phase 107: Strict Truncation Handling
                # If the AI response was truncated, the data is incomplete.
                # Even if we "repaired" the JSON structure, significant content is missing.
                if is_truncated:
                    print(f"[AI] Response for {stage_label} was truncated. Treating as None to trigger potential retry.")
                    return None, "Response truncated (max tokens reached)"
                return res_json, None
            else:
                return None, "JSON parsing failed after all repair attempts"
        except Exception as e:
            # Propagate the syntax error details
            err_msg = f"JSON Syntax Error: {e}"
            print(f"[AI] Failed to parse JSON for {stage_label}: {e}")
            if hasattr(e, 'lineno'):
                 print(f"[AI] Syntax Detail: Line {e.lineno}, Col {e.colno}")
            
            if hasattr(e, 'pos') and current_json:
                err_pos = e.pos
                snippet = current_json[max(0, err_pos-40):min(len(current_json), err_pos+40)]
                print(f"[AI] Error Context: ... {snippet} ...")
                err_msg += f" (Near: ... {snippet} ...)"

            return None, err_msg

    def _generate_json_raw_legacy(self, prompt: str, stage_label: str = "AI REQUEST", images=None) -> Any:
        # Keeping a wrapper just in case other things call it and expect old return type
        res, err = self._generate_json_raw(prompt, stage_label, images)
        return res

    # ==============================================================================
    # STAGE 2: SCHEMA HELPERS (Reusable Components)
    # ==============================================================================

    @staticmethod
    def get_address_schema() -> Dict:
        return {
            "raw_string": "String (Full address line as fallback)",
            "street": "String",
            "house_number": "String",
            "zip_code": "String",
            "city": "String",
            "state_province": "String",
            "country": "String (ISO Code if possible, e.g. DE)"
        }

    @staticmethod
    def get_contact_schema() -> Dict:
        return {
            "phones": ["String (List of phone numbers)"],
            "emails": ["String (List of email addresses)"],
            "websites": ["String (List of URLs)"],
            "contact_person": "String (Name of specific person)"
        }

    @classmethod
    def get_party_schema(cls) -> Dict:
        """Detailed structure for Sender/Recipient."""
        return {
            "name": "String (Official Company Name or Person Name)",
            "address": cls.get_address_schema(),
            "contact": cls.get_contact_schema(),
            "identifiers": {
                "vat_id": "String (USt-IdNr)",
                "tax_id": "String (Steuernummer)",
                "commercial_register": "String (HRB/HRA Number + Court)",
                "customer_id": "String (My ID at this company)",
                "creditor_id": "String (Gläubiger-ID)",
                "personnel_number": "String (Personalnummer)",
                "insurance_id": "String (Versichertennummer)"
            }
        }

    @staticmethod
    def get_bank_account_schema() -> Dict:
        return {
            "bank_name": "String",
            "account_holder": "String",
            "iban": "String",
            "bic": "String",
            "sort_code": "String (BLZ - optional)"
        }

    # ==============================================================================
    # STAGE 2: SCHEMA REGISTRY
    # ==============================================================================

    def get_target_schema(self, doc_type: str, include_repair: bool = True) -> Dict:
        """
        Phase 2.1: Schema Registry.
        Detailed polymorph schemas for each document type.
        """
        dt = doc_type.upper()
        
        # BASIS: Common Header (immer dabei)
        base_header = {
            "doc_date": "YYYY-MM-DD (Date written on document)",
            "summary": "String (1 sentence content summary)",
            
            # Granular Parties
            "sender": self.get_party_schema(),
            "recipient": self.get_party_schema(),
            
            # Life Context
            "subject_context": {
                "entity_name": "String (e.g. 'Sommerurlaub 2025', 'Lego Set', 'Python Kurs', 'Wintermantel')",
                "entity_type": "SELF | FAMILY | PET | ASSET | PROPERTY | VEHICLE | HOBBY | PROJECT | BUSINESS | HEALTH | HOLIDAY | JOURNEY | FOOD | TOY | DEVICE | DEVELOPMENT | SERVICE | CLOTHING | CLEANING | COSMETIC | GIFT | OTHER",
                "relation": "String (e.g. 'Owner', 'Participant', 'Consumer', 'Buyer')"
            }
        }

        # --- GROUP 1: FINANCE & TRANSACTIONAL ---
        if dt in ["INVOICE", "RECEIPT", "CREDIT_NOTE", "CASH_EXPENSE"]:
            schema = {
                "meta_header": base_header,
                "finance_body": {
                    "invoice_number": "String",
                    "order_number": "String",
                    "total_net": "Number (Float)",
                    "total_tax": "Number (Float)",
                    "total_gross": "Number (Float)",
                    "currency": "EUR | USD | ...",
                    
                    # Detailed Bank Info
                    "payment_accounts": [self.get_bank_account_schema()],
                    
                    "payment_details": {
                        "reference": "String (Verwendungszweck)",
                        "due_date": "YYYY-MM-DD",
                        "payment_terms": "String (e.g. '14 days net')"
                    },
                    
                    "line_items": [
                        {
                            "pos_no": "String",
                            "description": "String",
                            "article_id": "String (SKU/EAN)",
                            "quantity": "Number",
                            "unit": "String (pcs, kg, h)",
                            "unit_price": "Number",
                            "tax_rate": "Number",
                            "total_price": "Number"
                        }
                    ]
                }
            }

        elif dt == "DUNNING":
            schema = {
                "meta_header": base_header,
                "finance_body": {
                    "total_due": "Number (Float)",
                    "dunning_level": "String (e.g. '1. Mahnung')",
                    "original_invoice_ref": "String",
                    "fees": "Number",
                    "deadline": "YYYY-MM-DD",
                    "payment_accounts": [self.get_bank_account_schema()]
                }
            }

        # --- GROUP 2: TRADE & COMMERCE ---
        elif dt in ["QUOTE", "ORDER", "ORDER_CONFIRMATION"]:
            schema = {
                "meta_header": base_header,
                "trade_body": {
                    "document_number": "String (Offer/Order No)",
                    "valid_until": "YYYY-MM-DD",
                    "total_amount": "Number",
                    "terms_of_payment": "String",
                    "line_items": [
                        {
                            "pos_no": "String",
                            "description": "String",
                            "article_id": "String",
                            "quantity": "Number",
                            "unit_price": "Number",
                            "total_price": "Number"
                        }
                    ]
                }
            }
            
        elif dt == "DELIVERY_NOTE":
            schema = {
                "meta_header": base_header,
                "logistics_body": {
                    "delivery_number": "String",
                    "order_reference": "String",
                    "shipping_date": "YYYY-MM-DD",
                    "carrier": "String",
                    "tracking_number": "String",
                    "weight_kg": "Number",
                    "delivered_items": [
                        {
                            "pos_no": "String",
                            "description": "String",
                            "article_id": "String",
                            "quantity_ordered": "Number",
                            "quantity_delivered": "Number",
                            "unit": "String"
                        }
                    ]
                }
            }

        # --- GROUP 3: CONTRACTS & LEGAL ---
        elif dt in ["CONTRACT", "INSURANCE_POLICY", "APPLICATION"]:
            schema = {
                "meta_header": base_header,
                "legal_body": {
                    "contract_id": "String",
                    "contract_partners": [self.get_party_schema()], 
                    "start_date": "YYYY-MM-DD",
                    "end_date": "YYYY-MM-DD | null (if indefinite)",
                    "cancellation_period": "String (e.g. '3 months to year end')",
                    "renewal_clause": "String",
                    "cost_recurring": {
                        "amount": "Number",
                        "interval": "MONTHLY | YEARLY | QUARTERLY"
                    }
                },
                "verification": {
                     "is_signed": "Boolean (from Visual Audit)"
                }
            }

        elif dt in ["LEGAL_CORRESPONDENCE", "OFFICIAL_LETTER"]:
            schema = {
                "meta_header": base_header,
                "legal_body": {
                    "our_reference": "String (Unser Zeichen)",
                    "your_reference": "String (Ihr Zeichen/Aktenzeichen)",
                    "subject": "String",
                    "court_file_number": "String (Aktenzeichen Gericht)",
                    "deadlines": [{"reason": "String", "date": "YYYY-MM-DD"}]
                }
            }

        # --- GROUP 4: HR & HEALTH ---
        elif dt == "PAYSLIP":
            schema = {
                "meta_header": base_header,
                "hr_body": {
                    "employee_id": "String",
                    "period": "YYYY-MM",
                    "net_salary": "Number",
                    "gross_salary": "Number",
                    "payout_date": "YYYY-MM-DD",
                    "tax_class": "String",
                    "social_security_id": "String"
                }
            }

        elif dt in ["SICK_NOTE", "MEDICAL_DOCUMENT"]:
            schema = {
                "meta_header": base_header,
                "health_body": {
                    "patient": self.get_party_schema(),
                    "provider": self.get_party_schema(), # Doctor/Clinic
                    "type": "INITIAL | FOLLOW_UP | PRESCRIPTION | LETTER",
                    "incapacity_period": {
                        "start": "YYYY-MM-DD",
                        "end": "YYYY-MM-DD",
                        "estimated_return": "YYYY-MM-DD"
                    },
                    "insurance_provider": "String",
                    "diagnoses_icd": [
                        {
                            "icd_code": "String (e.g. J06.9)",
                            "description": "String",
                            "certainty": "String"
                        }
                    ],
                    "medication_plan": [
                        {
                            "name": "String",
                            "pzn": "String",
                            "dosage": "String",
                            "form": "String",
                            "instructions": "String",
                            "prescribed_amount": "String"
                        }
                    ]
                }
            }

        # --- GROUP 5: TRAVEL ---
        elif dt in ["TRAVEL_REQUEST", "EXPENSE_REPORT"]:
            schema = {
                "meta_header": base_header,
                "travel_body": {
                    "traveler": self.get_party_schema(),
                    "destination": "String",
                    "start_date": "YYYY-MM-DD",
                    "end_date": "YYYY-MM-DD",
                    "total_cost": "Number",
                    "expenses": [
                        {
                            "date": "YYYY-MM-DD",
                            "category": "String (Hotel, Meal, Transport)",
                            "description": "String",
                            "amount": "Number",
                            "currency": "String"
                        }
                    ]
                }
            }

        # --- GROUP 6: BANKING & TAX ---
        elif dt == "BANK_STATEMENT":
            schema = {
                "meta_header": base_header,
                "ledger_body": {
                    "account_info": self.get_bank_account_schema(),
                    "statement_number": "String",
                    "period_start": "YYYY-MM-DD",
                    "period_end": "YYYY-MM-DD",
                    "start_balance": "Number",
                    "end_balance": "Number",
                    "transactions": [
                        {
                            "date": "YYYY-MM-DD",
                            "counterparty_name": "String",
                            "description": "String",
                            "amount": "Number (negative for debit)",
                            "category": "String"
                        }
                    ]
                }
            }

        elif dt in ["TAX_ASSESSMENT", "UTILITY_BILL"]:
            schema = {
                "meta_header": base_header,
                "finance_body": {
                    "assessment_year": "YYYY",
                    "total_amount": "Number (Positive=Payment, Negative=Refund)",
                    "due_date": "YYYY-MM-DD",
                    "tax_id": "String"
                }
            }

        # --- GROUP 7: TECHNICAL & ASSETS ---
        elif dt == "VEHICLE_REGISTRATION":
            schema = {
                "meta_header": base_header,
                "asset_body": {
                    "vin": "String",
                    "license_plate": "String",
                    "vehicle_model": "String",
                    "manufacturer": "String",
                    "first_registration": "YYYY-MM-DD",
                    "owner": self.get_party_schema()
                }
            }

        elif dt in ["DATASHEET", "MANUAL", "TECHNICAL_DOC"]:
            schema = {
                "meta_header": base_header,
                "technical_body": {
                    "product_name": "String",
                    "model_number": "String",
                    "version": "String",
                    "manufacturer": "String",
                    "specs": [{"label": "String", "value": "String"}]
                }
            }

        elif dt == "CERTIFICATE":
            schema = {
                "meta_header": base_header,
                "career_body": {
                    "title": "String",
                    "issued_by": "String",
                    "recipient": "String",
                    "date_issued": "YYYY-MM-DD",
                    "grade": "String",
                    "expiry_date": "YYYY-MM-DD"
                }
            }

        # Fallback
        else:
            schema = {
                "meta_header": base_header,
                "generic_body": {
                    "subject": "String",
                    "keywords": ["String", "String"],
                    "content_summary": "String"
                }
            }

        # Ensure Common Root Fields
        if include_repair:
             schema["repaired_text"] = "String (The FULL, corrected, and plausible text of ALL pages. Use === PAGE X === separators.)"
        
        return schema

    def assemble_best_text_source(self, raw_ocr_pages: List[str], stage_1_5_result: Dict) -> str:
        """
        Phase 2.2: The Arbiter.
        Now simply joins the raw OCR pages to ensure structural consistency for pattern scanning.
        """
        # We use the pure RAW OCR for all pages.
        # This ensures the 'visual blueprint' from Page 1 matches the text pattern
        # on all subsequent raw OCR pages.
        
        optimized_pages = []
        for i, page_text in enumerate(raw_ocr_pages):
            optimized_pages.append(f"=== PAGE {i+1} (RAW OCR) ===\n{page_text}")

        return "\n\n".join(optimized_pages)

    def get_page_image_payload(self, pdf_path: str, page_index: int = 0) -> Optional[Dict]:
        """
        Renders a PDF page as a Base64 image for Vision AI.
        """
        try:
            doc = fitz.open(pdf_path)
            if page_index >= doc.page_count:
                doc.close()
                return None
            
            page = doc.load_page(page_index)
            # 200 DPI for better recognition
            pix = page.get_pixmap(dpi=200) 
            img_bytes = pix.tobytes("png")
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            
            doc.close()
            return {
                "base64": b64,
                "label": "FIRST_PAGE_VISUAL_CONTEXT",
                "page_index": page_index
            }
        except Exception as e:
            print(f"[Stage 2] Image generation failed: {e}")
            return None

    def run_stage_2(self, raw_ocr_pages: List[str], stage_1_result: Dict, stage_1_5_result: Dict, pdf_path: Optional[str] = None) -> Dict:
        """
        Phase 2.3: Semantic Extraction Pipeline.
        Executes extraction for each detected type and consolidates result.
        """
        # 1. Safety Net: Page Limit and Hybrid Repair Logic
        # Gemini's output limit is approx 8k tokens. 
        # We allow scanning up to 50 pages for semantic data, but only repair the first 10.
        MAX_PAGES_STAGE2 = 50
        is_long_document = len(raw_ocr_pages) > 10
        
        if len(raw_ocr_pages) > MAX_PAGES_STAGE2:
            print(f"[AI] Stage 2 -> WARNING: Document has {len(raw_ocr_pages)} pages. Truncating to {MAX_PAGES_STAGE2} for scanning.")
            raw_ocr_pages = raw_ocr_pages[:MAX_PAGES_STAGE2]

        # 2. Text Merging (Arbiter Logic)
        best_text = self.assemble_best_text_source(raw_ocr_pages, stage_1_5_result)

        # 2. Image Prep (Vision Support)
        images_payload = []
        if pdf_path:
            img_data = self.get_page_image_payload(pdf_path, 0)
            if img_data:
                # In Gemini API (genai), we need to convert base64 back to bytes or use a specific format
                # But _generate_json expect images as PIL or Dict? 
                # Let's check _generate_json implementation. It takes 'image'.
                # Actually, my _generate_with_retry takes 'contents'.
                
                # Use the already rendered image from get_page_image_payload
                try:
                    img_bytes = base64.b64decode(img_data["base64"])
                    images_payload.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
                    print("[AI] Stage 2 -> Vision context enabled (Page 1)")
                except Exception as e:
                    print(f"[AI] Stage 2 -> Vision prep failed: {e}")

        # 3. Extract Types
        detected_entities = stage_1_result.get("detected_entities", [])
        if not detected_entities:
            types_to_extract = stage_1_result.get("doc_types", ["OTHER"])
        else:
            primary = detected_entities[0]
            types_to_extract = primary.get("doc_types", ["OTHER"])

        types_to_extract = list(set([t for t in types_to_extract if t not in ["INBOUND", "OUTBOUND", "INTERNAL", "CTX_PRIVATE", "CTX_BUSINESS", "UNKNOWN"]]))
        if not types_to_extract:
            types_to_extract = ["OTHER"]

        # 4. Prepare Stamps
        stamps_list = []
        if stage_1_5_result:
            stamps_list = stage_1_5_result.get("layer_stamps", [])
        stamps_json_str = json.dumps(stamps_list, indent=2, ensure_ascii=False)

        # 5. Consolidated Result
        final_semantic_data = {
            "meta_header": {},
            "bodies": {},
            "repaired_text": ""
        }

        PROMPT_TEMPLATE = """
You are a 'Structural Pattern Interpreter' for document digitisation.
Your goal is to transform visual layout patterns into a page-independent, universal semantic JSON structure.

### 1. THE VISION BLUEPRINT (IMAGE of FIRST PAGE)
Analyze the image to find the **Geometric Master-Plan**:
- Locate where the 'Sender', 'Recipient', and 'Tables' are placed.
- Understand the **visual grammar**: How are table rows delimited in the raw source? Which columns contain what data?
- This visual blueprint is your KEY to interpreting the raw OCR text stream correctly.

### 2. MISSION: FULL-TEXT PATTERN SCANNING
Apply the blueprint found on Page 1 to the **ENTIRE RAW OCR TEXT** (all pages provided below):
- **Pattern Matching:** Search the raw OCR stream for content that matches the geometric structure from Page 1.
- **Consistency:** Use the image to 'calibrate' your reading of the raw OCR.
- **Table Expansion:** If a table continues on Page 2 or Page 3, use the identified layout from Page 1 to extract and append every single row into the semantic list.
- **Intelligent Repair:** If you detect obvious errors or noise in the raw OCR (e.g. 'St1ck' instead of 'Stick', or '1nd' instead of 'and'), especially on Page 1 where you have the image, use your visual and logical understanding to REPAIR the text and extract the CORRECT values.
{repair_mission}

### 3. INPUT DATA
**A. VISUAL CONTEXT:** (Image of Page 1)

**B. DOCUMENT TEXT (RAW OCR of ALL PAGES):**
{document_text}

**C. PRE-VERIFIED ANCHORS (STAMPS & SIGNATURES):**
These data points have ALREADY been processed and mapped to the system. 
>>> STAMPS: {stamps_json} <<<
>>> SIGNATURES: {signature_json} <<<
*Instruction:* STICKLY IGNORE these in your analysis. DO NOT re-extract them, DO NOT mention them in your summary or analysis. They are provided as context ONLY to avoid misinterpreting stamp noise as document content.

### 4. EXTRACTION TARGET: {doc_type}
- **Identity Context:** {user_identity}
- **Rules:**
  1. **Page Independence:** Scan ALL pages. Do not stop after Page 1.
  2. **Ignore Stamp Noise:** These anchors are already handled. Strictly ignore their text content and do NOT include or reference them in your JSON response.
  3. **Visual Supremacy:** If Raw OCR and Image conflict, the Image and your Logic are the source of truth. Correct OCR errors in your output JSON.
  4. **Target Specificity & Compliance:** 
     - Focus PRIMARILY on extracting fields relevant to `{doc_type}`. 
     - **MANDATORY:** You MUST provide the specific body key defined in the schema (e.g. `finance_body` for Invoices, `career_body` for Certificates). 
     - If the document is hybrid and contains other data, you may fill multiple body keys.
     - **BEWARE:** Do NOT return generic data under a wrong key. Ensure the category names match the TARGET SCHEMA exactly.
  5. **Strict Omission:** Do NOT return keys with null or empty values. Omit them entirely from the JSON.

### 5. TARGET SCHEMA
{target_schema_json}

Return ONLY valid JSON.
"""

        # User Identity Context
        priv_json = self.config.get_private_profile_json()
        bus_json = self.config.get_business_profile_json()
        user_identity = f"Private: {priv_json}\nBusiness: {bus_json}"

        # Signature Data
        sig_data = {}
        if stage_1_5_result and "signatures" in stage_1_5_result:
            sig_data = stage_1_5_result["signatures"]

        if types_to_extract:
            print(f"[AI] Stage 2 (Extraction) [START] -> Types: {', '.join(types_to_extract)}, Vision: {bool(pdf_path)}")

        for i, doc_type in enumerate(types_to_extract):
            include_repair = (i == 0)
            schema = self.get_target_schema(doc_type, include_repair=include_repair)
            
            # Context Limit: Gemini handles large contexts easily. 100k chars is safe.
            limit = 100000
            
            long_doc_hint = ""
            if is_long_document and include_repair:
                long_doc_hint = "CAUTION: This document is long (>10 pages). Please focus on repairing ONLY the first 10 pages in the `repaired_text` field to avoid output truncation. Ensure ALL semantic data (like transactions) are still extracted regardless of length!"

            prompt_repair_instruction = ""
            if include_repair:
                prompt_repair_instruction = f"""
### 2.1 MISSION: FULL TEXT REPAIR (HYBRID)
In addition to the JSON fields, you MUST provide the field `repaired_text`. 
{long_doc_hint}
Correct all OCR errors, restore broken words, and use `=== PAGE X ===` separators. This text will be used for future indexing and searching.
"""
            
            prompt = PROMPT_TEMPLATE.format(
                doc_type=doc_type,
                document_text=best_text[:limit],
                stamps_json=stamps_json_str,
                signature_json=json.dumps(sig_data),
                user_identity=user_identity,
                target_schema_json=json.dumps(schema, indent=2),
                repair_mission=prompt_repair_instruction
            )
            try:
                extraction = self._generate_json(prompt, stage_label=f"STAGE 2: {doc_type}", images=images_payload)
                if extraction:
                    found_keys = []
                    for key, value in extraction.items():
                        if key.endswith("_body") or key in ["internal_routing", "verification", "travel_body"]:
                            final_semantic_data["bodies"][key] = value
                            found_keys.append(key)
                    
                    if not found_keys:
                         print(f"[AI] STAGE 2: {doc_type} -> Success (But NO body-data found!)")
                    else:
                         print(f"[AI] STAGE 2: {doc_type} -> Success (Found: {', '.join(found_keys)})")

                    if not final_semantic_data["meta_header"]:
                        final_semantic_data["meta_header"] = extraction.get("meta_header", {})

                    if extraction.get("repaired_text"):
                        if not final_semantic_data["repaired_text"] or len(extraction["repaired_text"]) > len(final_semantic_data["repaired_text"]):
                            final_semantic_data["repaired_text"] = extraction["repaired_text"]
                else:
                    print(f"[AI] STAGE 2: {doc_type} -> FAILED (JSON Error or Truncation after retries)")
                    return None
            except Exception as e:
                print(f"[AI] Stage 2 Error ({doc_type}): {e}")
                return None

        # Final Validation: Did we get anything useful?
        bodies_count = len(final_semantic_data.get("bodies", {}))
        has_meta = len(final_semantic_data.get("meta_header", {})) > 0
        
        if bodies_count == 0 and not has_meta:
             print(f"[AI] Stage 2 (Extraction) [DONE] -> FAILED (No data extracted)")
             return None

        cat_str = "category" if bodies_count == 1 else "categories"
        print(f"[AI] Stage 2 (Extraction) [DONE] -> Success ({bodies_count} {cat_str}: {', '.join(final_semantic_data['bodies'].keys())})")
        return final_semantic_data

    def generate_smart_filename(self, semantic_data: Dict, doc_types: List[str]) -> str:
        """
        Phase 2.4: Smart Filename Generation.
        Generates a human-readable filename based on extracted data.
        Pattern: YYYY-MM-DD__ENTITY__TYPE.pdf
        """
        
        # 1. Date (WANN)
        date_str = "0000-00-00"
        meta = semantic_data.get("meta_header", {})
        if meta.get("doc_date"):
            date_str = meta["doc_date"]
        
        # 2. Entity (WER/WAS)
        entity_name = "Unknown"
        
        # Priority 1: Context Entity Name
        if meta.get("subject_context") and meta["subject_context"].get("entity_name"):
            entity_name = meta["subject_context"]["entity_name"]
        else:
            # Priority 2: Structured Sender Name
            sender = meta.get("sender", {})
            if isinstance(sender, dict):
                entity_name = sender.get("name") or "Unknown"
            elif isinstance(sender, str):
                entity_name = sender  # Fallback for old/flat formats
                
            # Priority 3: Check Bodies for specific partners/patients
            if entity_name == "Unknown":
                bodies = semantic_data.get("bodies", {})
                if "legal_body" in bodies:
                    partners = bodies["legal_body"].get("contract_partners", [])
                    if partners and isinstance(partners[0], dict):
                        entity_name = partners[0].get("name")
                elif "health_body" in bodies:
                     patient = bodies["health_body"].get("patient")
                     if isinstance(patient, dict):
                         entity_name = patient.get("name")

        # Clean Entity Name
        if not entity_name:
            entity_name = "Unknown"
            
        entity_name = re.sub(r'[\s\./\\:]+', '_', entity_name)
        entity_name = re.sub(r'__+', '_', entity_name)
        entity_name = entity_name.strip('_')

        # 3. Type (WAS)
        # Ensure we filter out None values and noise tags
        clean_types = [t for t in doc_types if t and isinstance(t, str) and t not in ["INBOUND", "OUTBOUND", "INTERNAL", "CTX_PRIVATE", "CTX_BUSINESS", "UNKNOWN"]]
        type_str = "-".join(clean_types[:2]) if clean_types else "DOC"

        filename = f"{date_str}__{entity_name}__{type_str}.pdf"
        # Final sanitize
        return re.sub(r'[^\w\-.@]', '_', filename)
