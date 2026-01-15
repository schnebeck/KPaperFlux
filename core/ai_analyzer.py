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
    doc_type: Optional[str] = None
    sender_address: Optional[str] = None
    iban: Optional[str] = None
    phone: Optional[str] = None
    tags: Optional[str] = None

class AIAnalyzer:
    """
    Analyzes document text using Google Gemini to extract structured data.
    """
    def __init__(self, api_key: str, model_name: str = 'gemini-2.0-flash'):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model_name 

    def analyze_text(self, text: str) -> AIAnalysisResult:
        """
        Send text to Gemini and parse the JSON response.
        """
        if not text or not text.strip():
            return AIAnalysisResult()

        prompt = """
        You are a document extraction assistant. Analyze the following document text and extract:
        1. Sender (Name of company or person)
        2. Document Date (in YYYY-MM-DD format)
        3. Total Amount (Numeric, valid decimal)
        4. Document Type (One of: Invoice, Receipt, Contract, Letter, Other)
        
        Your job is to extract structured data.
        Return ONLY valid JSON.
        
        Fields to extract:
        1. sender: Name of company or person.
        2. doc_date: YYYY-MM-DD.
        3. amount: numeric literal (e.g. 12.50).
        4. doc_type: e.g. "Invoice", "Contract", "Letter".
        5. sender_address: Full address (Street, Zip, City).
        6. iban: International Bank Account Number if present.
        7. phone: Sender's phone number.
        8. tags: A generic string of comma-separated keywords useful for organization (e.g. "Rechnung, Versicherung, KFZ"). Check context for appropriate tags.
        
        JSON Keys: ["sender", "doc_date", "amount", "doc_type", "sender_address", "iban", "phone", "tags"]
        If a field is not found, set it to null.
        
        Text:
        {text}
        """
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt.format(text=text)
            )
            response_text = response.text
            
            # Clean up markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "")
            elif "```" in response_text:
                response_text = response_text.replace("```", "")
                
            data = json.loads(response_text)
            
            # Parse Date
            doc_date = None
            if data.get("doc_date"):
                try:
                    doc_date = datetime.date.fromisoformat(data["doc_date"])
                except ValueError:
                    pass
            
            # Parse Amount
            amount = None
            if data.get("amount") is not None:
                try:
                    amount = Decimal(str(data["amount"]))
                except Exception:
                    pass
                    
            return AIAnalysisResult(
                sender=data.get("sender"),
                doc_date=doc_date,
                amount=amount,
                doc_type=data.get("doc_type"),
                sender_address=data.get("sender_address"),
                iban=data.get("iban"),
                phone=data.get("phone"),
                tags=data.get("tags")
            )
            
        except Exception as e:
            print(f"AI Analysis Error: {e}")
            return AIAnalysisResult()
