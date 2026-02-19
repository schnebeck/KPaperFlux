"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai/stage1.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Stage 1 Processor (Classification & Segmentation).
                Handles pre-flight checks, adaptive scan strategies, 
                and logical document splitting.
------------------------------------------------------------------------------
"""

import json
from typing import Any, Dict, List, Optional
from core.logger import get_logger

logger = get_logger("ai.stage1")

from core.models.identity import IdentityProfile
from core.ai import prompts


class Stage1Processor:
    """
    Orchestrates the first phase of AI analysis: identifying what a file contains
    and how it should be split into logical documents.
    """

    def __init__(self, client, config) -> None:
        """
        Initializes the Stage 1 Processor.

        Args:
            client: An instance of AIClient.
            config: An instance of AppConfig.
        """
        self.client = client
        self.config = config

    def extract_headers_footers(self, ocr_pages: List[str], header_ratio: float = 0.15, footer_ratio: float = 0.10) -> List[str]:
        """
        Reduces the text of each page to the top and bottom regions to save tokens.
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

    def ask_type_check(self, pre_flight_pages: List[str]) -> Dict[str, Any]:
        """
        Phase 1.0 (Pre-Flight): Determines the general document strategy.
        """
        content = "\n".join([f"--- PAGE {i+1} ---\n{p}" for i, p in enumerate(pre_flight_pages)])
        prompt = prompts.PROMPT_STAGE_1_0_PREFLIGHT.format(content=content)
        result = self.client.generate_json(prompt, stage_label="Stage 1.0 (Pre-Flight)")
        return result or {}

    def run_stage_1_adaptive(self, pages_text: List[str], private_id: Optional[IdentityProfile], business_id: Optional[IdentityProfile]) -> Dict[str, Any]:
        """
        Intelligent Controller for Stage 1. Selects optimal scan strategy.
        """
        total_pages = len(pages_text)
        if total_pages == 0:
            return {}

        # --- PHASE A: PRE-FLIGHT ---
        logger.info(f"[AI] Stage 1.0 (Pre-Flight) [START] -> Analyzing {total_pages} pages...")
        pre_flight_pages = pages_text[:3]
        pre_flight_res = self.ask_type_check(pre_flight_pages)
        logger.info("[AI] Stage 1.0 (Pre-Flight) [DONE]")

        primary_type = pre_flight_res.get("primary_type", "OTHER")
        is_stack_suspicion = pre_flight_res.get("looks_like_stack", False)

        logger.info(f"[AI] Stage 1.0 (Pre-Flight) -> {total_pages} Pages. Type: {primary_type}. Stack: {is_stack_suspicion}")

        # --- PHASE B: ROUTING ---
        scan_strategy = "FULL_READ_MODE"
        final_pages_to_scan = []

        if primary_type in ["MANUAL", "DATASHEET", "BOOK", "CATALOG"]:
            scan_strategy = "SANDWICH_MODE"
            indices = [0, 1, 2, total_pages - 1]
            indices = sorted(list(set(i for i in indices if i < total_pages)))
            for i in indices:
                final_pages_to_scan.append(pages_text[i])
        elif total_pages > 10 or is_stack_suspicion:
            scan_strategy = "HEADER_SCAN_MODE"
            final_pages_to_scan = self.extract_headers_footers(pages_text)
        else:
            scan_strategy = "FULL_READ_MODE"
            final_pages_to_scan = pages_text

        # --- PHASE C: EXECUTION ---
        return self.classify_structure(final_pages_to_scan, private_id, business_id, mode=scan_strategy, total_pages_ref=total_pages)

    def classify_structure(self, pages_text: List[str], private_id: Optional[IdentityProfile], business_id: Optional[IdentityProfile], mode: str = "FULL_READ_MODE", total_pages_ref: int = None) -> Dict[str, Any]:
        """
        Phase 1.1: Master Classification and Segmentation.
        """
        def fmt_id(p: Optional[IdentityProfile]):
            if not p:
                return "Not Configured"
            return f"{p.name} ({p.company_name}) | Keywords: {', '.join(p.address_keywords)}"

        identity_json_str = json.dumps({
            "PRIVATE_ENTITY": fmt_id(private_id),
            "BUSINESS_ENTITY": fmt_id(business_id)
        }, indent=2)

        analysis_text = "\n\n".join([f"--- PAGE {i+1} ---\n{p}" for i, p in enumerate(pages_text)])
        prompt_str = prompts.PROMPT_STAGE_1_1_CLASSIFICATION.format(
            identity_json_str=identity_json_str,
            mode=mode,
            analysis_text=analysis_text
        )

        try:
            max_retries = self.config.get_ai_retries()
            attempt = 0
            result = self.client.generate_json(prompt_str, stage_label="Stage 1.1 (Classification)")

            while attempt < max_retries:
                if not result:
                    break

                errors = self.validate_classification(result, pages_text, private_id, business_id)
                if not errors:
                    return result

                logger.info(f"[AI] Stage 1.1 Validation Failed (Attempt {attempt+1}): {errors}")
                attempt += 1

                error_summary = "\n".join(f"- {e}" for e in errors)
                correction_prompt = prompts.PROMPT_REFINEMENT_CORRECTION.format(
                    error_summary=error_summary,
                    validation_checks="Ensure all pages are covered and context is correct."
                )
                
                prompt_with_history = prompt_str + f"\n\n### PREVIOUS ATTEMPT ###\n{json.dumps(result)}\n\n{correction_prompt}"
                result = self.client.generate_json(prompt_with_history, stage_label=f"STAGE 1.1 CORRECTION {attempt}")

            return result or {}
        except Exception as e:
            logger.info(f"[AI] Classification Failed: {e}")
            return {}

    def validate_classification(self, result: Dict[str, Any], ocr_pages: List[str], priv_id: Optional[IdentityProfile] = None, bus_id: Optional[IdentityProfile] = None) -> List[str]:
        """
        Validates AI response for logical errors and performs AI-backed plausibility checks
        if analytical matching fails.
        """
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

        # 2. Context Sanity Check (Analytical Level)
        analytical_errors = validate_ai_structure_response(result, ocr_pages, priv_id, bus_id)
        
        # 3. Plausibility Arbiter (AI-Agentic Level)
        # If we have analytical errors, check if they are "plausible" anyway before reporting failure.
        if analytical_errors:
            logger.info(f"[AI] Analytical validation found {len(analytical_errors)} issues. Invoking AI Arbiter for second opinion...")
            real_errors = []
            
            for err in analytical_errors:
                # Identify if this is a classification error (Context or Direction)
                is_evaluable = "CONTEXT_ERROR" in err or "DIRECTION_ERROR" in err
                
                if is_evaluable:
                    match_found = False
                    for ent in entities:
                        ctx = ent.get("tenant_context")
                        direction = ent.get("direction")
                        pages = ent.get("page_indices", [])
                        if not pages: continue
                        
                        # Only check if this is likely the entity the error refers to
                        if f"Page {pages[0]}" in err:
                            # The Arbiter now checks BOTH context and direction in one go
                            is_plausible = self.run_plausibility_arbiter(ctx, direction, pages[0], ocr_pages, priv_id, bus_id)
                            if is_plausible:
                                logger.info(f"[AI] Arbiter OVERRIDE: {ctx}/{direction} for Page {pages[0]} is PLAUSIBLE. Ignoring analytical error.")
                                match_found = True
                                break
                    
                    if not match_found:
                        real_errors.append(err)
                else:
                    real_errors.append(err)
            errors.extend(real_errors)
        else:
            errors.extend(analytical_errors)

        return errors

    def run_plausibility_arbiter(self, context: str, direction: str, page_num: int, ocr_pages: List[str], priv_id: Optional[IdentityProfile], bus_id: Optional[IdentityProfile]) -> bool:
        """
        Invokes a small AI sub-task to check if a context/direction classification makes sense
        even if the exact address strings don't match.
        """
        try:
            page_idx = page_num - 1
            if page_idx < 0 or page_idx >= len(ocr_pages):
                return False
            
            page_text = ocr_pages[page_idx]
            # Limit text for arbiter
            page_text = page_text[:2000] # Usually first 2k chars are enough for header analysis
            
            target_profile = bus_id if context == "BUSINESS" else priv_id
            profile_info = "None"
            if target_profile:
                profile_info = f"Name: {target_profile.name}, Company: {target_profile.company_name}, Keywords: {', '.join(target_profile.address_keywords)}"
            
            prompt = prompts.PROMPT_PLAUSIBILITY_ARBITER.format(
                context=f"{context} ({direction})",
                profile_info=profile_info,
                page_text=page_text
            )
            
            res = self.client.generate_json(prompt, stage_label=f"Arbiter Check (P{page_num})")
            if res and res.get("is_plausible") is True:
                return True
        except Exception as e:
            logger.warning(f"[AI] Arbiter failed: {e}")
            
        return False

    def identify_entities(self, text: str, semantic_data: Optional[Dict[str, Any]] = None, detected_entities: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Phase 1.2: Logical Entity Identification/Refinement.
        """
        if semantic_data and isinstance(semantic_data, dict) and "pages" in semantic_data:
            return self.refine_semantic_entities(semantic_data)
        return self._identify_entities_text_fallback(text, semantic_data, detected_entities)

    def refine_semantic_entities(self, semantic_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Analyzes semantic structure to identify logical boundaries.
        """
        if hasattr(semantic_data, "model_dump"):
            semantic_data = semantic_data.model_dump()
            
        summary = semantic_data.get("summary", {})
        dt = summary.get("classification", "OTHER")
        existing_types_str = ", ".join(dt) if isinstance(dt, list) else str(dt)

        json_str = json.dumps(semantic_data, ensure_ascii=False, default=str)
        prompt_str = prompts.PROMPT_STAGE_1_2_REFINEMENT.format(
            existing_types_str=existing_types_str,
            json_str=json_str
        )

        try:
            result = self.client.generate_json(prompt_str, stage_label="STAGE 1.2 REFINEMENT")
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "entities" in result:
                return result["entities"]
            return []
        except Exception as e:
            logger.info(f"[AI] Refinement Failed: {e}")
            return []

    def _identify_entities_text_fallback(self, text: str, semantic_data: dict = None, detected_entities: List[dict] = None) -> List[dict]:
        """
        Splits a text stream into logical documents.
        """
        if hasattr(semantic_data, "model_dump"):
            semantic_data = semantic_data.model_dump()

        if not text:
            return []

        structural_hints = ""
        if detected_entities:
             entity_types = [str(t) for t in (ent.get("classification") for ent in detected_entities) if t]
             structural_hints = f"\n### PREVIOUS ANALYSIS HINTS\nThe classification stage (Stage 1.1) already identified these types: {', '.join(entity_types)}.\nEnsure the output contains boundaries for these documents.\n"
        elif semantic_data:
             summary = semantic_data.get("summary", {})
             entity_types = summary.get("classification", [])
             if isinstance(entity_types, list) and entity_types:
                 entity_types = [str(t) for t in entity_types if t]
                 structural_hints = f"\n### PREVIOUS ANALYSIS HINTS\nThe system previously detected the following Classification: {', '.join(entity_types)}.\nUse this to guide your splitting."

        allowed_types = [
            "QUOTE", "ORDER", "ORDER_CONFIRMATION", "DELIVERY_NOTE", "INVOICE", "CREDIT_NOTE", "RECEIPT", "DUNNING",
            "BANK_STATEMENT", "TAX_ASSESSMENT", "EXPENSE_REPORT", "UTILITY_BILL",
            "CONTRACT", "INSURANCE_POLICY", "PAYSLIP", "LEGAL_CORRESPONDENCE", "OFFICIAL_LETTER",
            "CERTIFICATE", "MEDICAL_DOCUMENT", "VEHICLE_REGISTRATION", "APPLICATION", "NOTE", "OTHER"
        ]

        prompt_str = prompts.PROMPT_STAGE_1_2_SPLIT.format(
            structural_hints=structural_hints,
            allowed_types_str=", ".join(allowed_types),
            text_content=text[:100000]
        )

        try:
            result = self.client.generate_json(prompt_str, stage_label="STAGE 1.2 SPLIT REQUEST")
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "entities" in result:
                return result["entities"]
            return []
        except Exception as e:
            logger.info(f"[AI] Entity Splitting Failed: {e}")
            return []
