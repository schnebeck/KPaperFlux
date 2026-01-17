from typing import Optional
from dataclasses import dataclass
import datetime
import json
from decimal import Decimal
from decimal import Decimal
import time
import random
from google import genai
from google.genai.errors import ClientError

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
    MAX_RETRIES = 5
    _cooldown_until: Optional[datetime.datetime] = None # Shared cooldown state
    _adaptive_delay: float = 0.0 # Adaptive delay in seconds (Harmonic Oscillation)

    @classmethod
    def get_adaptive_delay(cls) -> float:
        return cls._adaptive_delay
    
    def __init__(self, api_key: str, model_name: str = 'gemini-2.0-flash'):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model_name 

    def _wait_for_cooldown(self):
        """Check shared cooldown and sleep if necessary."""
        if AIAnalyzer._cooldown_until:
            now = datetime.datetime.now()
            if AIAnalyzer._cooldown_until > now:
                wait_time = (AIAnalyzer._cooldown_until - now).total_seconds()
                if wait_time > 0:
                    print(f"AI Rate Limit Active. Sleeping for {wait_time:.1f}s...")
                    time.sleep(wait_time)
            
            # Clear cooldown after waiting or if expired
            AIAnalyzer._cooldown_until = None

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
             7. "stamps": A LIST of objects found.
               - IMPORTANT: If a single visual stamp contains multiple fields (e.g. Date AND Cost Center), merge them into ONE object. Do NOT split them.
               - Each object: {"type": "entry"|"accounting"|"paid", "date": "YYYY-MM-DD", "cost_center": "...", "cost_bearer": "...", "editor": "...", "note": "..."}
               - Use "type": "accounting" if it contains financial codes (Cost Center/Bearer).
               - Use "type": "entry" if it acts as a date-received stamp.
           
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
                
            response = None
            
            # 0. Adaptive Delay (Swing In)
            if AIAnalyzer._adaptive_delay > 0:
                print(f"AI Adaptive Delay: Sleeping {AIAnalyzer._adaptive_delay:.2f}s...")
                time.sleep(AIAnalyzer._adaptive_delay)

            # Retry Loop
            for attempt in range(self.MAX_RETRIES):
                self._wait_for_cooldown()
                
                try:
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=contents
                    )
                    break # Success
                except ClientError as e:
                    # Check for 429 Resource Exhausted
                    # e.code or e.status might be present
                    is_429 = False
                    if hasattr(e, "code") and e.code == 429: is_429 = True
                    if hasattr(e, "status") and "RESOURCE_EXHAUSTED" in str(e.status): is_429 = True
                    # Check message text as fallback
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e): is_429 = True
                    
                    if is_429:
                        # 1. Increase Adaptive Delay (Multiplicative Increase with CAP)
                        # Limit max delay to 256s (approx 4 mins) as per user request.
                        old_delay = AIAnalyzer._adaptive_delay
                        new_delay = max(2.0, AIAnalyzer._adaptive_delay * 2.0)
                        AIAnalyzer._adaptive_delay = min(256.0, new_delay)
                        
                        if AIAnalyzer._adaptive_delay != old_delay:
                            print(f"AI Rate Limit Hit! Increasing Adaptive Delay: {old_delay:.2f}s -> {AIAnalyzer._adaptive_delay:.2f}s")

                        # 2. Exponential Backoff for *this* retry
                        # We still wait exponentially for the current request to clear the immediate congestion.
                        delay = 2 * (2 ** attempt) + random.uniform(0, 1)
                        print(f"AI 429 Error. Backing off for {delay:.1f}s (Attempt {attempt+1}/{self.MAX_RETRIES})")
                        
                        # Set Cooldown
                        AIAnalyzer._cooldown_until = datetime.datetime.now() + datetime.timedelta(seconds=delay)
                        
                        # Loop will check cooldown next iteration
                        continue
                    else:
                        raise e # Other error
            
            if not response:
                print("AI Analysis Failed after retries.")
                return AIAnalysisResult()

            # Success: Decrease Adaptive Delay (Multiplicative Decrease)
            # "Swing in" towards 0 if stable.
            if AIAnalyzer._adaptive_delay > 0:
                 old_delay = AIAnalyzer._adaptive_delay
                 AIAnalyzer._adaptive_delay = max(0.0, AIAnalyzer._adaptive_delay * 0.5)
                 # If very small, snap to 0
                 if AIAnalyzer._adaptive_delay < 0.1: AIAnalyzer._adaptive_delay = 0.0
                 print(f"AI Success. Decreasing Adaptive Delay: {old_delay:.2f}s -> {AIAnalyzer._adaptive_delay:.2f}s")
                 
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
