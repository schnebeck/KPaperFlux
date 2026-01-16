from typing import Optional
from dataclasses import dataclass
import datetime
import json
from decimal import Decimal
from google import genai

@dataclass
class AIAnalysisResult:
    sender: Optional[str] = None
    doc_date: Optional[datetime.date] = None
    amount: Optional[Decimal] = None
    
    # Phase 45 Financials
    gross_amount: Optional[Decimal] = None
    postage: Optional[Decimal] = None
    packaging: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    currency: Optional[str] = None
    
    doc_type: Optional[str] = None
    sender_address: Optional[str] = None
    iban: Optional[str] = None
    phone: Optional[str] = None
    tags: Optional[str] = None
    
    # Structured Details
    recipient_company: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_street: Optional[str] = None
    recipient_zip: Optional[str] = None
    recipient_city: Optional[str] = None
    recipient_country: Optional[str] = None
    
    sender_company: Optional[str] = None
    sender_name: Optional[str] = None
    sender_street: Optional[str] = None
    sender_zip: Optional[str] = None
    sender_city: Optional[str] = None
    sender_country: Optional[str] = None
    
    # Phase 30: Dynamic Data
    extra_data: Optional[dict] = None

class AIAnalyzer:
    """
    Analyzes document text using Google Gemini to extract structured data.
    """
    def __init__(self, api_key: str, model_name: str = 'gemini-2.0-flash'):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model_name 

    def analyze_text(self, text: str, image=None) -> AIAnalysisResult:
        """
        Send text and optional image to Gemini and parse the JSON response.
        :param text: Text content of the document.
        :param image: PIL.Image object of the first page (optional).
        """
        if (not text or not text.strip()) and not image:
            return AIAnalysisResult()

        prompt = """
        You are a document extraction assistant. Analyze the following document (text and optional image) and extract specific metadata.
        
        Extract:
        1. Main Details:
           - sender: Summary name of sender.
           - doc_date: YYYY-MM-DD.
           - amount: numeric literal (Net Amount).
           - gross_amount: numeric literal (Brutto Amount).
           - postage: numeric literal (Porto/Versand).
           - packaging: numeric literal (Verpackung).
           - tax_rate: numeric literal (e.g. 19.0 for 19%).
           - currency: ISO Code (EUR, USD, etc.).
           - doc_type: Invoice, Receipt, Contract, Letter, Auftragsbestätigung, Lieferschein, etc.
             (Note: "Auftragsbestätigung" -> "Order Confirmation", but keep German if document is German).
           - tags: Comma-separated keywords.
           - iban: IBAN string.
           - phone: Phone string.
        
        2. Sender Details (From whom):
           - Look for "Absender", header logos, or footer details.
           - sender_company
           - sender_name (Contact Person)
           - sender_street, sender_zip, sender_city, sender_country
           
        3. Recipient Details (To whom):
           - Look for "Empfänger", "Rechnungsadresse", "Lieferadresse".
           - recipient_company, recipient_name
           - recipient_street, recipient_zip, recipient_city, recipient_country

        4. Stamp & Custom Data (Dynamic):
           - LOOK AT THE IMAGE VISUALLY for stamps (Boxed areas, ink stamps).
           - Look for "Eingangsstempel" (Entry Stamp) or "Kontorierungsstempel" (Accounting Stamp).
           - These often appear as rectangular stamps with handwritten or typed fields like "Eingegangen am", "Kst", "Ktr", "Freigabe", "Gebucht".
           - If found, extract all fields into a "stamps" object within "extra_data".
           - IMPORTANT: Normalize all JSON keys to lowercase English, even if the stamp is German:
             - "Kst" / "Kostenstelle" -> "cost_center"
             - "Ktr" / "Kostenträger" -> "cost_bearer"
             - "Bearbeiter" / "Kürzel" -> "editor"
             - "Bemerkung" -> "note"
             - "Datum" -> "date" (Use ISO YYYY-MM-DD)
           - Example: extra_data: { "stamps": [{"type": "entry", "date": "2024-05-12", "cost_center": "10", "editor": "ABC"}] }
           
        Return ONLY valid JSON.
        JSON Structure:
        {
          "sender": "...",
          "doc_date": "YYYY-MM-DD",
          "amount": 12.50,
          "gross_amount": 14.88,
          "postage": 0.00,
          "packaging": 0.00,
          "tax_rate": 19.0,
          "currency": "EUR",
          "doc_type": "...",
          "iban": "...",
          "phone": "...",
          "tags": "...",
          "sender_address": "...",
          "sender_company": "...", "sender_name": "...", "sender_street": "...", "sender_zip": "...", "sender_city": "...", "sender_country": "...",
          "recipient_company": "...", "recipient_name": "...", "recipient_street": "...", "recipient_zip": "...", "recipient_city": "...", "recipient_country": "...",
          "extra_data": { ... }
        }
        If a field is not found, set to null.
        
        Text:
        {text}
        """
        
        try:
            contents = [prompt.replace("{text}", text)]
            if image:
                contents.append(image)
                
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents
            )
            response_text = response.text
            
            # Clean up markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "")
            elif "```" in response_text:
                response_text = response_text.replace("```", "")
                
            data = json.loads(response_text)
            print(f"DEBUG AI Response: {json.dumps(data, indent=2)}")
            
            # Parse Date
            doc_date = None
            if data.get("doc_date"):
                try:
                    doc_date = datetime.date.fromisoformat(data["doc_date"])
                except ValueError:
                    pass
            
            # Parse Amounts (Safe Decimal conversion)
            def get_decimal(key):
                val = data.get(key)
                if val is not None:
                    try: return Decimal(str(val))
                    except: pass
                return None

            amount = get_decimal("amount")
            gross_amount = get_decimal("gross_amount")
            postage = get_decimal("postage")
            packaging = get_decimal("packaging")
            tax_rate = get_decimal("tax_rate")
            currency = data.get("currency")
                    
            return AIAnalysisResult(
                sender=data.get("sender"),
                doc_date=doc_date,
                amount=amount,
                gross_amount=gross_amount,
                postage=postage,
                packaging=packaging,
                tax_rate=tax_rate,
                currency=currency,
                
                doc_type=data.get("doc_type"),
                sender_address=data.get("sender_address"),
                iban=data.get("iban"),
                phone=data.get("phone"),
                tags=data.get("tags"),
                
                recipient_company=data.get("recipient_company"),
                recipient_name=data.get("recipient_name"),
                recipient_street=data.get("recipient_street"),
                recipient_zip=data.get("recipient_zip"),
                recipient_city=data.get("recipient_city"),
                recipient_country=data.get("recipient_country"),
                
                sender_company=data.get("sender_company"),
                sender_name=data.get("sender_name"),
                sender_street=data.get("sender_street"),
                sender_zip=data.get("sender_zip"),
                sender_city=data.get("sender_city"),
                sender_country=data.get("sender_country"),
                
                extra_data=data.get("extra_data")
            )
            
        except Exception as e:
            print(f"AI Analysis Error: {e}")
            return AIAnalysisResult()
