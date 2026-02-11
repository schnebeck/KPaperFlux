"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           scripts/patch_demo_invoices.py
Version:        2.1.1
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Updates demo PDF invoices with test identities from the 'doc'
                profile configuration. Synchronizes ZUGFeRD XML and 
                rendered content. Ensures EN 16931 alignment.
------------------------------------------------------------------------------
"""

import json
import logging
import os
import traceback
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pikepdf
from lxml import etree

from core.config import AppConfig
from core.models.semantic import (
    AddressInfo,
    FinanceBody,
    LineItem,
    MetaHeader,
    MonetarySummation,
    SemanticExtraction,
)
from core.pdf_renderer import ProfessionalPdfRenderer
from core.utils.zugferd_extractor import ZugferdExtractor

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PatchDemos")

# ZUGFeRD Namespaces
NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}


def update_xml_party(node: etree._Element, identity: Dict[str, Any]) -> None:
    """
    Updates a party node (Seller/Buyer) in ZUGFeRD XML with identity details.

    Args:
        node: The XML node to update.
        identity: Dictionary containing name, company, street, zip, city, country.
    """
    if node is None:
        return

    name_node = node.find("ram:Name", NS)
    if name_node is not None:
        # Priority: company, then name
        name_node.text = identity.get("company") or identity.get("name") or ""

    addr = node.find("ram:PostalTradeAddress", NS)
    if addr is not None:
        mappings = [
            ("ram:LineOne", "street"),
            ("ram:PostcodeCode", "zip"),
            ("ram:CityName", "city"),
            ("ram:CountryID", "country"),
        ]
        for tag, key in mappings:
            n = addr.find(tag, NS)
            if n is not None:
                val = identity.get(key)
                if val is None and key == "zip":
                    val = identity.get("zip_code")
                n.text = str(val or "")


def load_identities() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Loads test identities from the application's 'doc' profile configuration.

    Returns:
        A tuple of (private_identity_dict, business_identity_dict).
    """
    config = AppConfig(profile="doc")

    def get_val_safety(keywords: List[str], idx: int, default: str) -> str:
        try:
            return keywords[idx] if len(keywords) > idx else default
        except (IndexError, TypeError):
            return default

    # Private Profile
    try:
        private_raw = json.loads(config.get_private_profile_json())
        kw = private_raw.get("address_keywords", [])
        private_id = {
            "name": private_raw.get("name", "Max Mustermann"),
            "street": get_val_safety(kw, 0, "Musterweg 1"),
            "zip": get_val_safety(kw, 1, "12345"),
            "city": get_val_safety(kw, 2, "Musterstadt"),
            "country": "DE",
            "iban": private_raw.get("iban", [""])[0] if private_raw.get("iban") else "",
        }
    except Exception as e:
        logger.warning(f"Failed to parse private profile from config: {e}. Using defaults.")
        private_id = {
            "name": "Max Mustermann",
            "street": "Musterweg 1",
            "zip": "12345",
            "city": "Musterstadt",
            "country": "DE",
        }

    # Business Profile
    try:
        business_raw = json.loads(config.get_business_profile_json())
        kw = business_raw.get("address_keywords", [])
        business_id = {
            "company": business_raw.get("company_name", "Muster Corp GmbH"),
            "name": business_raw.get("name", "Muster Corp GmbH"),
            "street": get_val_safety(kw, 0, "Businesspark A"),
            "zip": get_val_safety(kw, 1, "54321"),
            "city": get_val_safety(kw, 2, "Industriestadt"),
            "country": "DE",
            "vat_id": business_raw.get("vat_id"),
            "iban": business_raw.get("iban", [""])[0] if business_raw.get("iban") else "",
        }
    except Exception as e:
        logger.warning(f"Failed to parse business profile from config: {e}. Using defaults.")
        business_id = {
            "company": "Muster Corp GmbH",
            "name": "Muster Corp GmbH",
            "street": "Businesspark A",
            "zip": "54321",
            "city": "Industriestadt",
            "country": "DE",
        }

    return private_id, business_id


