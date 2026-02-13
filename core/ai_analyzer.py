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
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from core.ai.client import AIClient
from core.ai.stage1 import Stage1Processor
from core.ai.stage2 import Stage2Processor
from core.ai import prompts
from core.config import AppConfig
from core.models.identity import IdentityProfile
from core.models.types import DocType


class AIAnalyzer:
    """
    Analyzes document text using Google Gemini to extract structured data.
    
    Provides high-level methods for document classification, semantic extraction,
    and adaptive scan strategies.
    """

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash") -> None:
        """
        Initializes the AIAnalyzer.
        """
        self.config = AppConfig()
        self.client = AIClient(api_key, model_name)
        self.stage1 = Stage1Processor(self.client, self.config)
        self.stage2 = Stage2Processor(self.client, self.config)

    @classmethod
    def get_adaptive_delay(cls) -> float:
        """
        Retrieves the current adaptive delay value from AIClient.
        """
        return AIClient.get_adaptive_delay()

    def list_models(self) -> List[str]:
        """
        Fetches available models via the AIClient.
        """
        return self.client.list_models()

    def ask_type_check(self, pre_flight_pages: List[str]) -> Dict[str, Any]:
        """Delegates to Stage1Processor."""
        return self.stage1.ask_type_check(pre_flight_pages)

    def run_stage_1_adaptive(self, pages_text: List[str], private_id: Optional[IdentityProfile], business_id: Optional[IdentityProfile]) -> Dict[str, Any]:
        """Delegates to Stage1Processor."""
        return self.stage1.run_stage_1_adaptive(pages_text, private_id, business_id)

    def _generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        """
        Executes a JSON extraction request via the client.
        """
        return self.client.generate_json(prompt, stage_label, images)

    def identify_entities(self, text: str, semantic_data: Optional[Dict[str, Any]] = None, detected_entities: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Delegates to Stage1Processor."""
        return self.stage1.identify_entities(text, semantic_data, detected_entities)

    def refine_semantic_entities(self, semantic_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Delegates to Stage1Processor."""
        return self.stage1.refine_semantic_entities(semantic_data)

    def parse_identity_signature(self, text: str) -> Optional[IdentityProfile]:
        """Delegates to Stage2Processor."""
        return self.stage2.parse_identity_signature(text)

    def classify_structure(self, pages_text: List[str],
                          private_id: Optional[IdentityProfile],
                          business_id: Optional[IdentityProfile],
                          mode: str = "FULL_READ_MODE") -> Dict[str, Any]:
        """Delegates to Stage1Processor."""
        return self.stage1.classify_structure(pages_text, private_id, business_id, mode)

    def validate_classification(self, result: dict, ocr_pages: List[str], priv_id=None, bus_id=None) -> List[str]:
        """Delegates to Stage1Processor."""
        return self.stage1.validate_classification(result, ocr_pages, priv_id, bus_id)

    # ==============================================================================
    # STAGE 2: SCHEMA HELPERS (Reusable Components)
    # ==============================================================================

    @staticmethod
    def get_address_schema() -> Dict:
        """Delegates to Stage2Processor."""
        return Stage2Processor.get_address_schema()

    @staticmethod
    def get_contact_schema() -> Dict:
        """Delegates to Stage2Processor."""
        return Stage2Processor.get_contact_schema()

    @classmethod
    def get_party_schema(cls) -> Dict:
        """Delegates to Stage2Processor."""
        return Stage2Processor.get_party_schema()

    @staticmethod
    def get_bank_account_schema() -> Dict:
        """Delegates to Stage2Processor."""
        return Stage2Processor.get_bank_account_schema()

    def get_target_schema(self, entity_type: str, include_repair: bool = True) -> str:
        """Delegates to Stage2Processor."""
        return self.stage2.get_target_schema(entity_type, include_repair)

    def assemble_best_text_source(self, raw_ocr_pages: List[str], stage_1_5_result: Dict) -> str:
        """Delegates to Stage2Processor."""
        return self.stage2.assemble_best_text_source(raw_ocr_pages, stage_1_5_result)

    def get_page_image_payload(self, pdf_path: str, page_index: int = 0) -> Optional[Dict]:
        """Delegates to Stage2Processor."""
        return self.stage2.get_page_image_payload(pdf_path, page_index)

    def run_stage_2(self, raw_ocr_pages: List[str], stage_1_result: Dict, stage_1_5_result: Dict, pdf_path: Optional[str] = None) -> Dict:
        """Delegates to Stage2Processor."""
        return self.stage2.run_stage_2(raw_ocr_pages, stage_1_result, stage_1_5_result, pdf_path)

    def _apply_zugferd_overlay(self, extraction: Dict, zugferd_data: Dict, entity_type: str) -> Dict:
        """Delegates to Stage2Processor."""
        return self.stage2._apply_zugferd_overlay(extraction, zugferd_data, entity_type)

    def validate_semantic_extraction(self, extraction: Dict, entity_type: str) -> List[str]:
        """Delegates to Stage2Processor."""
        return self.stage2.validate_semantic_extraction(extraction, entity_type)

    def generate_smart_filename(self, semantic_data: Any, entity_types: List[str]) -> str:
        """Delegates to Stage2Processor."""
        return self.stage2.generate_smart_filename(semantic_data, entity_types)

