import pytest
from decimal import Decimal
from datetime import datetime
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, MetaHeader, FinanceBody, MonetarySummation, TaxBreakdownRow

# We will implement ReportGenerator and FinancialModule
# For now, we define the requirement via tests

def test_financial_aggregation_empty():
    """Requirement: Reporting engine handles empty document lists gracefully."""
    from core.reporting import ReportGenerator
    
    summary = ReportGenerator.get_monthly_summary([])
    assert summary == {}

def test_financial_aggregation_by_month():
    """Requirement: Aggregates total_amount from documents grouped by month."""
    from core.reporting import ReportGenerator
    
    # Setup test data
    doc1 = VirtualDocument(
        uuid="doc1",
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(doc_date="2023-01-15"),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(
                        grand_total_amount=Decimal("100.50"), 
                        tax_basis_total_amount=Decimal("84.45")
                    )
                )
            }
        )
    )
    doc2 = VirtualDocument(
        uuid="doc2",
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(doc_date="2023-01-20"),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(
                        grand_total_amount=Decimal("50.00"), 
                        tax_basis_total_amount=Decimal("42.02")
                    )
                )
            }
        )
    )
    doc3 = VirtualDocument(
        uuid="doc3",
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(doc_date="2023-02-05"),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(
                        grand_total_amount=Decimal("200.00"), 
                        tax_basis_total_amount=Decimal("168.07")
                    )
                )
            }
        )
    )
    
    monthly = ReportGenerator.get_monthly_summary([doc1, doc2, doc3])
    
    assert monthly["2023-01"]["gross"] == Decimal("150.50")
    assert monthly["2023-01"]["net"] == Decimal("126.47")
    assert monthly["2023-02"]["gross"] == Decimal("200.00")
    assert len(monthly) == 2

def test_csv_export_format():
    """Requirement: Generates Excel-friendly CSV with UTF-8-SIG."""
    from core.reporting import ReportGenerator
    
    doc = VirtualDocument(
        original_filename="test.pdf",
        type_tags=["INVOICE"],
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(doc_date="2023-01-01", doc_number="RE-001"),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("42.00"))
                )
            }
        )
    )
    
    content = ReportGenerator.export_to_csv([doc])
    
    # Check for UTF-8-SIG BOM
    assert content.startswith(b'\xef\xbb\xbf')
    
    # Check for content (as string, skipping BOM)
    csv_text = content[3:].decode("utf-8")
    assert "RE-001" in csv_text
    assert "42.00" in csv_text
    assert "INVOICE" in csv_text

def test_tax_aggregation():
    """Requirement: Aggregates tax amounts grouped by tax rate."""
    from core.reporting import ReportGenerator
    
    doc1 = VirtualDocument(
        semantic_data=SemanticExtraction(
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("119.00")),
                    tax_breakdown=[TaxBreakdownRow(tax_basis_amount=Decimal("100.00"), tax_rate=Decimal("19.00"), tax_amount=Decimal("19.00"))]
                )
            }
        )
    )
    doc2 = VirtualDocument(
        semantic_data=SemanticExtraction(
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("107.00")),
                    tax_breakdown=[TaxBreakdownRow(tax_basis_amount=Decimal("100.00"), tax_rate=Decimal("7.00"), tax_amount=Decimal("7.00"))]
                )
            }
        )
    )
    doc3 = VirtualDocument(
        semantic_data=SemanticExtraction(
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("59.50")),
                    tax_breakdown=[TaxBreakdownRow(tax_basis_amount=Decimal("50.00"), tax_rate=Decimal("19.00"), tax_amount=Decimal("9.50"))]
                )
            }
        )
    )
    
    tax_summary = ReportGenerator.get_tax_summary([doc1, doc2, doc3])
    
    assert tax_summary["19%"] == Decimal("28.50")
    assert tax_summary["7%"] == Decimal("7.00")
    assert len(tax_summary) == 2
