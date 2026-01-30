from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
import datetime
import json
import re
import base64
import fitz  # PyMuPDF
from decimal import Decimal
import time
import random
from google import genai
from google.genai.errors import ClientError
from core.models.canonical_entity import (
    DocType, InvoiceData, LogisticsData, BankStatementData,
    TaxAssessmentData, ExpenseData, UtilityData, ContractData,
    InsuranceData, VehicleData, MedicalData, LegalMetaData
)
from core.models.identity import IdentityProfile

@dataclass
class AIAnalysisResult:
    sender: Optional[str] = None
    doc_date: Optional[datetime.date] = None
    amount: Optional[Decimal] = None

    # Phase 45 Financials
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

    # Phase 30: Dynamic Data
    extra_data: Optional[dict] = None

    # Phase 70: Semantic Data
    semantic_data: Optional[dict] = None

class AIAnalyzer:
    """
    Analyzes document text using Google Gemini to extract structured data.
    """
    MAX_RETRIES = 5
    _cooldown_until: Optional[datetime.datetime] = None # Shared cooldown state
    _adaptive_delay: float = 0.0 # Adaptive delay in seconds (Harmonic Oscillation)
    _printed_prompts = set() # Phase 102: Debug Once

    def _print_debug_prompt(self, title: str, prompt: str):
        """Phase 102: Helper to print prompt ONCE in console for debugging."""
        if prompt not in self._printed_prompts:
            print(f"\n=== [{title}] ===\n{prompt}\n==============================\n")
            self._printed_prompts.add(prompt)

    @classmethod
    def get_adaptive_delay(cls) -> float:
        return cls._adaptive_delay

    def __init__(self, api_key: str, model_name: str = 'gemini-2.0-flash'):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model_name

    def list_models(self) -> List[str]:
        """
        Fetches available models from the Google GenAI API.
        Filters for models with generateContent support.
        """
        models = []
        for m in self.client.models.list():
            # Filter for models that support generating content
            # Note: In the new SDK, supported_methods is a list of strings
            if hasattr(m, 'supported_methods') and 'generateContent' in m.supported_methods:
                name = m.name
                if name.startswith("models/"):
                    name = name[7:]
                models.append(name)
        return sorted(models)

    @staticmethod
    def extract_headers_footers(ocr_pages: List[str], header_ratio=0.15, footer_ratio=0.10) -> List[str]:
        """
        Reduces text of each page to top 15% and bottom 10% to save tokens.
        """
        optimized_pages = []
        for text in ocr_pages:
            lines = text.split('\n')
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
          "looks_like_stack": true | false, // True if multiple different documents seem stuck together
          "confidence": 0.0-1.0
        }}
        """
        result = self._generate_json(prompt, stage_label="PRE-FLIGHT TYPE CHECK")
        return result or {}

    def run_stage_1_adaptive(self, pages_text: List[str], private_id: Optional[IdentityProfile], business_id: Optional[IdentityProfile]) -> dict:
        """
        Intelligent Controller for Stage 1.
        Selects optimal scan strategy based on content.
        """
        total_pages = len(pages_text)
        if total_pages == 0: return {}

        # --- PHASE A: PRE-FLIGHT ---
        pre_flight_pages = pages_text[:3]
        pre_flight_res = self.ask_type_check(pre_flight_pages)

        primary_type = pre_flight_res.get("primary_type", "OTHER")
        is_stack_suspicion = pre_flight_res.get("looks_like_stack", False)

        print(f"[STAGE 1] Pre-Flight: {total_pages} Pages. Type: {primary_type}. Stack: {is_stack_suspicion}")

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

        print(f"[STAGE 1] Selected Strategy: {scan_strategy} ({len(final_pages_to_scan)} pages prepared)")

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

    def analyze_text(self, text: str, image=None) -> AIAnalysisResult:
        """
        Send text and optional image to Gemini and parse the JSON response.
        :param text: Text content of the document.
        :param image: PIL.Image object of the first page (optional).
        """
        if (not text or not text.strip()) and not image:
            return AIAnalysisResult()

        return self._analyze_text_internal(text, image)

    def _generate_with_retry(self, contents):
        """
        Execute generation with robust 429 handling and adaptive delay.
        """
        # 0. Adaptive Delay (Swing In)
        if AIAnalyzer._adaptive_delay > 0:
            print(f"AI Adaptive Delay: Sleeping {AIAnalyzer._adaptive_delay:.2f}s...")
            time.sleep(AIAnalyzer._adaptive_delay)

        response = None
        last_error = None

        # Retry Loop
        for attempt in range(self.MAX_RETRIES):
            if attempt > 0:
                print(f"AI Retrying... (Attempt {attempt+1}/{self.MAX_RETRIES})")

            self._wait_for_cooldown()

            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents
                )

                # Success: Decrease Adaptive Delay (Multiplicative Decrease)
                if AIAnalyzer._adaptive_delay > 0:
                     old_delay = AIAnalyzer._adaptive_delay
                     AIAnalyzer._adaptive_delay = max(0.0, AIAnalyzer._adaptive_delay * 0.5)
                     if AIAnalyzer._adaptive_delay < 0.1: AIAnalyzer._adaptive_delay = 0.0
                     print(f"AI Success (Attempt {attempt+1}/{self.MAX_RETRIES}). Decreasing Adaptive Delay: {old_delay:.2f}s -> {AIAnalyzer._adaptive_delay:.2f}s")
                else:
                     # Just log success if it was first or subsequent attempt
                     if attempt > 0:
                         print(f"AI Success after {attempt+1} attempts.")

                return response

            except Exception as e:
                last_error = e
                # Check for 429 Resource Exhausted
                is_429 = False

                # ClientError usually wraps, but depending on library version:
                if hasattr(e, "code") and e.code == 429: is_429 = True
                if hasattr(e, "status") and "RESOURCE_EXHAUSTED" in str(e.status): is_429 = True
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e): is_429 = True

                if is_429:
                    # 1. Increase Adaptive Delay
                    old_delay = AIAnalyzer._adaptive_delay
                    new_delay = max(2.0, AIAnalyzer._adaptive_delay * 2.0)
                    AIAnalyzer._adaptive_delay = min(256.0, new_delay)

                    if AIAnalyzer._adaptive_delay != old_delay:
                        print(f"AI Rate Limit Hit! Increasing Adaptive Delay: {old_delay:.2f}s -> {AIAnalyzer._adaptive_delay:.2f}s")

                    # 2. Exponential Backoff for *this* retry
                    # Ensure we respect the adaptive delay if it's higher
                    backoff = 2 * (2 ** attempt) + random.uniform(0, 1)
                    delay = max(backoff, AIAnalyzer._adaptive_delay)
                    print(f"AI 429 Error. Backing off for {delay:.1f}s (Attempt {attempt+1}/{self.MAX_RETRIES})")

                    # Set Cooldown
                    AIAnalyzer._cooldown_until = datetime.datetime.now() + datetime.timedelta(seconds=delay)
                    continue
                else:
                    # Generic error fallback (e.g. 500, blocked content)
                    print(f"AI Error (Attempt {attempt+1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(1) # Small delay for generic errors

        # Soft Fail instead of hard crash
        print(f"ABORT: AI Analysis failed after {self.MAX_RETRIES} attempts. Last error: {last_error}")
        return None

    def analyze_text(self, text: str, image=None) -> AIAnalysisResult:
        schema_path = "/home/schnebeck/.gemini/antigravity/brain/0c4bc2e7-3c24-4140-a725-c6afcc6fb483/document_schema.json" # Hardcoded for now or loaded relative?
        # Let's read it here or pass it in. For robustness, I'll inline a minimal version if file read fails, or better read it.
        with open(schema_path, "r") as f:
            doc_schema = json.load(f)

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
            def to_decimal(val):
                if val is not None:
                    try: return Decimal(str(val))
                    except: pass
                return None

                # Phase 80: Backfill Summary for Indexing
                # Ensure semantic_data['summary'] has the best consolidated values
                if "summary" not in semantic_data:
                    semantic_data["summary"] = {}

                summ = semantic_data["summary"]
                if extracted["amount"]:
                    summ["amount"] = str(extracted["amount"])
                if extracted["gross_amount"]:
                    summ["gross_amount"] = str(extracted["gross_amount"])
                if extracted["sender"]:
                    summ["sender_name"] = extracted["sender"]

                # Re-assign modified semantic_data
                result.semantic_data = semantic_data

                return result

        except Exception as e:
            print(f"CRITICAL AI Analysis Error (Logic): {e}")
            import traceback
            traceback.print_exc()
            return AIAnalysisResult()
    def identify_entities(self, text: str, semantic_data: dict = None, detected_entities: List[dict] = None) -> List[dict]:
        """
        Phase 1.2 of Canonization: Identify distinct documents.
        Uses semantic_data if available (Phase 98 Refinement), otherwise fallback to text.
        """
        if semantic_data and isinstance(semantic_data, dict) and "pages" in semantic_data:
            # Phase 98: Use Semantic JSON Refinement
            print("[AIAnalyzer] Using Semantic JSON for Entity Identification (Refinement Mode)")
            return self.refine_semantic_entities(semantic_data)

        # Legacy / Fallback Mode (Raw Text)
        return self._identify_entities_legacy(text, semantic_data, detected_entities)

    def refine_semantic_entities(self, semantic_data: dict) -> List[dict]:
        """
        Phase 98: Analyzes the Semantic JSON structure to identify Logical Entities.
        Goals:
        - Detect Logical Boundaries (Start/End Page).
        - Merge content spanning pages (e.g. Tables).
        - Detach content from physical page numbers.
        """
        # 1. Extract Existing Type Hints
        existing_types_str = "OTHER"
        summary = semantic_data.get("summary", {})
        if "doc_type" in summary:
            # Can be list or string
            dt = summary["doc_type"]
            if isinstance(dt, list):
                existing_types_str = ", ".join(dt)
            else:
                existing_types_str = str(dt)

        # 2. Serialize semantic_data (Truncate if huge, but JSON usually fits)
        json_str = json.dumps(semantic_data, ensure_ascii=False)

        prompt = f"""
        You are a Semantic Document Architect.
        Your input is a "Physical Page Structure" (JSON) of a file.
        Your goal is to transform this into a "Logical Document Structure".

        ### EXISTING ANALYSIS
        The system has already detected the following Document Types: {existing_types_str}.
        You MUST respect these types. Do NOT invent new types.

        ### INPUT (Physical Structure)
        {json_str}

        ### TASK
        1. Analyze the JSON structure (Regions, Blocks).
        2. Identify Logical Document Boundaries (Start/End Pages).
           - MERGE content that spans multiple pages (e.g. a Table starting on Page 1 and ending on Page 2 is ONE logical unit).
        3. Return the start/end pages for each logical entity.

        ### OUTPUT
        Return a JSON LIST of Logical Entities:
        [
          {{
            "type": "INVOICE", // Use the type from EXISTING ANALYSIS
            "pages": [1, 2, 3], // The physical pages belonging to this entity
            "confidence": 0.99,
            "hints": "Table spans pages 1-3. Total amount found on page 3."
          }}
        ]
        """

        try:
             result = self._generate_json(prompt, stage_label="STAGE 1.2 REFINEMENT REQUEST")
             self._print_debug_prompt("REFINEMENT REQUEST", prompt)

             if isinstance(result, list): return result
             if isinstance(result, dict) and "entities" in result: return result["entities"]
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
             doc_types = [ent.get("doc_type") for ent in detected_entities if ent.get("doc_type")]
             structural_hints = f"\n### PREVIOUS ANALYSIS HINTS\nThe classification stage (Stage 1.1) already identified these types: {', '.join(doc_types)}.\n"
             structural_hints += "Ensure the output contains boundaries for these documents.\n"
        elif semantic_data:
             summary = semantic_data.get("summary", {})
             doc_types = summary.get("doc_type", [])
             if isinstance(doc_types, list) and doc_types:
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

    def extract_canonical_data(self, doc_type: Any, text: str) -> dict:
        """
        Phase 2 of Canonization: Extract strict CDM for a specific Entity Type.
        Dynamically builds the target schema based on the Pydantic model.
        """
        # Ensure DocType Enum
        if isinstance(doc_type, str):
            try:
                doc_type = DocType(doc_type)
            except:
                pass # Keep as string if custom, but mapping won't work

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
            except:
                pass

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
            except:
                pass

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
   - If a single logical document serves multiple purposes (e.g. "Invoice & Delivery Note"), assign **MULTIPLE** tags. Do NOT split a single physical page.

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
      "confidence": 0.99,
      "reasoning": "Billing address matches 'Max Mustermann' (Private). Delivery address to 'ACME Corp' is ignored."
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
            result = self._generate_json(prompt, stage_label="STAGE 1.1 AI REQUEST")

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

    def _generate_json(self, prompt: str, stage_label: str = "AI REQUEST", image=None) -> Any:
        """Helper to call Gemini with Retry and parse JSON."""
        self._print_debug_prompt(stage_label, prompt)

        contents = [prompt]
        if image: contents.append(image)

        # print(f"\n--- [DEBUG AI PROMPT START] ---\n{prompt}\n--- [DEBUG AI PROMPT END] ---\n")

        response = self._generate_with_retry(contents)

        if not response or not response.text:
            return None

        txt = response.text
        if "```json" in txt:
            txt = txt.replace("```json", "").replace("```", "")
        elif "```" in txt:
            txt = txt.replace("```", "")

        try:
            res_json = json.loads(txt)
            print(f"\n=== [{stage_label} RESPONSE] ===\n{json.dumps(res_json, indent=2)}\n===================================\n")
            return res_json
        except:
            print("Failed to parse JSON")
            return None

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

    def get_target_schema(self, doc_type: str) -> Dict:
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
            return {
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
                },
                "internal_routing": {
                    "project_code": "String (from Stamp 'Kostenstelle')",
                    "received_at": "YYYY-MM-DD (from Stamp 'Eingang')",
                    "verified_by": "String (from Stamp 'Bearbeiter')"
                }
            }

        elif dt == "DUNNING":
            return {
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
            return {
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
            return {
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
            return {
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
            return {
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
            return {
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
            return {
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
            return {
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
            return {
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
            return {
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
            return {
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
            return {
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
            return {
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
            return {
                "meta_header": base_header,
                "generic_body": {
                    "subject": "String",
                    "keywords": ["String", "String"],
                    "content_summary": "String"
                }
            }

    def assemble_best_text_source(self, raw_ocr_full: str, stage_1_5_result: Dict) -> str:
        """
        Phase 2.2: The Arbiter.
        Decides intelligently which text source to use (Raw OCR vs AI Repaired).
        """
        if not stage_1_5_result:
            return raw_ocr_full

        # 1. What did the Arbiter recommend?
        arbiter = stage_1_5_result.get("arbiter_decision", {})
        recommendation = arbiter.get("primary_source_recommendation", "RAW_OCR")

        # 2. If RAW is good enough, use RAW
        if recommendation == "RAW_OCR":
            return raw_ocr_full

        # 3. If AI is better (e.g. because of stamps or noise):
        clean_page_1 = stage_1_5_result.get("layer_document", {}).get("clean_text", "")

        if not clean_page_1:
            return raw_ocr_full

        # Build hybrid text:
        # Page 1 = AI Clean Text
        # Remaining = Raw OCR context
        combined_text = f"""
