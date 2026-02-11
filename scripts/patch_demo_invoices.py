"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           scripts/patch_demo_invoices.py
Version:        2.4.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Elite test data generator. Creates 25 highly diverse invoices
                with unique branding, logos, varied layouts, and multi-page
                content. Includes 5 scanned variants with stempel.
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
from reportlab.lib import colors

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

# --- BRANDING CONFIGURATIONS ---
LOGO_DIR = Path("/home/schnebeck/.gemini/antigravity/brain/3e157208-5267-48b9-970c-f790e48f6eb0")
LOGO_TECH = str(LOGO_DIR / "abstract_corp_logo_1770849852825.png")
LOGO_CONSTRUCTION = str(LOGO_DIR / "mountain_construction_logo_1770849865191.png")

VENDORS = [
    {
        "company": "AlpenGlück Bau GmbH",
        "street": "Gipfelweg 7", "zip": "6020", "city": "Innsbruck", "country": "AT",
        "banks": [{"iban": "AT123456789012345678", "bank_name": "Tiroler Bank"}],
        "style": {"color": colors.orange, "font": "Helvetica", "logo": LOGO_CONSTRUCTION, "cols": ["pos", "quantity", "unit", "description", "unit_price", "total_price"]}
    },
    {
        "company": "Global Tech Logistics Ltd",
        "street": "100 Fleet Street", "zip": "EC4Y 1QE", "city": "London", "country": "GB",
        "banks": [{"iban": "GB99UK88776655443322", "bank_name": "HSBC UK"}],
        "style": {"color": colors.teal, "font": "Helvetica", "logo": LOGO_TECH, "cols": ["quantity", "description", "unit_price", "total_price"]}
    },
    {
        "company": "Muster & Söhne (HQ)",
        "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
        "banks": [
            {"iban": "DE44123456781234567890", "bank_name": "Sparkasse Hamburg"},
            {"iban": "DE55876543218765432109", "bank_name": "Commerzbank"}
        ],
        "style": {"color": colors.black, "font": "Times-Roman", "logo": None, "cols": ["pos", "quantity", "unit", "description", "unit_price", "total_price"]}
    },
    {
        "company": "Smart Solution Apps",
        "street": "Market Square 1", "zip": "10115", "city": "Berlin", "country": "DE",
        "banks": [{"iban": "DE77222222222222222222", "bank_name": "N26"}],
        "style": {"color": colors.darkgreen, "font": "Courier", "logo": LOGO_TECH, "cols": ["description", "total_price"]}
    }
]

def add_noise(image: Image.Image) -> Image.Image:
    img_v = image.convert("RGB")
    pixels = img_v.load()
    w, h = image.size
    for _ in range(int(w * h * 0.003)):
        x, y = random.randint(0, w - 1), random.randint(0, h - 1)
        c = random.choice([0, 255])
        pixels[x, y] = (c, c, c)
    return img_v

