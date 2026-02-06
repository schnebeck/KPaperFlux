
import fitz  # PyMuPDF
import logging
from typing import Optional, Dict, Any
from lxml import etree
import decimal

logger = logging.getLogger("KPaperFlux.Zugferd")

class ZugferdExtractor:
    """
    Detects and extracts ZUGFeRD / Factur-X XML data from PDF/A files.
    """

    # ZUGFeRD 2.x / Factur-X Namespaces (CII)
    NS = {
        'rsm': 'urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100',
        'ram': 'urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100',
        'udt': 'urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100'
    }

    @classmethod
    def extract_from_pdf(cls, pdf_path: str) -> Optional[Dict[str, Any]]:
        """
        Main entry point: tries to find and parse ZUGFeRD XML in a PDF.
        Returns a dictionary compatible with our SemanticExtraction.finance_body.
        """
        try:
            doc = fitz.open(pdf_path)
            xml_data = None
            
            # 1. Search for embedded files
            for i in range(doc.embfile_count()):
                name = doc.embfile_info(i)["name"]
                if name.lower() in ["factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml"]:
                    xml_data = doc.embfile_get(i)
                    logger.info(f"Detected embedded ZUGFeRD file: {name}")
                    break
            
            doc.close()
            
            if not xml_data:
                return None
                
            return cls.parse_cii_xml(xml_data)
            
        except Exception as e:
            logger.error(f"Error extracting ZUGFeRD data: {e}")
            return None

    @classmethod
    def parse_cii_xml(cls, xml_bytes: bytes) -> Dict[str, Any]:
        """Parses UN/CEFACT CII XML into our internal FinanceBody structure."""
        root = etree.fromstring(xml_bytes)
        
        # Helper to find text safely
        def t(xpath, context=root):
            elements = context.xpath(xpath, namespaces=cls.NS)
            return elements[0].text if elements else None

        # --- 1. Basic Header (BT-1, BT-2, BT-9) ---
        invoice_number = t("//rsm:ExchangedDocument/ram:ID")
        raw_date = t("//rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString")
        invoice_date = cls._format_zugferd_date(raw_date)
        
        raw_due_date = t("//ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString")
        due_date = cls._format_zugferd_date(raw_due_date)

        currency = t("//ram:ApplicableTradeSettlementMonetarySummation/ram:TaxTotalAmount/@currencyID") or "EUR"

        # --- BT-10 to BT-14 (References) ---
        order_number = t("//ram:ApplicableHeaderTradeAgreement/ram:BuyerOrderReferencedDocument/ram:ID")
        raw_order_date = t("//ram:ApplicableHeaderTradeAgreement/ram:BuyerOrderReferencedDocument/ram:FormattedIssueDateTime/udt:DateTimeString")
        order_date = cls._format_zugferd_date(raw_order_date)
        
        # --- BT-7 / BT-72 (Service/Delivery Date) ---
        raw_service_date = t("//ram:ApplicableTradeSettlement/ram:TaxPointDate/udt:DateTimeString")
        if not raw_service_date:
             raw_service_date = t("//ram:ApplicableTradeSettlement/ram:ActualDeliverySupplyChainEvent/ram:OccurrenceDateTime/udt:DateTimeString")
        service_date = cls._format_zugferd_date(raw_service_date)
        
        customer_id = t("//ram:BuyerTradeParty/ram:ID")
        buyer_reference = t("//ram:ApplicableHeaderTradeAgreement/ram:BuyerReference")

        # --- BT-11, BT-19, BT-20 ---
        project_reference = t("//ram:ApplicableHeaderTradeAgreement/ram:SpecifiedProcurementProject/ram:ID")
        accounting_reference = t("//ram:ApplicableTradeSettlement/ram:ReceivableSpecifiedTradeAccountingAccount/ram:ID")
        payment_terms = t("//ram:SpecifiedTradePaymentTerms/ram:Description")

        # --- Payment Accounts (multiple possible) ---
        payment_accounts = []
        payment_means = root.xpath("//ram:SpecifiedTradeSettlementPaymentMeans", namespaces=cls.NS)
        for pm in payment_means:
            iban = t("ram:PayeePartyCreditorFinancialAccount/ram:IBANID", pm)
            if iban:
                payment_accounts.append({
                    "iban": iban,
                    "bic": t("ram:PayeePartyCreditorFinancialAccount/ram:ProprietaryID", pm) or t("ram:PayeePartyCreditorFinancialAccount/ram:BICID", pm),
                    "bank_name": t("ram:PayeePartyCreditorFinancialInstitution/ram:Name", pm)
                })

        # --- 2. Monetary Summation ---
        summation = root.xpath("//ram:ApplicableTradeSettlementMonetarySummation", namespaces=cls.NS)
        monetary_data = {}
        if summation:
            s = summation[0]
            monetary_data = {
                "line_total_amount": t("ram:LineTotalAmount", s),
                "tax_basis_total_amount": t("ram:TaxBasisTotalAmount", s),
                "tax_total_amount": t("ram:TaxTotalAmount", s),
                "grand_total_amount": t("ram:GrandTotalAmount", s),
                "due_payable_amount": t("ram:DuePayableAmount", s),
            }

        # --- 3. Line Items ---
        items = []
        item_nodes = root.xpath("//ram:IncludedSupplyChainTradeLineItem", namespaces=cls.NS)
        for i, node in enumerate(item_nodes):
            items.append({
                "pos": t("ram:AssociatedDocumentLineDocument/ram:LineID", node) or str(i+1),
                "description": t("ram:SpecifiedTradeProduct/ram:Name", node),
                "quantity": t("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", node),
                "unit": t("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity/@unitCode", node),
                "unit_price": t("ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount", node),
                "total_price": t("ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:NetLineTotalAmount", node),
            })

        # --- 4. Parties (Sender/Recipient) ---
        # Note: We return these so the analyzer can merge them into meta_header
        seller = root.xpath("//ram:SellerTradeParty", namespaces=cls.NS)
        buyer = root.xpath("//ram:BuyerTradeParty", namespaces=cls.NS)
        
        def parse_party(node_list):
            if not node_list: return None
            p = node_list[0]
            return {
                "name": t("ram:Name", p),
                "street": t("ram:PostalTradeAddress/ram:LineOne", p),
                "zip_code": t("ram:PostalTradeAddress/ram:PostcodeCode", p),
                "city": t("ram:PostalTradeAddress/ram:CityName", p),
                "country": t("ram:PostalTradeAddress/ram:CountryID", p),
                "vat_id": t("ram:SpecifiedTaxRegistration/ram:ID[starts-with(., 'DE') or starts-with(@schemeID, 'VA')]", p),
                "iban": t("//ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:IBANID", root) if "Seller" in p.tag else None
            }

        return {
            "meta_data": {
                "sender": parse_party(seller),
                "recipient": parse_party(buyer),
                "doc_number": invoice_number,
                "doc_date": invoice_date,
            },
            "finance_data": {
                "invoice_number": invoice_number,
                "invoice_date": invoice_date,
                "due_date": due_date,
                "currency": currency,
                "order_number": order_number,
                "order_date": order_date,
                "service_date": service_date,
                "customer_id": customer_id,
                "buyer_reference": buyer_reference,
                "project_reference": project_reference,
                "accounting_reference": accounting_reference,
                "payment_terms": payment_terms,
                "payment_accounts": payment_accounts,
                "monetary_summation": monetary_data,
                "line_items": items,
            }
        }

    @staticmethod
    def _format_zugferd_date(val: Optional[str]) -> Optional[str]:
        """Converts YYYYMMDD or other common ZUGFeRD formats to YYYY-MM-DD."""
        if not val: return None
        val = val.strip()
        if len(val) == 8 and val.isdigit():
            # YYYYMMDD
            return f"{val[:4]}-{val[4:6]}-{val[6:]}"
        # Already has dashes or other? 
        return val
