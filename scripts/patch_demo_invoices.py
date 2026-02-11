"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           scripts/patch_demo_invoices.py
Version:        2.3.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Comprehensive test data generator. Creates 20 base invoices
                (10 DE, 10 EN) with high variety. Adds 5 special scanned 
                documents with "SCANNED" stamp for OCR/Stage 0 testing.
------------------------------------------------------------------------------
"""

import json
import logging
import os
import random
import traceback
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pikepdf
from lxml import etree
from PIL import Image, ImageFilter, ImageDraw, ImageFont
from pdf2image import convert_from_path

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

# --- VENDOR PROFILES FOR VARIETY ---
VENDORS = [
    {
        "company": "AlpenGlück Bau GmbH",
        "street": "Gipfelweg 7", "zip": "6020", "city": "Innsbruck", "country": "AT",
        "banks": [{"iban": "AT123456789012345678", "bank_name": "Tiroler Bank"}]
    },
    {
        "company": "Global Tech Logistics Ltd",
        "street": "100 Fleet Street", "zip": "EC4Y 1QE", "city": "London", "country": "GB",
        "banks": [
            {"iban": "GB99UK88776655443322", "bank_name": "HSBC UK"},
            {"iban": "DE221002003004005006", "bank_name": "Deutsche Bank (Transfer)"}
        ]
    },
    {
        "company": "Muster & Söhne (Filiale Nord)",
        "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
        "banks": [
            {"iban": "DE44123456781234567890", "bank_name": "Sparkasse Hamburg"},
            {"iban": "DE55876543218765432109", "bank_name": "Commerzbank"},
            {"iban": "DE66333333333333333333", "bank_name": "Postbank"}
        ]
    },
    {
        "company": "Smart Solution Apps",
        "street": "Market Square 1", "zip": "10115", "city": "Berlin", "country": "DE",
        "banks": [{"iban": "DE77222222222222222222", "bank_name": "N26"}]
    }
]

def add_noise(image: Image.Image) -> Image.Image:
    img_gray = image.convert("L")
    pixels = img_gray.load()
    width, height = img_gray.size
    for _ in range(int(width * height * 0.005)):
        x, y = random.randint(0, width - 1), random.randint(0, height - 1)
        pixels[x, y] = random.choice([0, 255])
    return img_gray.convert("RGB")

def add_scanned_stamp(image: Image.Image) -> Image.Image:
    """Draws a red 'SCANNED' stamp at the top middle."""
    draw = ImageDraw.Draw(image)
    width, _ = image.size
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
    except:
        font = ImageFont.load_default()
    
    text = "SCANNED"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x, y = (width - tw) // 2, 50
    padding = 15
    # Draw border
    draw.rectangle([x-padding, y-padding, x+tw+padding, y+th+padding], outline="red", width=5)
    # Draw text
    draw.text((x, y), text, fill="red", font=font)
    return image

def simulate_scan(pdf_path: Path, stamped: bool = False) -> Path:
    logger.info(f"  Simulating scan impact {'+ STAMP ' if stamped else ''}for {pdf_path.name}...")
    images = convert_from_path(pdf_path, dpi=150)
    scanned_pages = []
    for i, page in enumerate(images):
        # 1. Stamping (only first page)
        if i == 0 and stamped:
            page = add_scanned_stamp(page)
        # 2. Rotation
        angle = random.uniform(-1.0, 1.0)
        page = page.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor="white")
        # 3. Noise
        page = add_noise(page)
        # 4. Blur
        if random.random() > 0.4:
            page = page.filter(ImageFilter.GaussianBlur(radius=0.2))
        scanned_pages.append(page)
    
    temp_scan_pdf = pdf_path.with_name(f"scan_{pdf_path.name}")
    if scanned_pages:
        scanned_pages[0].save(temp_scan_pdf, save_all=True, append_images=scanned_pages[1:], resolution=150, quality=65)
    pdf_path.unlink()
    temp_scan_pdf.rename(pdf_path)
    return pdf_path

def update_xml_party(node: etree._Element, identity: Dict[str, Any]) -> None:
    if node is None: return
    name_node = node.find("ram:Name", NS)
    if name_node is not None: name_node.text = identity.get("company") or identity.get("name") or ""
    addr = node.find("ram:PostalTradeAddress", NS)
    if addr is not None:
        for tag, key in [("ram:LineOne", "street"), ("ram:PostcodeCode", "zip"), ("ram:CityName", "city"), ("ram:CountryID", "country")]:
            n = addr.find(tag, NS)
            if n is not None: n.text = str(identity.get(key) or identity.get("zip_code") if key=="zip" else identity.get(key,""))

def load_tenant_identities() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    config = AppConfig(profile="doc")
    try:
        raw = json.loads(config.get_private_profile_json()); kw = raw.get("address_keywords", [])
        p_id = {"name": raw.get("name"), "street": kw[0] if len(kw)>0 else "Weg 1", "zip": kw[1] if len(kw)>1 else "123", "city": kw[2] if len(kw)>2 else "City", "country": "DE"}
    except: p_id = {"name": "Max Mustermann", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE"}
    try:
        raw = json.loads(config.get_business_profile_json()); kw = raw.get("address_keywords", [])
        b_id = {"company": raw.get("company_name"), "name": raw.get("name"), "street": kw[0] if len(kw)>0 else "Park 1", "zip": kw[1] if len(kw)>1 else "543", "city": kw[2] if len(kw)>2 else "Town", "country": "DE"}
    except: b_id = {"company": "Muster Corp GmbH", "name": "Max Mustermann", "street": "Businesspark 1A", "zip": "54321", "city": "Industriestadt", "country": "DE"}
    return p_id, b_id

def patch_demos() -> None:
    base_path = Path("/home/schnebeck/Dokumente/Projects/KPaperFlux")
    backup_dir = base_path / "tests/resources/demo_invoices_complex_backup"
    original_dir = base_path / "tests/resources/demo_invoices_complex"
    original_dir.mkdir(parents=True, exist_ok=True)
    tenant_p, tenant_b = load_tenant_identities()

    # Total 25 Docs: 1-20 (Base), 21-25 (Scanned Extras)
    total_docs = list(range(1, 21)) + [21, 22, 23, 24, 25]

    for i in total_docs:
        # Configuration
        suffix = "de" if i % 2 != 0 else "en"
        filename = f"Demo_{i:02d}_INVOICE_{suffix}.pdf"
        # Base input: For 1-20 use backup, for 21-25 reuse backup of 1-5
        src_id = i if i <= 20 else (i - 20)
        src_suffix = "de" if src_id % 2 != 0 else "en"
        src_filename = f"Demo_{src_id:02d}_INVOICE_{src_suffix}.pdf"
        src_path = backup_dir / src_filename
        dst_path = original_dir / filename
        
        if not src_path.exists(): 
            logger.warning(f"Source {src_path} not found, skipping i={i}")
            continue

        logger.info(f"Processing {filename} (from {src_filename})...")

        # 1. XML Extraction (only if i <= 20 and it's one of the 5 ZUGFeRD ones, or i in [21,22])
        xml_bytes: Optional[bytes] = None
        xml_name = "factur-x.xml"
        if (i <= 5) or (i in [21, 22]):
            try:
                with pikepdf.open(src_path) as pdf:
                    for name, att in pdf.attachments.items():
                        if name.lower() in ["factur-x.xml", "zugferd-invoice.xml"]:
                            obj = att.obj
                            if hasattr(obj, "EF"):
                                if hasattr(obj.EF, "F"): xml_bytes = obj.EF.F.read_bytes()
                                elif hasattr(obj.EF, "UF"): xml_bytes = obj.EF.UF.read_bytes()
                            xml_name = name; break
            except: pass

        # 2. Extract metadata
        raw = ZugferdExtractor.extract_from_pdf(str(src_path))
        if not raw:
            raw = {"meta_data": {"doc_number": f"INV-{i:03d}", "doc_date": "2026-02-12"}, "finance_data": {"line_items": []}}

        # 3. Roles
        # Vendor Variety
        vendor = VENDORS[i % len(VENDORS)]
        if i == 5: # Max sends an invoice
             dir, ctx = "OUTBOUND", "PRIVATE"
             s_id, r_id = tenant_p, (raw["meta_data"].get("recipient") or {"name": "Anton Nachbar"})
        elif i % 2 != 0:
             dir, ctx = "INBOUND", "BUSINESS"
             s_id, r_id = vendor, tenant_b
        else:
             dir, ctx = "INBOUND", "PRIVATE"
             s_id, r_id = vendor, tenant_p

        # 4. XML Patch
        if xml_bytes:
            try:
                root = etree.fromstring(xml_bytes)
                party = "//ram:SellerTradeParty" if dir == "OUTBOUND" else "//ram:BuyerTradeParty"
                nodes = root.xpath(party, namespaces=NS)
                if nodes: update_xml_party(nodes[0], s_id if dir=="OUTBOUND" else r_id)
                xml_bytes = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
            except: pass

        # 5. Semantic Construction & Render
        try:
            # Filter AddressInfo fields to avoid Pydantic ValidationError (extra fields)
            def filter_addr(d): return {k: v for k, v in d.items() if k in AddressInfo.model_fields}

            extraction = SemanticExtraction(direction=dir, tenant_context=ctx,
                meta_header=MetaHeader(sender=AddressInfo(**filter_addr(s_id)), recipient=AddressInfo(**filter_addr(r_id)),
                doc_date=raw["meta_data"].get("doc_date"), doc_number=raw["meta_data"].get("doc_number"), language=suffix),
                type_tags=["INVOICE"])
            fin = raw["finance_data"]; fb = FinanceBody(invoice_number=fin.get("invoice_number"), invoice_date=fin.get("invoice_date"), currency=fin.get("currency", "EUR"))
            
            # Variety in Length (Force 2 pages for some)
            item_pool = fin.get("line_items", [])
            items_to_add = item_pool if item_pool else [{"description": "Item 1", "total_price": 100}]
            if i % 4 == 0: # Larger documents
                items_to_add = items_to_add * 15 # Ensure multiple pages
                
            for itm in items_to_add:
                item_val = LineItem(pos=str(itm.get("pos","")), description=itm.get("description"),
                                    quantity=Decimal(str(itm.get("quantity") or 1)), unit=itm.get("unit") or "C62",
                                    unit_price=Decimal(str(itm.get("unit_price") or 0)), total_price=Decimal(str(itm.get("total_price") or 0)))
                fb.line_items.append(item_val)
            
            # Bank Accounts Variety
            fb.payment_accounts = [AddressInfo(**b) for b in vendor.get("banks", [])]
            
            ms = fin.get("monetary_summation", {})
            fb.monetary_summation = MonetarySummation(
                line_total_amount=Decimal(str(ms.get("line_total_amount") or sum(itm.total_price for itm in fb.line_items))),
                grand_total_amount=Decimal(str(ms.get("grand_total_amount") or sum(itm.total_price for itm in fb.line_items) * Decimal("1.19"))))
            extraction.bodies = {"finance_body": fb}

            temp_p = Path(f"temp_{i}.pdf")
            renderer = ProfessionalPdfRenderer(str(temp_p), locale=suffix)
            renderer.render_document(extraction)

            # 6. SCAN SIMULATION + STAMP (For 21-25)
            is_scanned = (i >= 21)
            if is_scanned:
                temp_p = simulate_scan(temp_p, stamped=True)

            # 7. Finalize
            with pikepdf.open(temp_p) as pdf:
                if xml_bytes:
                    pdf.attachments[xml_name] = pikepdf.AttachedFileSpec(pdf, xml_bytes, filename=xml_name)
                    logger.info(f"  Embedded ZUGFeRD into {filename}")
                pdf.save(dst_path)
            if temp_p.exists(): temp_p.unlink()

        except Exception as e:
            logger.error(f"  Fail i={i}: {e}")
            traceback.print_exc()

    logger.info("Universal test data generation completed.")

if __name__ == "__main__":
    patch_demos()
