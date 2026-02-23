"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/semantic_translator.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Translates abstract metadata keys into localized UI strings.
                Source language is English. Supports integration with Qt
                Linguist via QObject.tr().
------------------------------------------------------------------------------
"""

from typing import Optional

from PyQt6.QtCore import QObject


class SemanticTranslator(QObject):
    """
    Translates abstract keys from type_definitions.json into localized UI strings.
    Source language is English. Use Qt Linguist to translate to German/others.
    """

    _instance: Optional['SemanticTranslator'] = None

    @classmethod
    def instance(cls) -> 'SemanticTranslator':
        """
        Singleton access to the SemanticTranslator.

        Returns:
            The global SemanticTranslator instance.
        """
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def tr(self, text: str, disambiguation: Optional[str] = None, n: int = -1) -> str:
        """
        Expose QObject.tr for easier access.
        """
        return super().tr(text, disambiguation, n)

    def translate(self, key: str) -> str:
        """
        Maps a key (e.g. 'type_invoice') to a translated string.

        Args:
            key: The abstract metadata key string.

        Returns:
            The localized string.
        """
        match key:
            # Types
            case "type_invoice":
                return self.tr("Invoice")
            case "type_contract":
                return self.tr("Contract")
            case "type_letter":
                return self.tr("Letter")

            # Fields - Invoice
            case "field_invoice_number":
                return self.tr("Invoice Number")
            case "field_invoice_date":
                return self.tr("Invoice Date")
            case "field_due_date":
                return self.tr("Due Date")
            case "field_customer_id":
                return self.tr("Customer ID")
            case "field_order_id":
                return self.tr("Order ID")

            # Fields - Contract
            case "field_contract_id":
                return self.tr("Contract ID")
            case "field_start_date":
                return self.tr("Start Date")
            case "field_end_date":
                return self.tr("End Date")
            case "field_cancellation_period":
                return self.tr("Cancellation Period")

            # Fields - Letter
            case "field_subject":
                return self.tr("Subject")
            case "field_our_ref":
                return self.tr("Our Reference")

            # Fields - New Financial (Phase 84)
            case "field_tax_amount":
                return self.tr("Tax Amount")
            case "field_tax_rate":
                return self.tr("Tax Rate")
            case "field_iban":
                return self.tr("IBAN")
            case "field_cost_center":
                return self.tr("Cost Center")
            case "field_project_id":
                return self.tr("Project ID")
            case "field_incoterms":
                return self.tr("Incoterms")
            case "field_delivery_date":
                return self.tr("Delivery Date")

            # Filter Tokens - Basis
            case "field_doc_date":
                return self.tr("Document Date")
            case "field_classification":
                return self.tr("Classification")
            case "field_status":
                return self.tr("Status")
            case "field_tags":
                return self.tr("Tags")
            case "field_type_tags":
                return self.tr("System Tags")
            case "field_workflow_step":
                return self.tr("Workflow Step")
            case "field_full_text":
                return self.tr("Full Text")

            # Filter Tokens - AI
            case "field_direction":
                return self.tr("Direction")
            case "field_tenant_context":
                return self.tr("Context")
            case "field_ai_confidence":
                return self.tr("AI Confidence")
            case "field_ai_reasoning":
                return self.tr("AI Reasoning")

            # Filter Tokens - Stamps
            case "field_stamp_text_total":
                return self.tr("Stamp Text (Total)")
            case "field_stamp_type":
                return self.tr("Stamp Type")
            case "field_audit_mode":
                return self.tr("Audit Mode")

            # Filter Tokens - System
            case "field_filename":
                return self.tr("Filename")
            case "field_pages":
                return self.tr("Pages")
            case "field_uuid":
                return self.tr("UUID")
            case "field_created_at":
                return self.tr("Created At")
            case "field_processed_at":
                return self.tr("Processed At")
            case "field_in_trash":
                return self.tr("In Trash")

            # Generic
            case "Date":
                return self.tr("Date")
            case "Sender":
                return self.tr("Sender")
            case "Content":
                return self.tr("Content")
            case "Net Amount":
                return self.tr("Net Amount")
            case "Tax Rate":
                return self.tr("Tax Rate")
            case "Gross Amount":
                return self.tr("Gross Amount")
            case "Currency":
                return self.tr("Currency")
            case "Recipient":
                return self.tr("Recipient")
            case "IBAN":
                return self.tr("IBAN")
            case "Filename":
                return self.tr("Filename")
            case "File Link":
                return self.tr("File Link")

            # Generic / Segments
            case "bodies":
                return self.tr("Contents")
            case "meta_header":
                return self.tr("Meta Header")
            case "finance_body":
                return self.tr("Financial Data")
            case "legal_body":
                return self.tr("Legal Data")
            case "repaired_text":
                return self.tr("Repaired Text")
            case "visual_audit":
                return self.tr("Visual Audit")
            case "workflow":
                return self.tr("Workflow")
            
            # Workflow Segments
            case "current_step":
                return self.tr("Current Step")
            case "history":
                return self.tr("History")
            case "is_verified":
                return self.tr("Is Verified")
            case "pkv_eligible":
                return self.tr("Pkv Eligible")
            case "pkv_status":
                return self.tr("Pkv Status")
            case "rule_id":
                return self.tr("Rule Id")
            case "signature_detected":
                return self.tr("Signature Detected")
            case "verified_at":
                return self.tr("Verified At")
            case "verified_by":
                return self.tr("Verified By")

            # IMPLIED / Stamp Fields
            case "IMPLIED_BARCODE_VALUE":
                return self.tr("Barcode Value")
            case "IMPLIED_CODE":
                return self.tr("Code")
            case "IMPLIED_DATE_CODE":
                return self.tr("Date Code")
            case "IMPLIED_NUMBER":
                return self.tr("Number")
            case "IMPLIED_QR_CODE_DATA":
                return self.tr("QR Code Data")
            case "IMPLIED_QR_CODE_TYPE":
                return self.tr("QR Code Type")
            case "IMPLIED_SIGNATURE":
                return self.tr("Signature")
            case "IMPLIED_TEXT":
                return self.tr("Text")
            case "IMPLIED_TIME":
                return self.tr("Time")

            # Nested Workflow / Misc
            case "action":
                return self.tr("Action")
            case "comment":
                return self.tr("Comment")
            case "timestamp":
                return self.tr("Timestamp")
            case "user":
                return self.tr("User")

            # Fallback
            case _:
                return key

    def beautify_key(self, key: str) -> str:
        """
        Cleans up a technical key for UI display.
        Removes 'semantic:' prefix, replaces underscores with spaces, and capitalizes.
        """
        # 1. Remove Prefix
        clean = key
        if clean.startswith("semantic:"):
            clean = clean[9:]
        elif clean.startswith("field:"): # Used for some stamps/raw fields
            clean = clean[6:]
            
        # 2. Check if it's a known token ID
        from core.filter_token_registry import FilterTokenRegistry
        registry = FilterTokenRegistry.instance()
        token = registry.get_token(clean)
        if token:
            return self.translate(token.label_key)
            
        # 3. Check if there's a direct translation for the cleaned key
        trans = self.translate(clean)
        if trans != clean:
            return trans
            
        # 4. Beautify segments
        parts = clean.split(".")
        beautified_parts = []
        for p in parts:
            # Map common technical terms (many already in translate())
            p_map = {
                "bodies": self.tr("Contents"),
                "finance_body": self.tr("Financial Data"),
                "legal_body": self.tr("Legal Data"),
                "meta_header": self.tr("Meta Header"),
                "repaired_text": self.tr("Repaired Text"),
                "visual_audit": self.tr("Visual Audit"),
                "workflow": self.tr("Workflow"),
                "iban": "IBAN",
                "bic": "BIC",
                "vat_id": "VAT-ID",
                "tax_amount": self.tr("Tax Amount"),
                "tax_rate": self.tr("Tax Rate"),
                "total_amount": self.tr("Total Amount"),
                "currency": self.tr("Currency")
            }
            if p in p_map:
                beautified_parts.append(p_map[p])
            else:
                # Direct check against translate() for segments
                seg_trans = self.translate(p)
                if seg_trans != p:
                    beautified_parts.append(seg_trans)
                else:
                    # Fallback: Underscores to spaces, Capitalize
                    beautified_parts.append(p.replace("_", " ").title())
                
        return " > ".join(beautified_parts)