def patch_demos() -> None:
    """
    Main loop to process and patch 20 demo invoices.
    Reads from backup_dir and writes to original_dir.
    """
    base_path = Path("/home/schnebeck/Dokumente/Projects/KPaperFlux")
    backup_dir = base_path / "tests/resources/demo_invoices_complex_backup"
    original_dir = base_path / "tests/resources/demo_invoices_complex"

    if not backup_dir.exists():
        logger.error(f"Backup directory not found: {backup_dir}")
        return

    original_dir.mkdir(parents=True, exist_ok=True)
    private_id, business_id = load_identities()

    for i in range(1, 21):
        suffix = "de" if i % 2 != 0 else "en"
        filename = f"Demo_{i:02d}_INVOICE_{suffix}.pdf"
        src_path = backup_dir / filename
        dst_path = original_dir / filename

        if not src_path.exists():
            continue

        logger.info(f"Processing {filename}...")

        # 1. Extract original XML via pikepdf
        original_xml_bytes: Optional[bytes] = None
        xml_filename = "factur-x.xml"
        try:
            with pikepdf.open(src_path) as pdf:
                for name, attachment in pdf.attachments.items():
                    if name.lower() in ["factur-x.xml", "zugferd-invoice.xml"]:
                        # Access stream via underlying object attributes
                        obj = attachment.obj
                        if hasattr(obj, "EF"):
                            if hasattr(obj.EF, "F"):
                                original_xml_bytes = obj.EF.F.read_bytes()
                            elif hasattr(obj.EF, "UF"):
                                original_xml_bytes = obj.EF.UF.read_bytes()
                        xml_filename = name
                        break
        except Exception as e:
            logger.error(f"  Error reading attachments from {filename}: {e}")

        # 2. Extract structured metadata via ZugferdExtractor
        raw_data = ZugferdExtractor.extract_from_pdf(str(src_path))
        if not raw_data:
            logger.warning(f"  No ZUGFeRD data found in {filename}, using defaults.")
            raw_data = {
                "meta_data": {
                    "sender": {"company": f"Vendor {i}"},
                    "doc_number": f"D-{i:03d}",
                    "doc_date": "2026-02-12",
                },
                "finance_data": {"line_items": []},
            }

        # 3. Decision Logic: Direction and Tenant Context
        # i=5: OUTBOUND/PRIVATE (Max sends an invoice)
        # i odd: INBOUND/BUSINESS (Muster Corp receives an invoice)
        # i even: INBOUND/PRIVATE (Max receives an invoice)
        if i == 5:
            direction, ctx = "OUTBOUND", "PRIVATE"
            sender_id, recipient_id = private_id, (raw_data["meta_data"].get("recipient") or {"name": "Anton Nachbar"})
        elif i % 2 != 0:
            direction, ctx = "INBOUND", "BUSINESS"
            sender_id, recipient_id = (raw_data["meta_data"].get("sender") or {"company": f"Vendor {i}"}), business_id
        else:
            direction, ctx = "INBOUND", "PRIVATE"
            sender_id, recipient_id = (raw_data["meta_data"].get("sender") or {"company": f"Vendor {i}"}), private_id

        # 4. Modify XML
        modified_xml_bytes: Optional[bytes] = None
        if original_xml_bytes:
            try:
                root = etree.fromstring(original_xml_bytes)
                party_xpath = "//ram:SellerTradeParty" if direction == "OUTBOUND" else "//ram:BuyerTradeParty"
                party_nodes = root.xpath(party_xpath, namespaces=NS)
                if party_nodes:
                    update_xml_party(party_nodes[0], sender_id if direction == "OUTBOUND" else recipient_id)
                
                modified_xml_bytes = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
            except Exception as e:
                logger.error(f"  Error modifying XML in {filename}: {e}")

        # 5. Build Semantic Model for Rendering
        try:
            extraction = SemanticExtraction(
                direction=direction,
                tenant_context=ctx,
                meta_header=MetaHeader(
                    sender=AddressInfo(**sender_id),
                    recipient=AddressInfo(**recipient_id),
                    doc_date=raw_data["meta_data"].get("doc_date"),
                    doc_number=raw_data["meta_data"].get("doc_number"),
                    language=suffix
                ),
                type_tags=["INVOICE"]
            )

            fin = raw_data["finance_data"]
            fb = FinanceBody(
                invoice_number=fin.get("invoice_number"),
                invoice_date=fin.get("invoice_date"),
                currency=fin.get("currency", "EUR")
            )

            for item in fin.get("line_items", []):
                fb.line_items.append(LineItem(
                    pos=str(item.get("pos", "")),
                    description=item.get("description"),
                    quantity=Decimal(str(item.get("quantity") or 1)),
                    unit=item.get("unit") or "C62",
                    unit_price=Decimal(str(item.get("unit_price") or 0)),
                    total_price=Decimal(str(item.get("total_price") or 0))
                ))

            ms = fin.get("monetary_summation", {})
            fb.monetary_summation = MonetarySummation(
                line_total_amount=Decimal(str(ms.get("line_total_amount") or 0)),
                grand_total_amount=Decimal(str(ms.get("grand_total_amount") or 0)),
                tax_total_amount=Decimal(str(ms.get("tax_total_amount") or 0)),
                tax_basis_total_amount=Decimal(str(ms.get("tax_basis_total_amount") or 0))
            )
            # Re-calculating safety check for grand_total if 0
            if fb.monetary_summation.grand_total_amount == 0 and fb.monetary_summation.line_total_amount > 0:
                 fb.monetary_summation.grand_total_amount = fb.monetary_summation.line_total_amount * Decimal("1.19")

            extraction.bodies = {"finance_body": fb}

            # 6. Render
            temp_pdf = f"temp_{i}.pdf"
            renderer = ProfessionalPdfRenderer(temp_pdf, locale=suffix)
            renderer.render_document(extraction)

            # 7. Merge and Save
            with pikepdf.open(temp_pdf) as pdf:
                if modified_xml_bytes:
                    pdf.attachments[xml_filename] = pikepdf.AttachedFileSpec(
                        pdf, modified_xml_bytes, filename=xml_filename
                    )
                    logger.info(f"  Patched ZUGFeRD: {xml_filename}")
                pdf.save(dst_path)
            
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

        except Exception as e:
            logger.error(f"  Fatal error in {filename}: {e}")
            logger.debug(traceback.format_exc())

    logger.info("Patching process completed.")


if __name__ == "__main__":
    patch_demos()
