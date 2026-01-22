from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import datetime
import json
from decimal import Decimal
from decimal import Decimal
import time
import random
from google import genai
from google.genai.errors import ClientError
from core.models.canonical_entity import (
    DocType, InvoiceData, LogisticsData, BankStatementData, 
    TaxAssessmentData, ExpenseData, UtilityData, ContractData, 
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

    @classmethod
    def get_adaptive_delay(cls) -> float:
        return cls._adaptive_delay
    
    def __init__(self, api_key: str, model_name: str = 'gemini-2.0-flash'):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model_name 

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

        # Load Schema
        schema_path = "/home/schnebeck/.gemini/antigravity/brain/0c4bc2e7-3c24-4140-a725-c6afcc6fb483/document_schema.json" # Hardcoded for now or loaded relative?
        # Let's read it here or pass it in. For robustness, I'll inline a minimal version if file read fails, or better read it.
        try:
             with open(schema_path, "r") as f:
                 doc_schema = json.load(f)
        except Exception as e:
             print(f"Error loading schema: {e}")
             return AIAnalysisResult() # Fail safe
             
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
        
        print(f"DEBUG AI PROMPT:\n{prompt}")
        
        try:
            contents = [prompt]
            if image:
                contents.append(image)
                
            response = None
            
            # 0. Adaptive Delay (Swing In)
            if AIAnalyzer._adaptive_delay > 0:
                print(f"AI Adaptive Delay: Sleeping {AIAnalyzer._adaptive_delay:.2f}s...")
                time.sleep(AIAnalyzer._adaptive_delay)

            # Retry Loop
            for attempt in range(self.MAX_RETRIES):
                self._wait_for_cooldown()
                
                try:
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=contents
                    )
                    break # Success
                except ClientError as e:
                    # Check for 429 Resource Exhausted
                    # e.code or e.status might be present
                    is_429 = False
                    if hasattr(e, "code") and e.code == 429: is_429 = True
                    if hasattr(e, "status") and "RESOURCE_EXHAUSTED" in str(e.status): is_429 = True
                    # Check message text as fallback
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e): is_429 = True
                    
                    if is_429:
                        # 1. Increase Adaptive Delay (Multiplicative Increase with CAP)
                        # Limit max delay to 256s (approx 4 mins) as per user request.
                        old_delay = AIAnalyzer._adaptive_delay
                        new_delay = max(2.0, AIAnalyzer._adaptive_delay * 2.0)
                        AIAnalyzer._adaptive_delay = min(256.0, new_delay)
                        
                        if AIAnalyzer._adaptive_delay != old_delay:
                            print(f"AI Rate Limit Hit! Increasing Adaptive Delay: {old_delay:.2f}s -> {AIAnalyzer._adaptive_delay:.2f}s")

                        # 2. Exponential Backoff for *this* retry
                        # We still wait exponentially for the current request to clear the immediate congestion.
                        delay = 2 * (2 ** attempt) + random.uniform(0, 1)
                        print(f"AI 429 Error. Backing off for {delay:.1f}s (Attempt {attempt+1}/{self.MAX_RETRIES})")
                        
                        # Set Cooldown
                        AIAnalyzer._cooldown_until = datetime.datetime.now() + datetime.timedelta(seconds=delay)
                        
                        # Loop will check cooldown next iteration
                        continue
                    else:
                        raise e # Other error
            
            if not response:
                print("AI Analysis Failed after retries.")
                return AIAnalysisResult()

            # Success: Decrease Adaptive Delay (Multiplicative Decrease)
            # "Swing in" towards 0 if stable.
            if AIAnalyzer._adaptive_delay > 0:
                 old_delay = AIAnalyzer._adaptive_delay
                 AIAnalyzer._adaptive_delay = max(0.0, AIAnalyzer._adaptive_delay * 0.5)
                 # If very small, snap to 0
                 if AIAnalyzer._adaptive_delay < 0.1: AIAnalyzer._adaptive_delay = 0.0
                 print(f"AI Success. Decreasing Adaptive Delay: {old_delay:.2f}s -> {AIAnalyzer._adaptive_delay:.2f}s")
                 
            response_text = response.text
            
            # Clean up markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "")
            elif "```" in response_text:
                response_text = response_text.replace("```", "")
                
            semantic_data = json.loads(response_text)
            print(f"DEBUG Semantic Structure:\n{json.dumps(semantic_data, indent=2)}")
            
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

            return AIAnalysisResult(
                sender=extracted["sender"],
                doc_date=doc_date,
                amount=to_decimal(extracted["amount"]),
                gross_amount=to_decimal(extracted["gross_amount"]),
                # ... Other fields might be missing in this basic hybrid pass
                # For now, we focus on the core fields requested + Semantic Data
                
                # ... Other fields might be missing in this basic hybrid pass
                # For now, we focus on the core fields requested + Semantic Data
                
                doc_type=(
                    ", ".join(extracted["doc_type"]) 
                    if isinstance(extracted["doc_type"], list) 
                    else extracted["doc_type"]
                ),
                
                # IMPORTANT: Attach the full semantic structure
                semantic_data=semantic_data,
                
                # We can still attach extra_data if we want to support legacy or additional fields
                # extra_data=data.get("extra_data") # Legacy?
            )

            # Phase 80: Backfill Summary for Indexing
            # Ensure semantic_data['summary'] has the best consolidated values
            if "summary" not in semantic_data:
                semantic_data["summary"] = {}
            
            summ = semantic_data["summary"]
            if extracted["amount"]:
                 summ["amount"] = str(extracted["amount"])
            if extracted["gross_amount"]:
                 summ["gross_amount"] = str(extracted["gross_amount"]) # Add to schema?
            if extracted["sender"]:
                 summ["sender_name"] = extracted["sender"]
            # Currency usually not extracted in basic traverse yet, add if needed or rely on AI
            
            # Re-assign modified semantic_data
            result.semantic_data = semantic_data
            
            return result

            
        except Exception as e:
            print(f"AI Analysis Error: {e}")
            return AIAnalysisResult()
    def identify_entities(self, text: str, semantic_data: dict = None) -> List[dict]:
        """
        Phase 1 of Canonization: Identify distinct documents.
        Uses semantic_data if available (Phase 98 Refinement), otherwise fallback to text.
        """
        if semantic_data and isinstance(semantic_data, dict) and "pages" in semantic_data:
            # Phase 98: Use Semantic JSON Refinement
            print("[AIAnalyzer] Using Semantic JSON for Entity Identification (Refinement Mode)")
            return self.refine_semantic_entities(semantic_data)
        
        # Legacy / Fallback Mode (Raw Text)
        return self._identify_entities_legacy(text, semantic_data)

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
             result = self._generate_json(prompt)
             # Explicit logging for User Visibility
             print(f"\n[Refinement Result] AI Output: {json.dumps(result, indent=2)}\n")
             
             if isinstance(result, list): return result
             if isinstance(result, dict) and "entities" in result: return result["entities"]
             return []
        except Exception as e:
             print(f"[Refinement] Failed: {e}")
             return []

    def _identify_entities_legacy(self, text: str, semantic_data: dict = None) -> List[dict]:
        # ... (Original identify_entities logic mooved here) ...
        if not text: return []
        
        # Build hints from semantic data
        structural_hints = ""
        if semantic_data:
             summary = semantic_data.get("summary", {})
             doc_types = summary.get("doc_type", [])
             if isinstance(doc_types, list) and doc_types:
                 structural_hints = f"\n### PREVIOUS ANALYSIS HINTS\nThe system previously detected the following Semantic Types: {', '.join(doc_types)}.\nUse this to guide your splitting (e.g. look for an Invoice followed by an Order Confirmation)."

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
            result = self._generate_json(prompt)
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
        
        print("\n=== [DEBUG] STAGE 2 EXTRACTION PROMPT ===")
        print(prompt)
        print("=========================================\n")
        
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
            result = self._generate_json(prompt)
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
                         business_id: Optional[IdentityProfile]) -> Dict[str, Any]:
        """
        Phase 102: Master Classification Step.
        Uses 'Sandwich' input (First/Last Page) and User Identities to determine:
        1. DocType
        2. Direction (INBOUND/OUTBOUND)
        3. Tenant Context (PRIVATE/BUSINESS)
        """
        if not pages_text:
            print("[DEBUG] classify_structure called with empty pages_text!")
            return {}
            
        print(f"[DEBUG] classify_structure scanning {len(pages_text)} pages...")
            
        # 1. Build Sandwich Text
        # Plaintext construction with markers
        sandwich_parts = []
        
        # First Page
        sandwich_parts.append("--- PAGE 1 (START) ---")
        sandwich_parts.append(pages_text[0])
        
        # Second Page (if available) - Requested by User
        if len(pages_text) > 1:
            sandwich_parts.append("--- PAGE 2 (START CONTINUED) ---")
            sandwich_parts.append(pages_text[1])
            
        # Last Page (if distinct from first two)
        # If len > 2, we have at least 3 pages (1, 2, 3...N)
        # So we add the Last Page.
        # If len == 2, we already added 1 and 2.
        
        if len(pages_text) > 2:
            last_idx = len(pages_text)
            if len(pages_text) > 3:
                 sandwich_parts.append(f"\n... (SKIPPED {last_idx - 3} PAGES) ...\n")
                 
            sandwich_parts.append(f"--- PAGE {last_idx} (END) ---")
            sandwich_parts.append(pages_text[-1])
            
        sandwich_text = "\n".join(sandwich_parts)
        
        # 2. Build Prompt Context
        def fmt_id(p: Optional[IdentityProfile]):
            if not p: return "None"
            return f"Name: {p.name}, Aliases: {p.aliases}, Company: {p.company_name}, VAT: {p.vat_id}, Address: {p.address_keywords}"

        # 3. Construct System Prompt
        # 3. Construct System Prompt
        # Phase 102 Update: Multi-Doc Classification Prompt
        
        # Serialize IDs for prompt
        priv_json_str = private_id.model_dump_json() if private_id else "{}"
        bus_json_str = business_id.model_dump_json() if business_id else "{}"
        
        prompt = f"""
        You are a Document Analyzer & Splitter for a hybrid DMS.
        Your task is to analyze the input text and identify ALL distinct logical document types contained within it.

        ### 1. USER IDENTITIES (CONTEXT)
        Use these to determine `direction` and `tenant_context` for EACH detected document separately.

        A. PRIVATE_IDENTITY: {priv_json_str}
        B. BUSINESS_IDENTITY: {bus_json_str}

        ### 2. ALLOWED DOCTYPES
        [
          "QUOTE", "ORDER", "ORDER_CONFIRMATION", "DELIVERY_NOTE", "INVOICE", "CREDIT_NOTE", "RECEIPT", "DUNNING",
          "PAYSLIP", "SICK_NOTE", "TRAVEL_REQUEST", "EXPENSE_REPORT", "CASH_EXPENSE",
          "BANK_STATEMENT", "TAX_ASSESSMENT", "UTILITY_BILL",
          "CONTRACT", "INSURANCE_POLICY", "LEGAL_CORRESPONDENCE", "OFFICIAL_LETTER",
          "DATASHEET", "MANUAL", "TECHNICAL_DOC",
          "CERTIFICATE", "MEDICAL_DOCUMENT", "VEHICLE_REGISTRATION", "APPLICATION", "NOTE", 
          "OTHER"
        ]

        ### 3. ANALYSIS RULES
        1. **Multi-Detection:** A single file can contain multiple logical types (e.g., a document titled "Invoice & Order Confirmation").
           - In this case, output TWO entries: one for INVOICE, one for ORDER_CONFIRMATION.
        2. **Attachments:** If a main document (e.g., Invoice) has clearly attached appendices (e.g., Timesheets, Manuals) that are significant, detect them as separate entities (e.g., TECHNICAL_DOC).
        3. **Direction:** Determine direction for each entity independently (though they are usually the same).

        ### 4. OUTPUT SCHEMA (JSON)
        Return a JSON object containing a list of detected entities.

        {{
          "source_file_summary": {{
            "is_hybrid_document": Boolean, // True if >1 distinct types found
            "primary_language": "de | en | ..."
          }},
          "detected_entities": [
            {{
              "doc_type": "Enum Value",
              "direction": "INBOUND | OUTBOUND | INTERNAL | UNKNOWN",
              "tenant_context": "PRIVATE | BUSINESS | UNKNOWN",
              "confidence": Float,
              "reasoning": "Found keyword 'Rechnung' and explicit mention of 'Auftragsbestätigung'"
            }}
            // ... add more objects if multiple types found
          ]
        }}
        
        ### INPUT DOCUMENT CONTENT
        The following text represents selected pages from the document based on sandwich logic:

        {sandwich_text}
        """
        
        print("\n=== [DEBUG] STAGE 1 CLASSIFICATION PROMPT ===")
        print(prompt)
        print("=============================================\n")
        
        try:
            result = self._generate_json(prompt)
            if result:
                # Debug Output as requested
                print("\n=== [DEBUG] STAGE 1 CLASSIFICATION RESULT ===")
                print(json.dumps(result, indent=2))
                print("=============================================\n")
                return result
            return {}
        except Exception as e:
            print(f"Classification Failed: {e}")
            return {}

    def _generate_json(self, prompt: str, image=None) -> Any:
        """Helper to call Gemini with Retry and parse JSON."""
        contents = [prompt]
        if image: contents.append(image)
        
        # print(f"\n--- [DEBUG AI PROMPT START] ---\n{prompt}\n--- [DEBUG AI PROMPT END] ---\n")
        
        self._wait_for_cooldown()
        
        # Simple Retry Loop (can reuse the complex one from analyze_text later)
        # For now, simplistic
        response = None
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents
            )
        except Exception as e:
            print(f"GenAI Error: {e}")
            return None
            
        if not response or not response.text:
            return None
            
        txt = response.text
        if "```json" in txt:
            txt = txt.replace("```json", "").replace("```", "")
        elif "```" in txt:
            txt = txt.replace("```", "")
            
        try:
            return json.loads(txt)
        except:
            print("Failed to parse JSON")
            return None
            
    # Keep consolidate_semantics for legacy/pipeline compat if needed
    def consolidate_semantics(self, raw_semantic_data: dict) -> dict:
        # ... existing implementation (simplified for brevity or kept) ...
        # (For now we just keep the file end cleaner or remove if we fully switch)
        # Leaving existing method stub
        return raw_semantic_data