def add_scanned_stamp(image: Image.Image) -> Image.Image:
    draw = ImageDraw.Draw(image)
    w, _ = image.size
    try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 70)
    except: font = ImageFont.load_default()
    txt = "SCANNED / GEPRÜFT"
    bbox = draw.textbbox((0, 0), txt, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x, y = (w - tw) // 2, 80
    pad = 20
    draw.rectangle([x-pad, y-pad, x+tw+pad, y+th+pad], outline="red", width=8)
    draw.text((x, y), txt, fill="red", font=font)
    return image

def simulate_scan(pdf_path: Path, stamped: bool = False) -> Path:
    logger.info(f"  Dirtying {pdf_path.name}...")
    imgs = convert_from_path(pdf_path, dpi=150)
    scanned = []
    for i, img in enumerate(imgs):
        if i == 0 and stamped: img = add_scanned_stamp(img)
        img = img.rotate(random.uniform(-1.5, 1.5), resample=Image.BICUBIC, expand=False, fillcolor="white")
        img = add_noise(img)
        scanned.append(img)
    tmp = pdf_path.with_name(f"dirty_{pdf_path.name}")
    scanned[0].save(tmp, save_all=True, append_images=scanned[1:], resolution=150, quality=55)
    pdf_path.unlink()
    tmp.rename(pdf_path)
    return pdf_path

def load_tenant_ids() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    config = AppConfig(profile="doc")
    def g(raw_json):
        try:
            d = json.loads(raw_json); kw = d.get("address_keywords", [])
            return {"company": d.get("company_name"), "name": d.get("name"), "street": kw[0] if len(kw)>0 else "Weg 1", "zip": kw[1] if len(kw)>1 else "123", "city": kw[2] if len(kw)>2 else "City", "country": "DE"}
        except: return {"name": "Max Mustermann", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE"}
    return g(config.get_private_profile_json()), g(config.get_business_profile_json())

def patch_demos() -> None:
    base = Path("/home/schnebeck/Dokumente/Projects/KPaperFlux")
    orig_dir = base / "tests/resources/demo_invoices_complex"
    back_dir = base / "tests/resources/demo_invoices_complex_backup"
    tenant_p, tenant_b = load_tenant_ids()

    for i in range(1, 26):
        suffix = "de" if i % 2 != 0 else "en"
        filename = f"Demo_{i:02d}_INVOICE_{suffix}.pdf"
        dst_path = orig_dir / filename
        
        # Source Selection (reuse backup content for logical data)
        src_id = ((i-1) % 20) + 1
        src_filename = f"Demo_{src_id:02d}_INVOICE_{suffix}.pdf"
        src_path = back_dir / src_filename
        
        logger.info(f"Creating {filename}...")

        # 1. XML Migration
        xml_bytes: Optional[bytes] = None; xml_name = "factur-x.xml"
        if os.path.exists(src_path):
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

        # 2. Base Data
        extractor_res = ZugferdExtractor.extract_from_pdf(str(src_path)) if os.path.exists(src_path) else None
        raw = extractor_res if extractor_res else {"meta_data": {}, "finance_data": {"line_items": []}}
        
        # 3. Roles & Variety
        vendor = VENDORS[(i-1) % len(VENDORS)]
        if i == 5: dir, ctx, s_id, r_id = "OUTBOUND", "PRIVATE", tenant_p, (raw["meta_data"].get("recipient") or {"name": "Recipient"})
        elif i % 2 != 0: dir, ctx, s_id, r_id = "INBOUND", "BUSINESS", vendor, tenant_b
        else: dir, ctx, s_id, r_id = "INBOUND", "PRIVATE", vendor, tenant_p

        # 4. XML Patch (simplified)
        if xml_bytes:
             try:
                 root = etree.fromstring(xml_bytes)
                 p_xpath = "//ram:SellerTradeParty" if dir == "OUTBOUND" else "//ram:BuyerTradeParty"
                 p_nodes = root.xpath(p_xpath, namespaces=NS)
                 if p_nodes:
                     target = s_id if dir=="OUTBOUND" else r_id
                     n = p_nodes[0].find("ram:Name", NS)
                     if n is not None: n.text = target.get("company") or target.get("name") or ""
                 xml_bytes = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
             except: pass

        # 5. Render
        try:
            def filter_addr(d): return {k: v for k, v in d.items() if k in AddressInfo.model_fields}
            extraction = SemanticExtraction(direction=dir, tenant_context=ctx,
                meta_header=MetaHeader(sender=AddressInfo(**filter_addr(s_id)), recipient=AddressInfo(**filter_addr(r_id)),
                doc_date=raw["meta_data"].get("doc_date") or "2026-02-12", doc_number=raw["meta_data"].get("doc_number") or f"INV-{i:03d}", language=suffix),
                type_tags=["INVOICE"])
            
            fin = raw["finance_data"]; fb = FinanceBody(currency=fin.get("currency", "EUR"))
            items = fin.get("line_items", []) or [{"description": f"Service Item {i}", "total_price": 500}]
            if i % 3 == 0: items *= 8 # Variety in length
            
            for itm in items:
                fb.line_items.append(LineItem(pos=str(itm.get("pos","")), description=itm.get("description"),
                    quantity=Decimal(str(itm.get("quantity") or 1)), unit=itm.get("unit") or "C62",
                    unit_price=Decimal(str(itm.get("unit_price") or 0)), total_price=Decimal(str(itm.get("total_price") or 0))))
            
            fb.payment_accounts = [AddressInfo(**b) for b in vendor.get("banks", [])]
            ms = fin.get("monetary_summation", {})
            fb.monetary_summation = MonetarySummation(
                line_total_amount=Decimal(str(ms.get("line_total_amount") or sum(x.total_price for x in fb.line_items))),
                tax_total_amount=Decimal(str(ms.get("tax_total_amount") or sum(x.total_price for x in fb.line_items)*Decimal("0.19"))),
                grand_total_amount=Decimal(str(ms.get("grand_total_amount") or sum(x.total_price for x in fb.line_items)*Decimal("1.19"))))
            extraction.bodies = {"finance_body": fb}

            tmp_p = Path(f"build_{i}.pdf")
            renderer = ProfessionalPdfRenderer(str(tmp_p), locale=suffix)
            # Apply corporate style
            vs = vendor["style"]
            renderer.set_style(primary_color=vs["color"], font=vs["font"], logo=vs["logo"], columns=vs["cols"])
            renderer.render_document(extraction)

            # 6. Scan simulation for 21-25
            if i >= 21: tmp_p = simulate_scan(tmp_p, stamped=True)

            # 7. Save
            with pikepdf.open(tmp_p) as pdf:
                if xml_bytes: pdf.attachments[xml_name] = pikepdf.AttachedFileSpec(pdf, xml_bytes, filename=xml_name)
                pdf.save(dst_path)
            if tmp_p.exists(): tmp_p.unlink()
        except: traceback.print_exc()

    logger.info("Ultimate Test Data Generation Finished.")

if __name__ == "__main__":
    patch_demos()