=== PAGE 1 (AI CLEANED / VERIFIED) ===
{clean_page_1}

=== RAW OCR CONTEXT (FULL DOCUMENT) ===
{raw_ocr_full}
"""
        return combined_text

    def get_page_image_payload(self, pdf_path: str, page_index: int = 0) -> Optional[Dict]:
        """
        Renders a PDF page as a Base64 image for Vision AI.
        """
        try:
            doc = fitz.open(pdf_path)
            if page_index >= doc.page_count:
                return None
                
            # 200 DPI is requested for better recognition
            pix = page.get_pixmap(dpi=200) 
            img_bytes = pix.tobytes("png")
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            
            return {
                "base64": b64,
                "label": "FIRST_PAGE_VISUAL_CONTEXT",
                "page_index": page_index
            }
        except Exception as e:
            print(f"[Stage 2] Image generation failed: {e}")
            return None

    def run_stage_2(self, raw_ocr_text: str, stage_1_result: Dict, stage_1_5_result: Dict, pdf_path: Optional[str] = None) -> Dict:
        """
        Phase 2.3: Semantic Extraction Pipeline.
        Executes extraction for each detected type and consolidates result.
        Now supports Vision Context if pdf_path is provided.
        """
        print(f"--- [AIAnalyzer] STARTING STAGE 2 SEMANTIC EXTRACTION ---")

        # 1. Text Merging (Arbiter Logic)
        best_text = self.assemble_best_text_source(raw_ocr_text, stage_1_5_result)

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
                    images_payload.append({"mime_type": "image/png", "data": img_bytes})
                    print("[Stage 2] Vision Context enabled (Page 1).")
                except Exception as e:
                    print(f"[Stage 2] Vision prep failed: {e}")

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
            "bodies": {}
        }

        PROMPT_TEMPLATE = """
