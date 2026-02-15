from typing import Any, Dict, Optional, Tuple
import json
import io
import os
import fitz  # PyMuPDF
from pydantic import BaseModel

class ExchangePayload(BaseModel):
    """Universal container for KPaperFlux portable data."""
    version: str = "1.0"
    type: str  # "report_definition", "smart_list", "workflow_playbook", "layout", "filter_tree"
    payload: Dict[str, Any]
    origin: str = "KPaperFlux"

class ExchangeService:
    """Central service for embedding and extracting machine-readable state from files."""
    
    ATTACHMENT_NAME = "kpaperflux_metadata.json"

    @staticmethod
    def embed_in_pdf(pdf_bytes: bytes, payload_type: str, data: Dict[str, Any]) -> bytes:
        """Embeds a KPaperFlux payload into a PDF byte stream."""
        payload = ExchangePayload(type=payload_type, payload=data)
        payload_json = payload.model_dump_json(indent=2).encode("utf-8")
        
        try:
            with fitz.open("pdf", pdf_bytes) as doc:
                # Remove existing metadata attachment if any to keep it clean
                for i in range(doc.embfile_count()):
                    if doc.embfile_info(i)["name"] == ExchangeService.ATTACHMENT_NAME:
                        doc.embfile_del(i)
                        break
                
                doc.embfile_add(
                    ExchangeService.ATTACHMENT_NAME,
                    payload_json,
                    filename=ExchangeService.ATTACHMENT_NAME,
                    desc=f"KPaperFlux {payload_type} Metadata"
                )
                return doc.tobytes()
        except Exception as e:
            print(f"ExchangeService: Failed to embed in PDF: {e}")
            return pdf_bytes

    @staticmethod
    def extract_from_pdf(path: str) -> Optional[ExchangePayload]:
        """Extracts a KPaperFlux payload from a PDF file."""
        try:
            with fitz.open(path) as doc:
                for i in range(doc.embfile_count()):
                    if doc.embfile_info(i)["name"] == ExchangeService.ATTACHMENT_NAME:
                        data = doc.embfile_get(i)
                        return ExchangePayload.model_validate_json(data)
                        
        except Exception as e:
            print(f"ExchangeService: Failed to extract from PDF: {e}")
        return None

    @staticmethod
    def save_to_file(payload_type: str, data: Dict[str, Any], target_path: str):
        """Saves a standalone JSON exchange file."""
        payload = ExchangePayload(type=payload_type, payload=data)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(payload.model_dump_json(indent=2))

    @staticmethod
    def load_from_file(path: str) -> Optional[ExchangePayload]:
        """Loads a KPaperFlux payload from a JSON or PDF file."""
        if path.lower().endswith(".pdf"):
            return ExchangeService.extract_from_pdf(path)
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                return ExchangePayload.model_validate_json(f.read())
        except Exception as e:
            print(f"ExchangeService: Failed to load from file {path}: {e}")
        return None
