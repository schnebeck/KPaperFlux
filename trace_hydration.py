
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict
from core.models.semantic import SemanticExtraction
from core.models.virtual import VirtualDocument as Document

# Setup logging as in database.py
logger = logging.getLogger("Test")

raw_json = """
{"meta_header": {"sender": {"name": "Modellbau Berthold", "company": null, "street": null, "zip_code": null, "city": null, "country": null, "phone": null, "email": null, "iban": "DE87765600600003200132", "bic": "GENODEF1ANS", "bank_name": "VR-Bank Mittelfranken Mitte eG", "tax_id": null, "address": {"raw_string": "Gewerbering 6, 91629 Weihenzell", "street": "Gewerbering", "house_number": "6", "zip_code": "91629", "city": "Weihenzell", "country": "DE"}, "contact": {"phones": ["+49 9802-9586677"], "emails": ["info@mb-rc.de"], "websites": ["www.mb-rc.de"]}, "identifiers": {"vat_id": "DE328965576"}}, "recipient": {"name": "TEWISS GmbH", "company": null, "street": null, "zip_code": null, "city": null, "country": null, "phone": null, "email": null, "iban": null, "bic": null, "bank_name": null, "tax_id": null, "address": {"raw_string": "An der Universit\u00e4t 2, 30823 Garbsen, Germany", "street": "An der Universit\u00e4t", "house_number": "2", "zip_code": "30823", "city": "Garbsen", "country": "DE"}, "contact": {"contact_person": "Thorsten Schnebeck"}}, "doc_date": "2025-06-13", "doc_number": null, "language": "en", "summary": "Invoice from Modellbau Berthold to TEWISS GmbH for various steel wires and shipping costs.", "subject_context": {"entity_name": "Steel Wire and Shipping", "entity_type": "BUSINESS", "relation": "Buyer"}}, "bodies": {"finance_body": {"total_gross": 16.9, "total_net": 14.2, "total_tax": 2.7, "currency": "EUR", "payment_method": null, "due_date": null, "invoice_number": "202559054", "order_number": "25-13179-58503", "customer_id": null, "line_items": [{"pos_no": "1", "description": "Stahldraht Federstahldraht von 0,3 mm bis 6 mm verschiedene Mengen [1,5mm - 1 St\u00fcck]", "quantity": 1, "unit": "St\u00fcck", "unit_price": 2.9, "total_price": 2.9}, {"pos_no": "2", "description": "Stahldraht Federstahldraht von 0,3 mm bis 6 mm verschiedene Mengen [0,5mm - 1 St\u00fcck]", "quantity": 1, "unit": "St\u00fcck", "unit_price": 2.5, "total_price": 2.5}, {"pos_no": "3", "description": "Stahldraht Federstahldraht von 0,3 mm bis 6 mm verschiedene Mengen [1,2mm - 1 St\u00fcck]", "quantity": 1, "unit": "St\u00fcck", "unit_price": 2.8, "total_price": 2.8}, {"pos_no": "4", "description": "Stahldraht Federstahldraht von 0,3 mm bis 6 mm verschiedene Mengen [0,8mm - 1 St\u00fcck]", "quantity": 1, "unit": "St\u00fcck", "unit_price": 2.8, "total_price": 2.8}, {"pos_no": "5", "description": "Versandkosten", "quantity": 1, "unit": "pcs", "unit_price": 5.9, "total_price": 5.9}], "payment_accounts": [{"bank_name": "VR-Bank Mittelfranken Mitte eG", "account_holder": "Modellbau Berthold", "iban": "DE87 7656 0060 0003 2001 32", "bic": "GENODEF1ANS"}], "payment_details": {"payment_terms": "Paid on 2025-06-13 via eBay payment processing."}, "tax_details": {}}}, "workflow": {"is_verified": false, "verified_at": null, "verified_by": null, "current_step": "NEW", "history": [], "pkv_eligible": false, "pkv_status": null, "signature_detected": false}, "repaired_text": "...", "type_tags": [], "direction": "INBOUND", "tenant_context": "PRIVATE", "visual_audit": {"audit_summary": {"was_stamp_interference": false, "has_handwriting": false}, "layer_stamps": [], "integrity": {"is_type_match": true, "suggested_types": ["INVOICE"]}, "arbiter_decision": {"raw_ocr_quality_score": 95, "ai_vision_quality_score": 98, "primary_source_recommendation": "RAW_OCR"}, "meta_mode": "STAMP_ONLY"}}
"""

semantic_raw = json.loads(raw_json)

# Hydrate Semantic Model
semantic_data = None
if semantic_raw:
    try:
        semantic_data = SemanticExtraction(**semantic_raw)
        print("Hydration Successful")
    except Exception as e:
        print(f"Hydration Failed: {e}")

if semantic_data:
    print(f"IBAN: {semantic_data.meta_header.sender.iban}")
    print(f"Total Gross: {semantic_data.bodies['finance_body'].total_gross}")
