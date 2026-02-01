
import pytest
from datetime import date
from core.models.canonical_entity import CanonicalEntity, DocType, InvoiceData, LogisticsData

class TestCDMModels:
    def test_invoice_model(self):
        # User defined structure
        data = {
            "entity_type": "INVOICE",
            "doc_id": "INV-123",
            "doc_date": "2025-01-01",
            "source_doc_uuid": "mock-uuid",
            "specific_data": {
                "invoice_number": "INV-123",
                "net_amount": 100.00
            }
        }
        entity = CanonicalEntity(**data)
        assert entity.entity_type == DocType.INVOICE
        assert entity.specific_data["invoice_number"] == "INV-123"

    def test_logistics_model(self):
        # User Example A
        data = {
            "entity_type": "DELIVERY_NOTE",
            "doc_id": "LIEF-123",
            "source_doc_uuid": "mock-uuid",
            "specific_data": {
                "logistics": {
                    "delivery_date_expected": "2025-02-01",
                    "tracking_number": "123456789"
                }
            },
            "list_data": [
                 {"pos": 1, "sku": "123", "quantity_delivered": 10}
            ]
        }
        entity = CanonicalEntity(**data)
        assert entity.entity_type == DocType.DELIVERY_NOTE
        # Check specific data access
        logistics = LogisticsData(**entity.specific_data.get("logistics", {}))
        assert logistics.tracking_number == "123456789"
        assert logistics.delivery_date_expected == date(2025, 2, 1)

    def test_bank_statement_model(self):
        # User Example B
        data = {
            "entity_type": "BANK_STATEMENT",
            "source_doc_uuid": "mock-uuid",
            "specific_data": {
                "account_info": { "iban": "DE123" },
                "balances": { "closing_balance": 1500.50 }
            }
        }
        entity = CanonicalEntity(**data)
        assert entity.entity_type == DocType.BANK_STATEMENT
        
    def test_polymorphic_parsing_helper(self):
        # Ideally we want a helper that converts specific_data dict to Typed Model
        pass