You are a Semantic Data Extractor for a Life Management System.
Your goal is to extract structured data for the document type: **{doc_type}**.

### 1. INPUT DATA

**A. VISUAL CONTEXT (IMAGE):**
(If provided) Use the image to understand the layout and geometric relationships.
**Pattern Recognition Rule:** Apply the visual structure found on Page 1 to interpret the raw text stream.

**B. DOCUMENT TEXT:**
{document_text}

**C. STAMP DATA (Validated Meta-Data):**
The visual audit identified the following structured data (Stamps/Handwriting).
**Use these values with high priority** to fill metadata fields like 'received_at', 'project_code' or 'verified_by'.
>>> {stamps_json} <<<

### 2. INSTRUCTION
Extract data into the target JSON schema.
1. **Address Splitting:** Split addresses into street, house_number, zip_code, city, country.
2. **Contact Info:** Extract all phones, emails, and websites into lists.
3. **Registry/Tax:** Look for VAT IDs, Tax IDs and Commercial Register numbers.
4. **Metadata Fields:** Extract Project IDs, Verifiers from STAMP DATA (match labels).
5. **Normalization:** - Dates must be ISO 8601 (YYYY-MM-DD).
   - Amounts must be Float (10.50). 
   - Empty fields must be `null` or empty lists `[]`.

