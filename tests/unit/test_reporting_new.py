
import pytest
from decimal import Decimal
from core.reporting import ReportGenerator
from core.utils.girocode import GiroCodeGenerator
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, MetaHeader, AddressInfo, FinanceBody, MonetarySummation, TaxBreakdownRow

@pytest.fixture
def sample_docs():
    d1 = VirtualDocument(
        uuid="doc-1",
        type_tags=["INVOICE"],
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(
                doc_date="2026-01-15",
                sender=AddressInfo(company="Sender A", iban="DE123456789")
            ),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(
                        grand_total_amount=Decimal("119.00"), 
                        tax_basis_total_amount=Decimal("100.00"), 
                        tax_total_amount=Decimal("19.00")
                    ),
                    tax_breakdown=[
                        TaxBreakdownRow(tax_basis_amount=Decimal("100.00"), tax_rate=Decimal("19.00"), tax_amount=Decimal("19.00"))
                    ]
                )
            }
        )
    )
    d2 = VirtualDocument(
        uuid="doc-2",
        type_tags=["RECEIPT"],
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(
                doc_date="2026-01-20",
                sender=AddressInfo(name="Store B")
            ),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("50.00"))
                )
            }
        )
    )
    d3 = VirtualDocument(
        uuid="doc-3",
        type_tags=["INVOICE"],
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(
                doc_date="2026-02-01",
                sender=AddressInfo(company="Sender C")
            ),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("200.00"))
                )
            }
        )
    )
    return [d1, d2, d3]

def test_monthly_summary(sample_docs):
    summary = ReportGenerator.get_monthly_summary(sample_docs)
    assert "2026-01" in summary
    assert "2026-02" in summary
    assert summary["2026-01"]["gross"] == Decimal("169.00")
    assert summary["2026-02"]["gross"] == Decimal("200.00")

def test_tax_summary(sample_docs):
    tax = ReportGenerator.get_tax_summary(sample_docs)
    assert "19%" in tax
    assert tax["19%"] == Decimal("19.00")

def test_girocode_payload():
    payload = GiroCodeGenerator.generate_payload(
        recipient_name="Max Mustermann",
        iban="DE123456789",
        amount=123.45,
        purpose="Invoice 123"
    )
    assert "BCD" in payload
    assert "Max Mustermann" in payload
    assert "EUR123.45" in payload
    assert "Invoice 123" in payload
