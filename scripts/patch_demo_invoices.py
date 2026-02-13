"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           scripts/patch_demo_invoices.py
Version:        2.7.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Ultimate diversity engine. Generates 20+ completely unique 
                invoice designs with randomized layout concepts, colors,
                fonts, and logos. 5 Documents feature multi-type tags.
------------------------------------------------------------------------------
"""

import json
import logging
import os
import random
import traceback
import fitz
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
NS = {"rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
      "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}

# Branding Assets (Discover relative to script)
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
LOGO_BASE_DIR = REPO_ROOT / "tests/resources/demo_invoices_complex/logos"

if not LOGO_BASE_DIR.exists():
    # Try alternate location if symlinks are weird
    LOGO_BASE_DIR = Path("/home/schnebeck/Documents/Projects/KPaperFlux/tests/resources/demo_invoices_complex/logos")

LOGOS = list(LOGO_BASE_DIR.glob("*.png"))
if not LOGOS:
    logger.error(f"No logos found in {LOGO_BASE_DIR}!")
    LOGOS = [None] # Fallback
else:
    logger.info(f"Found {len(LOGOS)} logos in {LOGO_BASE_DIR}")
    LOGOS = [str(l) for l in LOGOS]

# Randomized Design Assets
CONCEPTS = ["CLASSIC", "MODERN", "INDUSTRIAL", "MINIMAL"]
FONTS = ["Helvetica", "Times-Roman", "Courier"]
COL_SETS = [
    ["pos", "quantity", "unit", "description", "unit_price", "total_price"],
    ["quantity", "unit", "description", "unit_price", "total_price"],
    ["quantity", "description", "unit_price", "total_price"],
    ["pos", "description", "total_price"],
    ["description", "total_price"]
]
COLORS = [colors.black, colors.darkblue, colors.darkred, colors.darkgreen, colors.darkslategray, colors.orange, colors.teal, colors.rosybrown]
LINE_STYLES = ["SOLID", "DASHED", "THICK"]

# 20 Unique Pseudo-Vendors
V_COMPANIES = [
    "AlpenGlück Bau GmbH", "Quantum Dynamics", "Vintage Paper Supply", "Heavy Metal Parts", 
    "Minimalist Design Studio", "Eco Green Solutions", "Digital Architects", "Blue Ocean Logistics",
    "Starlight Media Group", "Northern Lights Energy", "Iron Clad Software", "Silver Leaf Catering",
    "Golden Gate Consulting", "Red Rock Construction", "Aero Tech Systems", "Global Trade Corp",
    "Urban Style Fashion", "Bio Genetics Lab", "Future Vision Apps", "Old Town Bakery"
]

def generate_valid_iban(country_code, bban):
    """Calculates valid IBAN for test purposes (mod 97)."""
    # Convert CC to numeric (A=10, ..., Z=35). CC00 at the end.
    chars = country_code + "00"
    suffix = ""
    for c in chars:
        if c.isdigit():
            suffix += c
        else:
            suffix += str(ord(c.upper()) - 55)
    
    num_str = bban + suffix
    checksum = 98 - (int(num_str) % 97)
    return f"{country_code}{checksum:02d}{bban}"

def get_random_vendor(i):
    idx = i % len(V_COMPANIES)
    bban = f"100200300400500600{idx:02d}"
    iban = generate_valid_iban("DE", bban)
    
    return {
        "company": V_COMPANIES[idx],
        "street": f"Example St {random.randint(1, 400)}",
        "zip": str(random.randint(10000, 99999)),
        "city": random.choice(["Berlin", "Hamburg", "München", "London", "Paris"]),
        "country": "Deutschland" if idx % 2 == 0 else "United Kingdom",
        "banks": [{"iban": iban, "bank_name": "Commercial Bank"}],
        "design": {
            "concept": random.choice(CONCEPTS),
            "color": random.choice(COLORS),
            "font": random.choice(FONTS),
            "logo": LOGOS[idx % len(LOGOS)],
            "columns": random.choice(COL_SETS),
            "lines": random.choice(LINE_STYLES)
        }
    }

def generate_invoice(vendor, idx, lang="de", filename=None, pages=1):
    output_dir = Path("/home/schnebeck/Dokumente/Projects/KPaperFlux/tests/resources/demo_invoices_complex")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Use index to make it unique
    inv_num = f"INV-2026-{idx:04d}"
    if filename is None:
        filename = f"Demo_{idx:02d}_INVOICE_{lang}.pdf"
    
    path = output_dir / filename
    renderer = ProfessionalPdfRenderer(str(path), locale=lang) # Pass locale to renderer

    # Branding
    # The ProfessionalPdfRenderer in this file uses set_style, not direct attribute assignment
    # Assuming the user wants to use the existing set_style method
    logo_path = vendor["design"].get("logo")
    if logo_path:
        logger.info(f"Assigning logo {os.path.basename(logo_path)} to {vendor['company']}")
    else:
        logger.warning(f"No logo assigned to {vendor['company']}")

    renderer.set_style(
        concept=vendor["design"].get("concept", "MODERN"),
        color=vendor["design"].get("color", colors.dodgerblue),
        font=vendor["design"].get("font", "Helvetica"),
        logo=logo_path,
        columns=vendor["design"].get("columns", COL_SETS[0]),
        line_style=vendor["design"].get("lines", "SOLID")
    )

    # Content - This part needs to be adapted to the SemanticExtraction model
    # The provided `generate_invoice` snippet uses a simplified API for render_document
    # which is not compatible with the existing ProfessionalPdfRenderer.
    # I will adapt it to use SemanticExtraction as per the original file's renderer usage.

    # Identity Logic (simplified for this helper, actual logic is in patch_demos)
    # For this helper, we'll assume a generic sender/recipient setup
    sender_info = AddressInfo(
        name=vendor["company"],
        street=vendor["street"],
        zip=vendor["zip"],
        city=vendor["city"],
        country=vendor["country"]
    )
    recipient_info = AddressInfo(
        name="KPaperFlux Test User",
        street="Experiment Lane 42",
        zip="12345",
        city="Testing City",
        country="Germany"
    )

    meta_header = MetaHeader(
        sender=sender_info,
        recipient=recipient_info,
        doc_date="2026-02-12",
        doc_number=inv_num,
        language=lang
    )
    
    fb = FinanceBody(currency="EUR")
    total_net = Decimal("0.00")
    for i in range(5): # Random items for page 1
        price = Decimal(f"{85.0 + random.random()*50:.2f}")
        qty = Decimal("1")
        item_total = qty * price
        fb.line_items.append(LineItem(
            pos=str(i+1),
            description=f"Position {i+1} - High Quality Service",
            quantity=qty,
            unit="HUR", # C62 for piece, HUR for hour
            unit_price=price,
            total_price=item_total
        ))
        total_net += item_total
    
    fb.payment_accounts = [AddressInfo(**b) for b in vendor["banks"]]
    fb.monetary_summation = MonetarySummation(
        line_total_amount=total_net,
        tax_total_amount=total_net * Decimal("0.19"),
        grand_total_amount=total_net * Decimal("1.19")
    )

    extraction = SemanticExtraction(
        direction="OUTBOUND", # Assuming outbound for generated invoices
        tenant_context="BUSINESS",
        meta_header=meta_header,
        type_tags=["INVOICE"],
        bodies={"finance_body": fb}
    )
    
    renderer.render_document(extraction)
    
    # Add extra pages if requested
    if pages > 1:
        doc = fitz.open(path)
        for p in range(pages - 1):
            # Just add a page with some text (simulating attachments or many items)
            page = doc.new_page()
            page.insert_text((72, 72), f"Attachment Page {p+2} for {inv_num}", fontsize=12)
            page.insert_text((72, 100), "Detailed terms and conditions follow here...", fontsize=10)
            for line in range(10):
                page.insert_text((72, 150 + line*20), f"Standard clause number {line+1} of the general service agreement.", fontsize=9)
        doc.save(path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        doc.close()

    return path

def add_noise(image: Image.Image) -> Image.Image:
    img_v = image.convert("RGB"); pixels = img_v.load(); w, h = image.size
    for _ in range(int(w * h * 0.0015)):
        x, y = random.randint(0, w-1), random.randint(0, h-1); c = random.choice([0, 255]); pixels[x, y] = (c, c, c)
    return img_v

def add_scanned_stamp(image: Image.Image) -> Image.Image:
    draw = ImageDraw.Draw(image); w, _ = image.size
    try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except: font = ImageFont.load_default()
    txt = "SCANNED / GEPRÜFT"
    bbox = draw.textbbox((0, 0), txt, font=font); tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x, y = (w-tw)//2, 120
    draw.rectangle([x-8, y-8, x+tw+8, y+th+8], outline="red", width=3)
    draw.text((x, y), txt, fill="red", font=font)
    return image

def simulate_scan(pdf_path: Path) -> Path:
    import fitz
    from PIL import Image, ImageFilter
    doc = fitz.open(pdf_path)
    scanned = []
    for page in doc:
        pix = page.get_pixmap(dpi=150) # Use 150 DPI for better default
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        # 50% reduced noise as requested earlier (rotation range)
        img = img.rotate(random.uniform(-0.5, 0.5), resample=Image.BICUBIC, expand=False, fillcolor="white")
        img = add_noise(img)
        img = add_scanned_stamp(img) # Always add stamp
        scanned.append(img)
    
    tmp = pdf_path.with_name(f"sim_{pdf_path.name}")
    scanned[0].save(tmp, save_all=True, append_images=scanned[1:], resolution=150.0, quality=75) # Use 150 resolution
    doc.close()
    return tmp

def filter_addr(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if k in AddressInfo.model_fields}

def load_tenant_ids() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    config = AppConfig(profile="doc")
    def g(rj):
        try:
            d = json.loads(rj); kw = d.get("address_keywords", [])
            return {"name": d.get("name"), "street": kw[0] if len(kw)>0 else "Weg 1", "zip": kw[1] if len(kw)>1 else "123", "city": kw[2] if len(kw)>2 else "City", "country": kw[3] if len(kw)>3 else "Deutschland"}
        except: return {"name": "Max Mustermann", "street": "Musterweg 1,", "zip": "12345", "city": "Musterstadt", "country": "Deutschland"}
    return g(config.get_private_profile_json()), g(config.get_business_profile_json())

def patch_demos() -> None:
    base = Path("/home/schnebeck/Dokumente/Projects/KPaperFlux")
    orig_dir = base / "tests/resources/demo_invoices_complex"
    back_dir = base / "tests/resources/demo_invoices_complex_backup"
    tenant_p, tenant_b = load_tenant_ids()

    for i in range(1, 21):
        suffix = "de" if i % 2 != 0 else "en"
        filename = f"Demo_{i:02d}_INVOICE_{suffix}.pdf"
        dst_path = orig_dir / filename
        
        logger.info(f"Generating unique design for {filename}...")

        vendor = get_random_vendor(i)
        ds = vendor["design"]
        
        # Identity Logic
        if i == 5: dir, ctx, s_id, r_id = "OUTBOUND", "PRIVATE", tenant_p, {"name": "Test Client", "street": "Main Rd 1", "zip": "1000", "city": "London", "country": "UK"}
        elif i % 2 != 0: dir, ctx, s_id, r_id = "INBOUND", "BUSINESS", vendor, tenant_b
        else: dir, ctx, s_id, r_id = "INBOUND", "PRIVATE", vendor, tenant_p

        # Multi-Tag Support (last 5 or random 5)
        tags = ["INVOICE"]
        if i > 15: # Random 5 items
            tags.append(random.choice(["DELIVERY_NOTE", "ORDER_CONFIRMATION"]))

        try:
            extraction = SemanticExtraction(direction=dir, tenant_context=ctx,
                meta_header=MetaHeader(sender=AddressInfo(**filter_addr(s_id)), recipient=AddressInfo(**filter_addr(r_id)),
                doc_date="2026-02-14", doc_number=f"DEMO-{2026}-{i:03d}", language=suffix), type_tags=tags)
            
            fb = FinanceBody(currency="EUR")
            items_count = 1 if i % 7 != 0 else 15
            for j in range(items_count):
                price = Decimal(f"{random.randint(20, 1000)}.50")
                fb.line_items.append(LineItem(pos=str(j+1), description=f"Unique Service Item {i}-{j}", quantity=Decimal("1"), unit="C62", unit_price=price, total_price=price))
            
            fb.payment_accounts = [AddressInfo(**b) for b in vendor["banks"]]
            net = sum(x.total_price for x in fb.line_items)
            fb.monetary_summation = MonetarySummation(line_total_amount=net, tax_total_amount=net*Decimal("0.19"), grand_total_amount=net*Decimal("1.19"))
            extraction.bodies = {"finance_body": fb}

            renderer = ProfessionalPdfRenderer(str(dst_path), locale=suffix)
            if ds.get("logo"): logger.info(f"Using logo {os.path.basename(ds['logo'])} for {filename}")
            renderer.set_style(concept=ds["concept"], color=ds["color"], font=ds["font"], 
                               logo=ds["logo"], columns=ds["columns"], line_style=ds["lines"])
            renderer.render_document(extraction)

            # Attachment Logic
            src_path = back_dir / filename
            if os.path.exists(src_path):
                with pikepdf.open(src_path) as s_pdf:
                    xml_b, xml_n = None, "factur-x.xml"
                    for n, a in s_pdf.attachments.items():
                        if n.lower() in ["factur-x.xml", "zugferd-invoice.xml"]:
                             xml_b = a.obj.EF.F.read_bytes(); xml_n = n; break
                    if xml_b:
                        with pikepdf.open(dst_path) as d_pdf:
                            d_pdf.attachments[xml_n] = pikepdf.AttachedFileSpec(d_pdf, xml_b, filename=xml_n)
                            d_pdf.save(dst_path)
        except: traceback.print_exc()

    # Standard Scans (Demo_21-25) from Natives (01-05)
    for i in range(21, 26):
        base_id = i - 20
        suffix = "de" if base_id % 2 != 0 else "en"
        src_p = orig_dir / f"Demo_{base_id:02d}_INVOICE_{suffix}.pdf"
        dst_p = orig_dir / f"Demo_{i:02d}_INVOICE_{suffix}.pdf"
        logger.info(f"Scanning unique design {src_p.name} as {dst_p.name}...")
        tmp = simulate_scan(src_p)
        if tmp.exists():
            os.rename(tmp, dst_p)

    # Telekom-Style Challenge (Demo 26-28): 3-page docs, same layout, different text
    logger.info("Generating Telekom-Style multi-page documents (Demo 26-28)...")
    telekom_vendor = get_random_vendor(1) # Base on vendor 1
    for i in range(26, 29):
        filename = f"Demo_{i:02d}_INVOICE_de.pdf"
        dst_path = orig_dir / filename
        # Modify meta for each
        extraction = SemanticExtraction(direction="INBOUND", tenant_context="BUSINESS",
            meta_header=MetaHeader(sender=AddressInfo(**filter_addr(telekom_vendor)), recipient=AddressInfo(**filter_addr(tenant_b)),
            doc_date=f"2026-02-{i:02d}", doc_number=f"TELEKOM-99-{i:02d}", language="de"), type_tags=["INVOICE"])
        
        fb = FinanceBody(currency="EUR")
        price = Decimal("39.95")
        fb.line_items.append(LineItem(pos="1", description="Monthly Subscription", quantity=Decimal("1"), unit="C62", unit_price=price, total_price=price))
        fb.payment_accounts = [AddressInfo(**b) for b in telekom_vendor["banks"]]
        fb.monetary_summation = MonetarySummation(line_total_amount=price, tax_total_amount=price*Decimal("0.19"), grand_total_amount=price*Decimal("1.19"))
        extraction.bodies = {"finance_body": fb}

        renderer = ProfessionalPdfRenderer(str(dst_path), locale="de")
        if telekom_vendor["design"].get("logo"):
            logger.info(f"Using logo {os.path.basename(telekom_vendor['design']['logo'])} for {filename} (Telekom-Style)")
        renderer.set_style(concept=telekom_vendor["design"]["concept"], color=telekom_vendor["design"]["color"], 
                          font=telekom_vendor["design"]["font"], logo=telekom_vendor["design"].get("logo"), 
                          columns=telekom_vendor["design"]["columns"], line_style=telekom_vendor["design"]["lines"])
        renderer.render_document(extraction)
        
        # Make them 3 pages
        doc = fitz.open(dst_path)
        for p_idx in range(2):
            p = doc.new_page()
            p.insert_text((72, 72), f"Detailed Usage Report Page {p_idx+2}", fontsize=12)
        doc.save(dst_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP); doc.close()

    # Scan for Demo_26 as Demo_29
    logger.info("Scanning Telekom-Style doc (Demo_26 -> Demo_29)...")
    src_p = orig_dir / "Demo_26_INVOICE_de.pdf"
    dst_p = orig_dir / "Demo_29_INVOICE_de.pdf"
    tmp = simulate_scan(src_p)
    if tmp.exists():
        os.rename(tmp, dst_p)

    logger.info("Universal Layout Variety Engine Finished.")

if __name__ == "__main__":
    patch_demos()
