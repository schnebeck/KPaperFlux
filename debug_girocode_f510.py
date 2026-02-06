
import json
from decimal import Decimal
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction

# Data from sqlite3
raw_semantic = {
    "meta_header": {
        "sender": {
            "name": "Modellbau Berthold",
            "iban": "DE87765600600003200132",
            "bic": "GENODEF1ANS",
            "bank_name": "VR-Bank Mittelfranken Mitte eG"
        }
    },
    "bodies": {
        "finance_body": {
            "total_gross": 16.9,
            "payment_accounts": [
                {
                    "bank_name": "VR-Bank Mittelfranken Mitte eG",
                    "account_holder": "Modellbau Berthold",
                    "iban": "DE87 7656 0060 0003 2001 32",
                    "bic": "GENODEF1ANS"
                }
            ]
        }
    }
}

doc = VirtualDocument(
    uuid="f51049bf-27e9-452f-9b49-bb742cb62409",
    type_tags=["INVOICE", "INBOUND", "CTX_BUSINESS"],
    semantic_data=SemanticExtraction(**raw_semantic)
)

print(f"UUID: {doc.uuid}")
print(f"Type Tags: {doc.type_tags}")
print(f"Sender Name: {doc.sender_name}")
print(f"IBAN: {doc.iban}")
print(f"BIC: {doc.bic}")
print(f"Bank Name: {doc.bank_name}")
print(f"Total Amount: {doc.total_amount}")

is_financial = any(t in ["INVOICE", "RECEIPT", "UTILITY_BILL"] for t in (doc.type_tags or []))
print(f"Is Financial: {is_financial}")
print(f"Condition for Tab: {is_financial or doc.iban or doc.total_amount}")
