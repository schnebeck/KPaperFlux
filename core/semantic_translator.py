"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/semantic_translator.py
Version:        1.2.0
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

            # Fallback
            case _:
                return key
