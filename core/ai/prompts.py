"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai/prompts.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Centralized storage for AI instructions and prompt templates.
                Organized by processing stage to reduce logic file complexity.
------------------------------------------------------------------------------
"""

# --- STAGE 1.0: PRE-FLIGHT ---
PROMPT_STAGE_1_0_PREFLIGHT = """
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

# --- STAGE 1.1: CLASSIFICATION & SEGMENTATION ---
PROMPT_STAGE_1_1_CLASSIFICATION = """
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
      "type_tags": ["INVOICE"],
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

# --- STAGE 1.2: ENTITY IDENTIFICATION (REFINEMENT) ---
PROMPT_STAGE_1_2_REFINEMENT = """
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

# --- STAGE 1.2: ENTITY IDENTIFICATION (TEXT FALLBACK) ---
PROMPT_STAGE_1_2_SPLIT = """
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
{allowed_types_str}
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

### TEXT CONTENT:
{text_content}
"""

# --- STAGE 2: CANONICAL EXTRACTION (MASTER) ---
PROMPT_STAGE_2_MASTER = """
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
{zugferd_hint}
### 4. EXTRACTION TARGET: {entity_type}
- **Identity Context:** {user_identity}
- **Rules:**
  1. **Page Independence:** Scan ALL pages. Do not stop after Page 1.
  2. **Ignore Stamp Noise:** These anchors are already handled. Strictly ignore their text content and do NOT include or reference them in your JSON response.
  3. **Visual Supremacy:** If Raw OCR and Image conflict, the Image and your Logic are the source of truth. Correct OCR errors in your output JSON.
  4. **Target Specificity & Compliance:** 
     - **MISSION:** Extract ONLY fields relevant to the target type `{entity_type}`. 
     - **MANDATORY:** You MUST provide the specific body key defined in the schema.
     - **EXCLUSIVITY:** Do NOT populate other body sections (e.g., do not provide `finance_body` if the target is `CERTIFICATE`). This pass is a specialized extraction.
     - **BEWARE:** Do NOT return generic data under a wrong key. Ensure the category names match the TARGET SCHEMA exactly.
  5. **Strict Omission:** Do NOT return keys with null or empty values. Omit them entirely from the JSON.
  6. **Strict Flattening:** Never create nested sub-objects (like `address` or `contact`) unless they are explicitly defined in the PROVIDED SCHEMA. Follow the provided schema key-for-key.

### 5. TARGET SCHEMA
{target_schema_json}

Return ONLY valid JSON.
"""

# --- STAGE 2: REPAIR INSTRUCTIONS ---
PROMPT_STAGE_2_REPAIR_INSTRUCTION = """
### 2.1 MISSION: FULL TEXT REPAIR (HYBRID)
In addition to the JSON fields, you MUST provide the field `repaired_text`. 
{long_doc_hint}
Correct all OCR errors, restore broken words, and use `=== PAGE X ===` separators. This text will be used for future indexing and searching.
"""

# --- STAGE 1.99: VALIDATION/CORRECTION ---
PROMPT_REFINEMENT_CORRECTION = """
Your previous response contained the following errors/violations:
{error_summary}

### TASK
Please correct the extraction and return the updated JSON according to the schema.
Ensure that:
{validation_checks}
"""

# --- PHASE 2: CANONICAL DATA EXTRACTION ---
PROMPT_STAGE_2_EXTRACTION = """
You are a Specialized Data Extractor for: {val}.

### TARGET SCHEMA (Canonical Data Model)
Extract data into this exact JSON structure:

{{
  "entity_type": "{val}",
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
{text_content}
"""

# --- STAGE 2: PEDANTIC CORRECTION ---
PROMPT_STAGE_2_CORRECTION = """
### ⚠️ SYSTEM VALIDATOR REJECTION (Role: Pedantic JSON Corrector) ⚠️
You are now acting as a pedantic JSON structure and syntax corrector. 
Your SOLE MISSION is to repair the previous faulty JSON response by following the error reports below. 

### YOUR FAULTY JSON RESPONSE:
```json
{faulty_json_str}
```

### ERRORS DETECTED:
{error_msg}

### MANDATORY REPAIR RULES:
1. Implement every ACTION specified in the error list.
2. Use the "FAULTY JSON" as your starting point and apply the fixes.
3. Strictly follow the JSON schema provided in section 5.
4. DO NOT create nested 'address', 'contact', or 'identifiers' objects.
5. Provide the FULL, CORRECTED JSON response now.

Refusal to comply will result in an immediate resubmission of this task!
"""