### 3. TARGET SCHEMA (JSON)
{target_schema_json}

Return ONLY the valid JSON.
"""

        for doc_type in types_to_extract:
            print(f"[Stage 2] Processing Type: {doc_type}")
            schema = self.get_target_schema(doc_type)
            
            # Context Limit
            limit = 6000 if doc_type in ["TECHNICAL_DOC", "MANUAL"] else 14000
            
            prompt = PROMPT_TEMPLATE.format(
                doc_type=doc_type,
                document_text=best_text[:limit],
                stamps_json=stamps_json_str,
                target_schema_json=json.dumps(schema, indent=2)
            )

            try:
                # Merge images_payload into contents for _generate_json
                image = images_payload[0] if images_payload else None
                extraction = self._generate_json(prompt, stage_label=f"STAGE 2 EXTRACTION ({doc_type})", image=image)
                
                if not extraction: continue

                if not final_semantic_data["meta_header"]:
                    final_semantic_data["meta_header"] = extraction.get("meta_header", {})

                for key, value in extraction.items():
                    if key.endswith("_body") or key in ["internal_routing", "verification", "travel_body"]:
                        final_semantic_data["bodies"][key] = value

            except Exception as e:
                print(f"[Stage 2] Extraction Error ({doc_type}): {e}")

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
        if entity_name:
            entity_name = re.sub(r'[\s\./\\:]+', '_', entity_name)
            entity_name = re.sub(r'__+', '_', entity_name)
            entity_name = entity_name.strip('_')

        # 3. Type (WAS)
        clean_types = [t for t in doc_types if t not in ["INBOUND", "OUTBOUND", "INTERNAL", "CTX_PRIVATE", "CTX_BUSINESS", "UNKNOWN"]]
        type_str = "-".join(clean_types[:2]) if clean_types else "DOC"

        filename = f"{date_str}__{entity_name}__{type_str}.pdf"
        # Final sanitize
        return re.sub(r'[^\w\-.@]', '_', filename)
