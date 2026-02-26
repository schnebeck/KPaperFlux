import pytest
from core.models.semantic import SemanticExtraction, SubscriptionInfo
from decimal import Decimal

def test_subscription_info_model():
    """Verify that SubscriptionInfo can be parsed into SemanticExtraction bodies."""
    raw_data = {
        "is_recurring": True,
        "frequency": "MONTHLY",
        "service_period_start": "2024-01-01",
        "service_period_end": "2024-01-31",
        "next_billing_date": "2024-02-01"
    }
    
    sd_dict = {
        "bodies": {
            "subscription_info": raw_data
        }
    }
    
    sd = SemanticExtraction.model_validate(sd_dict)
    
    assert "subscription_info" in sd.bodies
    sub = sd.bodies["subscription_info"]
    assert isinstance(sub, SubscriptionInfo)
    assert sub.is_recurring is True
    assert sub.frequency == "MONTHLY"
    assert sub.service_period_start == "2024-01-01"

def test_subscription_info_missing_fields():
    """Verify that SubscriptionInfo handles defaults correctly."""
    sd_dict = {
        "bodies": {
            "subscription_info": {"is_recurring": False}
        }
    }
    sd = SemanticExtraction.model_validate(sd_dict)
    sub = sd.bodies["subscription_info"]
    assert sub.is_recurring is False
    assert sub.frequency is None
    assert sub.next_billing_date is None