# --- IDENTITY PARSING ---
PROMPT_IDENTITY_PARSE = """
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

# --- ZUGFERD / EN 16931 GUIDE ---
ZUGFERD_GUIDE = """
### 📋 EXTRACTION DIRECTIVES (EN 16931 / ZUGFeRD 2.2)
Use the following standardized terminology for extraction:
- **BT-1 (Invoice ID):** -> "invoice_number"
- **BT-2 (Issue Date):** -> "invoice_date" (ISO 8601: YYYY-MM-DD)
- **BT-9 (Due Date):** -> "due_date" (ISO 8601: YYYY-MM-DD)
- **BT-5 (Currency):** -> "currency" (ISO 4217, default: "EUR")
- **BT-13 (Order ID):** -> "order_number"
- **BT-7 (Service Date):** -> "service_date" (Leistungsdatum, often separate from invoice date)
- **BT-46 (Customer ID):** -> "customer_id" (Internal number assigned to recipient)
- **BT-10 (Buyer Reference):** -> "buyer_reference"
- **BT-11 (Project ID):** -> "project_reference"
- **BT-19 (Cost Center):** -> "accounting_reference" (Buyer accounting reference)
- **BT-20 (Payment Terms):** -> "payment_terms" (Cash discounts, valid for 10 days, etc.)
- **Line Items (IncludedSupplyChainTradeLineItem):**
  - BT-126 (ID) -> "pos"
  - BT-153 (Description) -> "description"
  - BT-129 (Quantity) -> "quantity"
  - BT-146 (Price) -> "unit_price"
  - BT-131 (Net Amount) -> "total_price"
- **Monetary Summation (Totals):**
  - BT-109 (Tax Basis) -> "tax_basis_total_amount"
  - BT-110 (Tax Total) -> "tax_total_amount"
  - BT-112 (Grand Total) -> "grand_total_amount"
  - BT-115 (Payable) -> "due_payable_amount"

### 📜 LEGAL & CONTRACTUAL DIRECTIVES
If extracting into "legal_body":
- **document_title:** The exact title (e.g., "Rental Agreement", "Insurance Policy").
- **contract_id:** Any unique reference or policy number.
- **issuer:** The issuing party (e.g., Landlord, Insurer).
- **beneficiary:** The protected or served party (e.g., You).
- **effective_date:** The start date of the contract (YYYY-MM-DD).
- **termination_date:** The date the contract ends IF it has already been cancelled (YYYY-MM-DD).
- **valid_until:** The fixed expiration or warranty end date (YYYY-MM-DD). Use this for fixed terms or one-off certificates.
- **notice_period:** 
  - **value:** Numerical duration (e.g., 3).
  - **unit:** Time unit (DAYS, WEEKS, MONTHS, YEARS).
  - **anchor_type:** START_OF, END_OF, or ANY_TIME.
  - **anchor_scope:** WEEK, MONTH, QUARTER, HALF_YEAR, or YEAR.
  - **original_text:** The raw text describing the notice period (e.g., '6 weeks to quarter end').
- **renewal_clause:** Text describing auto-renewal (e.g., '12 months').
- **contract_type:** RENTAL, INSURANCE, EMPLOYMENT, etc.

### 🔗 UNIVERSAL SEMANTIC LINKING (MetaHeader)
For ALL document types, extract ALL found IDs into the "references" list:
- **CUSTOMER_ID:** Your reference number at the sender.
- **ORDER_NUMBER:** Reference to a specific purchase order (BT-13).
- **PROJECT_REFERENCE:** Reference to a project or site (BT-11).
- **INVOICE_ID:** If found as a reference in a non-invoice document.
- **OTHER:** Use for any other significant technical identifiers.
"""
