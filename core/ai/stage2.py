"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai/stage2.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Stage 2 Processor (Semantic Extraction).
                Handles detailed data extraction for specific document types,
                vision-assisted calibration, and ZUGFeRD data overlay.
------------------------------------------------------------------------------
"""

import base64
import copy
import json
import re
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

import fitz
from google.genai import types
from pydantic import ValidationError

from core.ai import prompts
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
from core.models.semantic import SemanticExtraction, FinanceBody, LegalBody


class Stage2Processor:
    """
    Handles the details of extracting domain-specific data from documents.
    """

    def __init__(self, client, config) -> None:
        self.client = client
        self.config = config

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
            "iban": "String (International Bank Account Number)",
            "bic": "String (Bank Identifier Code / SWIFT)",
            "bank_name": "String (Name of the financial institution)",
            "identifiers": {
                "vat_id": "String (USt-IdNr)",
                "tax_id": "String (Steuernummer)",
                "commercial_register": "String (HRB/HRA Number + Court)",
                "customer_id": "String (My ID at this company)"
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

    def get_target_schema(self, entity_type: str, include_repair: bool = True) -> str:
        """
        Generates a detailed, EN 16931 aligned JSON schema hint for the LLM.
        """
        schema_dict = SemanticExtraction.model_json_schema()
        
        def clean_schema(d):
            if not isinstance(d, dict): return
            keys_to_drop = ["title", "additionalProperties", "default", "populate_by_name"]
            for k in keys_to_drop: d.pop(k, None)
            for v in d.values():
                if isinstance(v, dict): clean_schema(v)
                elif isinstance(v, list):
                    for item in v: clean_schema(item)

        clean_schema(schema_dict)
        
        # Determine target body
        TYPE_TO_BODY = {
            "INVOICE": "finance_body", "CREDIT_NOTE": "finance_body", "RECEIPT": "finance_body",
            "DUNNING": "finance_body", "UTILITY_BILL": "finance_body", "ORDER": "finance_body",
            "QUOTE": "finance_body", "ORDER_CONFIRMATION": "finance_body",
            "BANK_STATEMENT": "finance_body", "TAX_ASSESSMENT": "finance_body",
            "EXPENSE_REPORT": "finance_body", "PAYSLIP": "finance_body",
            "CONTRACT": "legal_body", "INSURANCE_POLICY": "legal_body",
            "OFFICIAL_LETTER": "legal_body", "LEGAL_CORRESPONDENCE": "legal_body",
            "CERTIFICATE": "legal_body"
        }
        target_body_key = TYPE_TO_BODY.get(entity_type.upper(), "other_body")
        
        BODY_MODELS = {
            "finance_body": FinanceBody,
            "legal_body": LegalBody
        }
        target_model = BODY_MODELS.get(target_body_key)
        
        if "properties" in schema_dict and "bodies" in schema_dict["properties"]:
            if target_model:
                target_body_schema = target_model.model_json_schema()
                clean_schema(target_body_schema)
                schema_dict["properties"]["bodies"]["properties"] = {
                    target_body_key: target_body_schema
                }
            else:
                schema_dict["properties"]["bodies"]["properties"] = {}

        if include_repair:
            schema_dict["repaired_text"] = "The complete document text with errors fixed."
            
        return f"{json.dumps(schema_dict, indent=2)}\n{prompts.ZUGFERD_GUIDE}"

    def assemble_best_text_source(self, raw_ocr_pages: List[str], stage_1_5_result: Dict) -> str:
        """
        Joins OCR pages with markers.
        """
        return "\n\n".join([f"=== PAGE {i+1} (RAW OCR) ===\n{p}" for i, p in enumerate(raw_ocr_pages)])

    def get_page_image_payload(self, pdf_path: str, page_index: int = 0) -> Optional[Dict]:
        """
        Renders a PDF page as a Base64 image payload.
        """
        try:
            doc = fitz.open(pdf_path)
            if page_index >= doc.page_count:
                doc.close()
                return None
            
            page = doc.load_page(page_index)
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
        Phase 2.3: Master Semantic Extraction Pipeline.
        """
        MAX_PAGES_STAGE2 = 50
        is_long_document = len(raw_ocr_pages) > 10
        
        if len(raw_ocr_pages) > MAX_PAGES_STAGE2:
            print(f"[AI] Stage 2 -> WARNING: Document has {len(raw_ocr_pages)} pages. Truncating to {MAX_PAGES_STAGE2} for scanning.")
            raw_ocr_pages = raw_ocr_pages[:MAX_PAGES_STAGE2]

        best_text = self.assemble_best_text_source(raw_ocr_pages, stage_1_5_result)

        images_payload = []
        if pdf_path:
            img_data = self.get_page_image_payload(pdf_path, 0)
            if img_data:
                try:
                    img_bytes = base64.b64decode(img_data["base64"])
                    images_payload.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
                    print("[AI] Stage 2 -> Vision context enabled (Page 1)")
                except Exception as e:
                    print(f"[AI] Stage 2 -> Vision prep failed: {e}")

        detected_entities = stage_1_result.get("detected_entities", [])
        if not detected_entities:
            types_to_extract = stage_1_result.get("type_tags", ["OTHER"])
        else:
            primary = detected_entities[0]
            types_to_extract = primary.get("type_tags") or ["OTHER"]

        types_to_extract = list(set([t for t in types_to_extract if t not in ["INBOUND", "OUTBOUND", "INTERNAL", "CTX_PRIVATE", "CTX_BUSINESS", "UNKNOWN"]]))
        if not types_to_extract:
            types_to_extract = ["OTHER"]

        stamps_list = []
        if stage_1_5_result:
            stamps_list = stage_1_5_result.get("layer_stamps", [])
        stamps_json_str = json.dumps(stamps_list, indent=2, ensure_ascii=False)

        final_semantic_data = {
            "meta_header": {},
            "bodies": {},
            "repaired_text": ""
        }

        user_identity = f"Private: {self.config.get_private_profile_json()}\nBusiness: {self.config.get_business_profile_json()}"

        sig_data = {}
        if stage_1_5_result and "signatures" in stage_1_5_result:
            sig_data = stage_1_5_result["signatures"]

        zugferd_data = None
        if pdf_path:
            from core.utils.zugferd_extractor import ZugferdExtractor
            zugferd_data = ZugferdExtractor.extract_from_pdf(pdf_path)
            if zugferd_data:
                print(f"[AI] ZUGFeRD XML detected (will be merged as priority ground-truth).")

        if types_to_extract:
            print(f"[AI] Stage 2 (Extraction) [START] -> Types: {', '.join(types_to_extract)}, Vision: {bool(pdf_path)}")

        for i, entity_type in enumerate(types_to_extract):
            include_repair = (i == 0)
            schema = self.get_target_schema(entity_type, include_repair=include_repair)
            
            limit = 100000
            long_doc_hint = ""
            if is_long_document and include_repair:
                long_doc_hint = "CAUTION: This document is long (>10 pages). Please focus on repairing ONLY the first 10 pages in the `repaired_text` field to avoid output truncation."

            zugferd_hint = ""
            if zugferd_data:
                xml_fin = zugferd_data.get("finance_data", {})
                ms = xml_fin.get("monetary_summation", {})
                tax = xml_fin.get("tax_breakdown", [])
                
                hint_parts = []
                if ms.get("grand_total_amount"): hint_parts.append(f"Total: {ms['grand_total_amount']} {xml_fin.get('currency', 'EUR')}")
                if tax:
                    tax_str = ", ".join([f"{t.get('tax_rate')}% on {t.get('tax_basis_amount')}" for t in tax if t.get('tax_rate')])
                    hint_parts.append(f"Tax Breakdown: {tax_str}")
                
                if hint_parts:
                    zugferd_hint = "\n### 3.D ELECTRONIC DATA REFERENCE (ZUGFeRD)\nThe following values were detected in the electronic layer and are CONSIDERED GROUND TRUTH. Use them to calibrate your extraction:\n- " + "\n- ".join(hint_parts) + "\n"

            prompt_repair_instruction = ""
            if include_repair:
                prompt_repair_instruction = prompts.PROMPT_STAGE_2_REPAIR_INSTRUCTION.format(
                    long_doc_hint=long_doc_hint
                )
            
            prompt = prompts.PROMPT_STAGE_2_MASTER.format(
                entity_type=entity_type,
                document_text=best_text[:limit],
                stamps_json=stamps_json_str,
                signature_json=json.dumps(sig_data),
                user_identity=user_identity,
                target_schema_json=schema,
                repair_mission=prompt_repair_instruction,
                zugferd_hint=zugferd_hint
            )
            
            try:
                max_s2_retries = self.config.get_ai_retries()
                s2_attempt = 0
                extraction = None
                
                while s2_attempt <= max_s2_retries:
                    extraction = self.client.generate_json(prompt, stage_label=f"STAGE 2: {entity_type}", images=images_payload)
                    if not extraction:
                        return None

                    original_ai_extraction = copy.deepcopy(extraction)

                    if zugferd_data:
                        extraction = self._apply_zugferd_overlay(extraction, zugferd_data, entity_type)

                    s2_errors = self.validate_semantic_extraction(extraction, entity_type)
                    if not s2_errors:
                        break
                    
                    s2_attempt += 1
                    if s2_attempt <= max_s2_retries:
                        error_msg = "\n".join(f"- {e}" for e in s2_errors)
                        faulty_json_str = json.dumps(original_ai_extraction, indent=2, ensure_ascii=False)
                        prompt += prompts.PROMPT_STAGE_2_CORRECTION.format(
                            faulty_json_str=faulty_json_str,
                            error_msg=error_msg
                        )

                if extraction:
                    TYPE_TO_BODY = {
                        "INVOICE": "finance_body", "CREDIT_NOTE": "finance_body", "RECEIPT": "finance_body",
                        "DUNNING": "finance_body", "UTILITY_BILL": "finance_body", "ORDER": "finance_body",
                        "QUOTE": "finance_body", "ORDER_CONFIRMATION": "finance_body",
                        "BANK_STATEMENT": "finance_body", "TAX_ASSESSMENT": "finance_body",
                        "EXPENSE_REPORT": "finance_body", "PAYSLIP": "finance_body",
                        "CONTRACT": "legal_body", "INSURANCE_POLICY": "legal_body",
                        "OFFICIAL_LETTER": "legal_body", "LEGAL_CORRESPONDENCE": "legal_body",
                        "CERTIFICATE": "legal_body"
                    }
                    target_body_key = TYPE_TO_BODY.get(entity_type.upper(), "other_body")
                    
                    source_bodies = extraction.get("bodies", {}) if isinstance(extraction.get("bodies"), dict) else {}
                    for key, value in extraction.items():
                        if key.endswith("_body"):
                            source_bodies[key] = value
                    
                    for key, value in source_bodies.items():
                        if key == target_body_key:
                            final_semantic_data["bodies"][key] = value
                    
                    if not final_semantic_data["meta_header"]:
                        final_semantic_data["meta_header"] = extraction.get("meta_header", {})
                    else:
                        new_meta = extraction.get("meta_header", {})
                        for k, v in new_meta.items():
                            if v and not final_semantic_data["meta_header"].get(k):
                                final_semantic_data["meta_header"][k] = v
                    
                    if extraction.get("repaired_text"):
                        if not final_semantic_data["repaired_text"] or len(extraction["repaired_text"]) > len(final_semantic_data["repaired_text"]):
                            final_semantic_data["repaired_text"] = extraction["repaired_text"]
            except Exception as e:
                print(f"[AI] Stage 2 Error ({entity_type}): {e}")
                return None

        return final_semantic_data

    def _apply_zugferd_overlay(self, extraction: Dict, zugferd_data: Dict, entity_type: str) -> Dict:
        """
        Deep merge ZUGFeRD ground truth into an extraction result.
        """
        if not zugferd_data or entity_type.upper() not in ["INVOICE", "RECEIPT", "UTILITY_BILL"]:
            return extraction
            
        print(f"[AI] Applying ZUGFeRD Ground-Truth Overlay...")

        xml_meta = zugferd_data.get("meta_data", {})
        if xml_meta:
            if "meta_header" not in extraction:
                extraction["meta_header"] = {}
            for party_key in ["sender", "recipient"]:
                xml_party = xml_meta.get(party_key)
                if xml_party:
                    extraction["meta_header"][party_key] = xml_party
            if "doc_date" in xml_meta: extraction["meta_header"]["doc_date"] = xml_meta["doc_date"]
            if "doc_number" in xml_meta: extraction["meta_header"]["doc_number"] = xml_meta["doc_number"]

        xml_finance = zugferd_data.get("finance_data", {})
        if xml_finance:
            if "bodies" not in extraction: 
                extraction["bodies"] = {}
            extraction["bodies"]["finance_body"] = xml_finance
            
        return extraction

    def validate_semantic_extraction(self, extraction: Dict, entity_type: str) -> List[str]:
        """Validates AI extraction for schema compliance, critical fields, and bank info."""
        from core.utils.validation import validate_iban
        errors = []

        meta = extraction.get("meta_header", {})
        for party_key in ["sender", "recipient"]:
            party = meta.get(party_key, {})
            if isinstance(party, dict):
                for forbidden in ["address", "contact", "identifiers"]:
                    if forbidden in party:
                        errors.append(f"STRICTNESS_ERROR: Nested object '{party_key} -> {forbidden}' is NOT allowed. Flatten all fields.")

        def get_value_at_path(obj: Any, loc: tuple) -> Any:
            curr = obj
            for p in loc:
                if isinstance(curr, dict) and p in curr:
                    curr = curr[p]
                elif isinstance(curr, list) and isinstance(p, int) and p < len(curr):
                    curr = curr[p]
                else:
                    return None
            return curr

        def find_hallucinated_keys(obj: Any, target_key: str) -> List[str]:
            if not isinstance(obj, dict): return []
            from difflib import get_close_matches
            matches = get_close_matches(target_key, obj.keys(), n=3, cutoff=0.5)
            return [m for m in matches if m != target_key]

        try:
            SemanticExtraction.model_validate(extraction)
        except ValidationError as e:
            for error in e.errors():
                loc_tuple = error["loc"]
                loc_str = " -> ".join([str(x) for x in loc_tuple])
                parent_val = get_value_at_path(extraction, loc_tuple[:-1])
                target_key = str(loc_tuple[-1])
                
                if error["type"] == "missing":
                    similar = find_hallucinated_keys(parent_val, target_key)
                    if similar:
                        errors.append(f"MAPPING_ERROR [{loc_str}]: Field '{target_key}' is missing, but I found similar keys: {similar}.")
                    else:
                        errors.append(f"MISSING_FIELD [{loc_str}]: This field is mandatory.")
                else:
                    current_val = get_value_at_path(extraction, loc_tuple)
                    errors.append(f"VALUE_ERROR [{loc_str}]: {error['msg']}. You provided: {current_val}.")

        bodies = extraction.get("bodies", {})
        if isinstance(bodies, dict):
            body_map = {"finance_body": FinanceBody, "legal_body": LegalBody}
            for b_key, b_model in body_map.items():
                b_data = bodies.get(b_key)
                if isinstance(b_data, dict):
                    try:
                        b_model.model_validate(b_data)
                    except ValidationError as ve:
                        for error in ve.errors():
                            loc_tuple = error["loc"]
                            loc_str = f"bodies -> {b_key} -> " + " -> ".join([str(x) for x in loc_tuple])
                            target_key = str(loc_tuple[-1])
                            parent_val = get_value_at_path(b_data, loc_tuple[:-1])
                            
                            if error["type"] == "missing":
                                similar = find_hallucinated_keys(parent_val, target_key)
                                if similar:
                                    errors.append(f"BODY_MAPPING_ERROR [{loc_str}]: Field '{target_key}' is missing in {b_key}, but I found {similar}.")
                                else:
                                    errors.append(f"BODY_MISSING [{loc_str}]: Mandatory field '{target_key}' is missing.")
                            else:
                                val = get_value_at_path(b_data, loc_tuple)
                                errors.append(f"BODY_VALUE_ERROR [{loc_str}]: {error['msg']}. You provided: {val}.")

        # Manual Logic Checks
        sender = meta.get("sender", {})
        if entity_type.upper() in ["INVOICE", "RECEIPT", "DUNNING", "UTILITY_BILL"]:
            iban = sender.get("iban") if isinstance(sender, dict) else None
            if not iban:
                body = extraction.get("finance_body") or (extraction.get("bodies") or {}).get("finance_body", {})
                if isinstance(body, dict):
                    accs = body.get("payment_accounts", [])
                    if accs and isinstance(accs[0], dict):
                        iban = accs[0].get("iban")
            if iban:
                clean_iban = "".join(iban.split()).upper()
                if not validate_iban(clean_iban):
                    errors.append(f"INVALID_IBAN: The identified IBAN '{iban}' has an invalid checksum.")

        if entity_type.upper() == "INVOICE":
            bodies = extraction.get("bodies", {})
            body = bodies.get("finance_body", {})
            
            def get_aliased(d, primary, alias):
                if not isinstance(d, dict): return None
                val = d.get(primary, d.get(alias))
                if val is None or val == "": return None
                try: return Decimal(str(val))
                except: return None

            ms = body.get("monetary_summation", body.get("SpecifiedTradeSettlementMonetarySummation", {}))
            if not isinstance(ms, dict): ms = {}
            
            net_total = get_aliased(ms, "tax_basis_total_amount", "BT-109")
            tax_total = get_aliased(ms, "tax_total_amount", "BT-110")
            grand_total = get_aliased(ms, "grand_total_amount", "BT-112")
            
            if grand_total is None:
                errors.append("MISSING_TOTAL: The 'monetary_summation -> grand_total_amount' is missing.")
            elif net_total is not None and tax_total is not None:
                expected_gross = (net_total + tax_total).quantize(Decimal("0.01"))
                if abs(expected_gross - grand_total) > Decimal("0.05"):
                    errors.append(f"CALCULATION_ERROR: Net ({net_total}) + Tax ({tax_total}) should be {expected_gross}, but you provided {grand_total}.")

        return errors

    def extract_canonical_data(self, primary_type: Any, text: str) -> Dict[str, Any]:
        """Legacy style extraction."""
        if isinstance(primary_type, str):
            try: primary_type = DocType(primary_type.upper())
            except: pass

        model_map = {
            DocType.INVOICE: InvoiceData, DocType.CREDIT_NOTE: InvoiceData,
            DocType.ORDER: InvoiceData, DocType.QUOTE: InvoiceData,
            DocType.ORDER_CONFIRMATION: InvoiceData, DocType.DELIVERY_NOTE: LogisticsData,
            DocType.RECEIPT: InvoiceData, DocType.DUNNING: InvoiceData,
            DocType.BANK_STATEMENT: BankStatementData, DocType.TAX_ASSESSMENT: TaxAssessmentData,
            DocType.EXPENSE_REPORT: ExpenseData, DocType.UTILITY_BILL: UtilityData,
            DocType.CONTRACT: ContractData, DocType.INSURANCE_POLICY: InsuranceData,
            DocType.OFFICIAL_LETTER: LegalMetaData, DocType.LEGAL_CORRESPONDENCE: LegalMetaData,
            DocType.VEHICLE_REGISTRATION: VehicleData, DocType.MEDICAL_DOCUMENT: MedicalData,
            DocType.OTHER: None
        }

        target_model = model_map.get(primary_type)
        val = primary_type.value if hasattr(primary_type, 'value') else str(primary_type)

        specific_schema_hint = ""
        if target_model:
            try:
                schema = target_model.model_json_schema()
                props = schema.get("properties", {})
                field_list = [f'"{k}": "{v.get("type", "string")}"' for k, v in props.items()]
                joined_fields = ",\n               ".join(field_list)
                specific_schema_hint = f' "specific_data": {{\n               // Fields for {val}:\n               {joined_fields}\n          }},'
            except: pass

        prompt = prompts.PROMPT_STAGE_2_EXTRACTION.format(
            val=val,
            specific_schema_hint=specific_schema_hint,
            text_content=text[:100000]
        )

        try:
            raw_data = self.client.generate_json(prompt, stage_label="STAGE 2 EXTRACTION") or {}
            if target_model and "specific_data" in raw_data:
                try:
                    spec_data = raw_data.get("specific_data", {})
                    if spec_data:
                         validated_spec = target_model(**spec_data)
                         raw_data["specific_data"] = validated_spec.model_dump()
                except: pass
            return raw_data
        except: return {}

    def generate_smart_filename(self, semantic_data: Dict, entity_types: List[str]) -> str:
        """
        Phase 2.4: Smart Filename Generation.
        """
        if semantic_data is None:
            return "0000-00-00__Unknown__DOC.pdf"

        # 1. Date Extraction
        meta = semantic_data.get("meta_header", {})
        doc_date = meta.get("doc_date", "0000-00-00")
        
        # 2. Entity Name
        sender = meta.get("sender", {})
        entity_name = sender.get("name", "Unknown")
        entity_name = re.sub(r'[^\w\s]', '', entity_name).replace(' ', '_')[:30]

        # 3. Type
        doc_type = "DOC"
        if entity_types:
            doc_type = entity_types[0].upper()
        
        return f"{doc_date}__{entity_name}__{doc_type}.pdf"
