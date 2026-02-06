import os
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, List
from core.models.semantic import SemanticExtraction

logger = logging.getLogger("KPaperFlux.Renderer")

class SemanticRenderer:
    """
    Renders structured semantic data into human-readable representations
    using external JSON templates for maximum flexibility.
    """
    
    def __init__(self, l10n_dir: str = "resources/l10n", locale: str = "de"):
        # Normalize locale to 2-letter code (de_DE -> de)
        self.locale = locale.split("_")[0].lower()
        self.l10n_dir = l10n_dir
        self.templates: Dict[str, List[Dict]] = {"locale": [], "standard": []}
        self.unit_codes: Dict[str, str] = {}
        self._load_templates()
        self._load_unit_codes()

    def _load_unit_codes(self):
        """Loads ISO unit code translations from the l10n folder."""
        # Try current locale first, then fallback to English
        for loc in [self.locale, "en"]:
            path = os.path.join(self.l10n_dir, loc, "units.json")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self.unit_codes = json.load(f)
                        return
                except Exception as e:
                    logger.error(f"Failed to load unit codes for {loc}: {e}")

    def _load_templates(self):
        """Loads templates from the locale-specific folder and the common folder."""
        # 1. Load Locale Specific (e.g. l10n/de/templates/)
        locale_path = os.path.join(self.l10n_dir, self.locale, "templates")
        self.templates["locale"] = self._load_from_dir(locale_path)
        
        # 2. Load Common Fallbacks (e.g. l10n/common/templates/)
        common_path = os.path.join(self.l10n_dir, "common", "templates")
        self.templates["standard"] = self._load_from_dir(common_path)

    def _load_from_dir(self, path: str) -> List[Dict]:
        found = []
        if not os.path.exists(path):
            return found
            
        for filename in os.listdir(path):
            if filename.endswith(".json"):
                full_path = os.path.join(path, filename)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        found.append(json.load(f))
                except Exception as e:
                    logger.error(f"Failed to load template {filename}: {e}")
        return found

    def _get_template_for(self, tags: List[str]) -> Optional[Dict]:
        """Finds the best matching template. Search order: locale -> standard."""
        tags_upper = [t.upper() for t in tags]
        
        # Check Priority 1: Locale
        for tpl in self.templates["locale"]:
            match_tags = [mt.upper() for mt in tpl.get("match_tags", [])]
            if any(tag in match_tags for tag in tags_upper):
                return tpl
                
        # Check Priority 2: Standard
        for tpl in self.templates["standard"]:
            match_tags = [mt.upper() for mt in tpl.get("match_tags", [])]
            if any(tag in match_tags for tag in tags_upper):
                return tpl
                
        return None

    def render_as_markdown(self, data: SemanticExtraction) -> str:
        """Generates a structured Markdown summary using templates."""
        tpl = self._get_template_for(data.type_tags or [])
        
        if not tpl:
            return self._render_fallback(data)

        lines = []
        lines.append(f"# {self._get_doc_title(data)}")
        lines.append(f"**Template:** {tpl.get('name', 'Standard')}")
        lines.append("---")

        for section in tpl.get("sections", []):
            s_type = section.get("type", "table")
            title = section.get('title', 'Details')
            
            # Skip special layout blocks for Markdown or render them as KV
            if s_type in ["sender_info", "recipient_info"]:
                label = "Absender" if s_type == "sender_info" else "Empfänger"
                path = "meta_header.sender" if s_type == "sender_info" else "meta_header.recipient"
                info = self._resolve_path(data, path)
                if info:
                    lines.append(f"## {label}")
                    lines.append(f"* **Name:** {info.name or info.company or '---'}")
                    lines.append(f"* **Adresse:** {info.street or '---'}, {info.zip_code or ''} {info.city or ''}")
                continue

            lines.append(f"## {title}")

            if s_type == "table":
                lines.extend(self._render_table_section(section, data))
            elif s_type == "key_value":
                 lines.extend(self._render_kv_section(section, data))
            elif s_type == "list":
                lines.extend(self._render_list_section(section, data))
            elif s_type == "item_list":
                lines.extend(self._render_item_list_section(section, data))
            
            lines.append("")

        lines.append("---")
        lines.append(f"**Generiert am:** {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        return "\n".join(lines)

    def render_as_html(self, data: SemanticExtraction) -> str:
        """Generates a professional HTML representation from templates (PDF-like)."""
        tpl = self._get_template_for(data.type_tags or [])
        if not tpl:
            return f"<html><body><pre>{self._render_fallback(data)}</pre></body></html>"

        html = ["""
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            body { font-family: 'Helvetica', 'Arial', sans-serif; font-size: 11pt; color: #000; margin: 0; padding: 30px; line-height: 1.4; }
            .page { background: #fff; }
            .header-info { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
            .header-info td { vertical-align: top; border: none; padding: 0; }
            .sender-info { text-align: right; font-size: 9pt; color: #444; }
            .recipient-info { text-align: left; padding-top: 40px; margin-bottom: 40px; font-size: 11pt; }
            .meta-info { text-align: right; font-size: 10pt; }
            
            h1 { font-size: 18pt; margin-top: 30px; margin-bottom: 5px; border-bottom: none; text-align: left; text-transform: uppercase; }
            .title-details { font-size: 9pt; margin-bottom: 30px; color: #555; }
            
            table.items { width: 100%; border-collapse: collapse; margin-top: 20px; }
            table.items th { border-bottom: 2px solid #000; padding: 8px 4px; text-align: left; font-size: 10pt; }
            table.items td { border-bottom: 1px solid #ddd; padding: 8px 4px; font-size: 10pt; vertical-align: top; }
            
            .totals-container { width: 100%; margin-top: 20px; }
            .totals-table { width: 280px; margin-left: auto; border-collapse: collapse; }
            .totals-table td { padding: 4px; text-align: right; }
            .totals-table .total-label { text-align: left; }
            .totals-table .gross { border-top: 1px solid #000; font-weight: bold; font-size: 12pt; border-bottom: 2px double #000; }
            
            .footer-info { margin-top: 100px; font-size: 9pt; color: #666; width: 100%; border-top: 1px solid #ddd; padding-top: 10px; }
        </style>
        </head>
        <body>
        <div class="page">
        """]

        # 1. Header Area (Sender info - Right aligned)
        sender = data.meta_header.sender if data.meta_header else None
        if sender:
            html.append('<div class="sender-info">')
            html.append(f'<strong>{sender.company or sender.name or ""}</strong><br>')
            html.append(f'{sender.street or ""}<br>')
            html.append(f'{sender.zip_code or ""} {sender.city or ""}<br>')
            if sender.iban:
                html.append(f'Bank: {sender.bank_name or ""} | IBAN: {sender.iban}')
            html.append('</div>')

        # 2. Recipient Area (Left aligned)
        recipient = data.meta_header.recipient if data.meta_header else None
        if recipient:
            html.append('<div class="recipient-info">')
            html.append(f'{recipient.name or recipient.company or ""}<br>')
            if recipient.company and recipient.name:
                html.append(f'{recipient.name}<br>') # Contact person
            html.append(f'{recipient.street or ""}<br>')
            html.append(f'{recipient.zip_code or ""} {recipient.city or ""}')
            html.append('</div>')

        # 3. Meta info (Date/Number - Right aligned)
        html.append('<div class="meta-info">')
        if data.meta_header and data.meta_header.doc_date:
            html.append(f'Datum: {self._format_value(data.meta_header.doc_date, "date")}<br>')
        if data.meta_header and data.meta_header.doc_number:
            html.append(f'Beleg-Nr.: {data.meta_header.doc_number}')
        html.append('</div>')

        # 4. Title
        title_text = self._get_doc_title(data).split(' #')[0]
        html.append(f'<h1>{title_text}</h1>')
        
        # Subtitle details (Order#, etc)
        details = []
        fb = data.bodies.get("finance_body")
        if fb:
            if hasattr(fb, 'order_number') and fb.order_number:
                details.append(f"Auftrag-Nr.: {fb.order_number}")
            if hasattr(fb, 'order_date') and fb.order_date:
                details.append(f"Bestelldatum: {self._format_value(fb.order_date, 'date')}")
            if hasattr(fb, 'customer_id') and fb.customer_id:
                details.append(f"Kunden-Nr.: {fb.customer_id}")
        
        if details:
            html.append(f'<div class="title-details">{" | ".join(details)}</div>')

        # 5. Iterative Sections (Table, List, Items)
        for section in tpl.get("sections", []):
            s_type = section.get("type")
            if s_type in ["sender_info", "recipient_info"]:
                continue # Already handled in specific layout spots
            
            if s_type == "item_list":
                html.extend(self._render_item_list_html(section, data))
            elif s_type == "table":
                # Totals are usually tables
                if section.get("id") == "totals_block":
                    html.extend(self._render_totals_html(section, data))
                else:
                    html.append(f"<h3>{section.get('title', '')}</h3>")
                    html.extend(self._render_table_html(section, data))
            elif s_type == "list":
                html.append(f"<h3>{section.get('title', '')}</h3>")
                html.extend(self._render_list_html(section, data))
            elif s_type == "key_value":
                # Already handled in meta for some, but generic KV if still there
                if section.get("id") != "meta_block":
                    html.append(f"<h3>{section.get('title', '')}</h3>")
                    html.extend(self._render_kv_html(section, data))

        # 6. Sticky Footer (Payment instructions)
        fb = data.bodies.get("finance_body")
        if fb and hasattr(fb, 'payment_accounts') and fb.payment_accounts:
            html.append('<div class="footer-info">')
            for acc in fb.payment_accounts:
                acc_name = acc.get('bank_name', 'Bank')
                iban = acc.get('iban', '')
                html.append(f'Bezahlung an: {acc_name} - IBAN: {iban}<br>')
            html.append('</div>')

        html.append("</div></body></html>")
        return "\n".join(html)

    def _resolve_path(self, data: Any, path: str) -> Any:
        """Navigates through Pydantic models/dicts using dot notation."""
        ALIASES = {
            "net_price": "unit_price",
            "total": "total_price",
            "line_total": "total_price",
            "pos_no": "pos",
            "item_name": "description"
        }
        
        parts = path.split(".")
        curr = data
        for p in parts:
            if curr is None: return None
            
            # Map alias if present
            target_p = ALIASES.get(p, p)
            
            if isinstance(curr, dict):
                # Try original, then alias
                val = curr.get(p)
                if val is None and target_p != p:
                    val = curr.get(target_p)
                curr = val
            else:
                # Try original, then alias
                val = getattr(curr, p, None)
                if val is None and target_p != p:
                    val = getattr(curr, target_p, None)
                curr = val
        return curr

    def _format_value(self, val: Any, fmt: str) -> str:
        from core.utils.formatting import format_currency, format_date
        
        if val is None: return "---"
        if fmt == "currency":
            return format_currency(val, currency="EUR", locale=self.locale)
        if fmt == "date":
            return format_date(val, locale=self.locale)
        if fmt == "unit":
            code = str(val).upper()
            return self.unit_codes.get(code, code)
        return str(val)

    def _render_table_section(self, section: Dict, data: SemanticExtraction) -> List[str]:
        l = ["| Feld | Wert |", "| :--- | :--- |"]
        for field in section.get("fields", []):
            raw_val = self._resolve_path(data, field.get("path", ""))
            val = self._format_value(raw_val, field.get("format"))
            label = field.get("label", "Unbekannt")
            if field.get("important"):
                l.append(f"| **{label}** | **{val}** |")
            else:
                l.append(f"| {label} | {val} |")
        return l

    def _render_item_list_section(self, section: Dict, data: SemanticExtraction) -> List[str]:
        """Markdown rendering for line items."""
        source_path = section.get("source", "")
        items = self._resolve_path(data, source_path)
        if not items: return ["*Keine Positionen gefunden.*"]
        
        cols = section.get("columns", [])
        header = "| " + " | ".join([c.get("label") for c in cols]) + " |"
        sep = "| " + " | ".join([":---" for _ in cols]) + " |"
        l = [header, sep]
        
        for item in items:
            row = []
            for col in cols:
                raw = item.get(col.get("path")) if isinstance(item, dict) else getattr(item, col.get("path"), None)
                row.append(self._format_value(raw, col.get("format")))
            l.append("| " + " | ".join(row) + " |")
        return l

    def _render_kv_section(self, section: Dict, data: SemanticExtraction) -> List[str]:
        l = []
        for field in section.get("fields", []):
            raw_val = self._resolve_path(data, field.get("path", ""))
            val = self._format_value(raw_val, field.get("format"))
            l.append(f"**{field.get('label')}:** {val}")
        return l

    def _render_list_section(self, section: Dict, data: SemanticExtraction) -> List[str]:
        l = []
        source_path = section.get("source", "")
        items = self._resolve_path(data, source_path)
        if not items: return ["*Keine Einträge*"]
        
        template = section.get("item_template", "* {item}")
        for item in items:
            if isinstance(item, dict):
                l.append(template.format(**item))
            else:
                l.append(template.replace("{item}", str(item)))
        return l

    def _render_item_list_html(self, section: Dict, data: SemanticExtraction) -> List[str]:
        items = self._resolve_path(data, section.get("source", ""))
        cols = section.get("columns", [])
        if not items: return ["<p><em>Keine Positionen vorhanden.</em></p>"]
        
        html = ['<table class="items">', '<thead><tr>']
        for c in cols:
            html.append(f'<th>{c.get("label")}</th>')
        html.append('</tr></thead><tbody>')
        
        for item in items:
            html.append('<tr>')
            for c in cols:
                raw = item.get(c.get("path")) if isinstance(item, dict) else getattr(item, c.get("path"), None)
                val = self._format_value(raw, c.get("format"))
                html.append(f'<td>{val}</td>')
            html.append('</tr>')
        
        html.append('</tbody></table>')
        return html

    def _render_totals_html(self, section: Dict, data: SemanticExtraction) -> List[str]:
        html = ['<div class="totals-container">', '<table class="totals-table">']
        for field in section.get("fields", []):
            raw_val = self._resolve_path(data, field.get("path", ""))
            if raw_val is None: continue
            
            val = self._format_value(raw_val, field.get("format"))
            cls = "gross" if field.get("important") else ""
            html.append(f'<tr class="{cls}">')
            html.append(f'<td class="total-label">{field.get("label")}</td>')
            html.append(f'<td>{val}</td>')
            html.append('</tr>')
        html.append('</table></div>')
        return html

    def _render_table_html(self, section: Dict, data: SemanticExtraction) -> List[str]:
        html = ['<table style="width: 100%;">']
        for field in section.get("fields", []):
            raw_val = self._resolve_path(data, field.get("path", ""))
            val = self._format_value(raw_val, field.get("format"))
            html.append(f'<tr><td style="width: 40%; font-weight: bold;">{field.get("label")}</td><td>{val}</td></tr>')
        html.append('</table>')
        return html

    def _render_kv_html(self, section: Dict, data: SemanticExtraction) -> List[str]:
        html = []
        for field in section.get("fields", []):
            raw_val = self._resolve_path(data, field.get("path", ""))
            val = self._format_value(raw_val, field.get("format"))
            html.append(f'<div><strong>{field.get("label")}:</strong> {val}</div>')
        return html

    def _render_list_html(self, section: Dict, data: SemanticExtraction) -> List[str]:
        items = self._resolve_path(data, section.get("source", ""))
        if not items: return []
        html = ["<ul>"]
        tpl = section.get("item_template", "{item}")
        for item in items:
            txt = tpl.format(**item) if isinstance(item, dict) else tpl.replace("{item}", str(item))
            html.append(f"<li>{txt}</li>")
        html.append("</ul>")
        return html

    def _get_doc_title(self, data: SemanticExtraction) -> str:
        translated_tags = []
        mapping = {
            "INVOICE": "Rechnung",
            "RECHNUNG": "Rechnung",
            "ORDER_CONFIRMATION": "Auftragsbestätigung",
            "DELIVERY_NOTE": "Lieferschein",
            "RECEIPT": "Quittung",
            "CONTRACT": "Vertrag",
            "LETTER": "Schreiben"
        }
        
        for t in data.type_tags:
            tag_up = t.upper()
            if tag_up in mapping:
                translated_tags.append(mapping[tag_up])
            else:
                translated_tags.append(t.capitalize())
                
        types = " / ".join(list(dict.fromkeys(translated_tags))) if translated_tags else "Dokument"
        number = ""
        if data.meta_header and data.meta_header.doc_number:
            number = f" #{data.meta_header.doc_number}"
        return f"{types}{number}"

    def _render_fallback(self, data: SemanticExtraction) -> str:
        """Backwards compatibility renderer."""
        return f"# {self._get_doc_title(data)}\n*Kein passendes Template gefunden.*\n\n```json\n{data.model_dump_json(indent=2)}\n```"
