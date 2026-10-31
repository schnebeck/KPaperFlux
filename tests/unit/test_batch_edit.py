import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QLineEdit, QTextEdit
from core.models.virtual import VirtualDocument as Document
from gui.metadata_editor import MetadataEditorWidget
from core.database import DatabaseManager
from core.models.semantic import SemanticExtraction, MetaHeader, AddressInfo, FinanceBody, MonetarySummation

@pytest.fixture
def mock_db():
    return MagicMock(spec=DatabaseManager)

@pytest.fixture
def editor(qtbot, mock_db):
    widget = MetadataEditorWidget(mock_db)
    qtbot.addWidget(widget)
    return widget

def test_display_documents_mixed(editor):
    doc1 = Document(
        uuid="1", 
        original_filename="a.pdf", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(sender=AddressInfo(name="Company A")),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("10.0"))
                )
            }
        )
    )
    doc2 = Document(
        uuid="2", 
        original_filename="b.pdf", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(sender=AddressInfo(name="Company B")),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("10.0"))
                )
            }
        )
    ) 
    
    docs = [doc1, doc2]
    editor.display_documents(docs)
    
    # Check Sender (Mixed)
    assert editor.sender_edit.text() == ""
    assert editor.sender_edit.placeholderText() == "<Multiple Values>"
    
def test_save_changes_batch(editor, mock_db):
    # Setup two documents with same metadata
    doc1 = Document(
        uuid="1", 
        original_filename="a.pdf", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(sender=AddressInfo(name="Company A")),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("10.0"))
                )
            }
        )
    )
    doc2 = Document(
        uuid="2", 
        original_filename="b.pdf", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(sender=AddressInfo(name="Company B")),
            bodies={
                "finance_body": FinanceBody(
                    monetary_summation=MonetarySummation(grand_total_amount=Decimal("10.0"))
                )
            }
        )
    )
    
    editor.display_documents([doc1, doc2])
    
    # User edits SENDER (Mixed -> New Value)
    editor.sender_edit.setText("Common Sender")
    
    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()
    
    # Verify DB calls
    assert mock_db.update_document_metadata.call_count == 2
    
    # Check updates passed for first doc
    args, _ = mock_db.update_document_metadata.call_args_list[0]
    uuid, updates = args
    assert uuid == "1"
    # updates["semantic_data"] is now a SemanticExtraction object
    assert updates["semantic_data"].sender_summary == "Common Sender"




def test_batch_save_without_changes_writes_nothing(editor, mock_db):
    docs = [Document(uuid="1", tags=["a"]), Document(uuid="2", tags=["b"])]
    editor.display_documents(docs)

    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()

    mock_db.update_document_metadata.assert_not_called()


def _invoice(uuid: str, sender: str, total: str, tags: list[str], status: str) -> Document:
    return Document(
        uuid=uuid,
        original_filename=f"{uuid}.pdf",
        status=status,
        tags=tags,
        type_tags=["INVOICE", "INBOUND", "CTX_PRIVATE"],
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(sender=AddressInfo(name=sender)),
            type_tags=["INVOICE", "INBOUND", "CTX_PRIVATE"],
            direction="INBOUND",
            tenant_context="PRIVATE",
            bodies={"finance_body": FinanceBody(
                monetary_summation=MonetarySummation(grand_total_amount=Decimal(total)))},
        ),
    )


@pytest.fixture
def real_db(tmp_path):
    db = DatabaseManager(str(tmp_path / "batch.db"))
    db.init_db()
    db.insert_document(_invoice("doc-a", "Sender A", "10.00", ["alpha", "shared"], "NEW"))
    db.insert_document(_invoice("doc-b", "Sender B", "20.00", ["beta", "shared"], "PROCESSED"))
    db.insert_document(Document(uuid="doc-stale", original_filename="s.pdf", status="ERROR",
                                tags=["stale"], type_tags=["RECEIPT", "OUTBOUND"]))
    return db


@pytest.fixture
def real_editor(qtbot, real_db):
    widget = MetadataEditorWidget(real_db)
    qtbot.addWidget(widget)
    # A previously viewed single document leaves its values in the widgets
    widget.display_documents([real_db.get_document_by_uuid("doc-stale")])
    widget.display_documents([real_db.get_document_by_uuid("doc-a"), real_db.get_document_by_uuid("doc-b")])
    return widget


def _total(db, uuid: str) -> Decimal:
    body = db.get_document_by_uuid(uuid).semantic_data.bodies["finance_body"]
    summation = body["monetary_summation"] if isinstance(body, dict) else body.monetary_summation
    total = summation["grand_total_amount"] if isinstance(summation, dict) else summation.grand_total_amount
    return Decimal(str(total))


def test_batch_shows_common_values_only(real_editor):
    assert real_editor.tags_edit.getTags() == ["shared"]
    assert real_editor.doc_types_combo.getCheckedItems() == ["INVOICE"]
    assert real_editor.direction_combo.currentData() == "Inbound"
    assert real_editor.context_combo.currentData() == "Private"


def test_batch_tag_change_keeps_each_documents_data(real_editor, real_db):
    real_editor.tags_edit.setTags(["shared", "batch"])

    with patch("gui.metadata_editor.show_notification"):
        real_editor.save_changes()

    doc_a = real_db.get_document_by_uuid("doc-a")
    doc_b = real_db.get_document_by_uuid("doc-b")
    assert doc_a.tags == ["alpha", "shared", "batch"]
    assert doc_b.tags == ["beta", "shared", "batch"]
    assert (doc_a.status, doc_b.status) == ("NEW", "PROCESSED")
    assert doc_a.semantic_data.sender_summary == "Sender A"
    assert doc_b.semantic_data.sender_summary == "Sender B"
    assert (_total(real_db, "doc-a"), _total(real_db, "doc-b")) == (Decimal("10.00"), Decimal("20.00"))
    assert doc_a.type_tags == ["INVOICE", "INBOUND", "CTX_PRIVATE"]


def test_batch_tag_removal_applies_to_all(real_editor, real_db):
    real_editor.tags_edit.setTags([])

    with patch("gui.metadata_editor.show_notification"):
        real_editor.save_changes()

    assert real_db.get_document_by_uuid("doc-a").tags == ["alpha"]
    assert real_db.get_document_by_uuid("doc-b").tags == ["beta"]


def test_batch_direction_and_type_change_keeps_bodies(real_editor, real_db):
    real_editor.doc_types_combo.setCheckedItems(["INVOICE", "CONTRACT"])
    real_editor._select_data(real_editor.direction_combo, "Outbound")

    with patch("gui.metadata_editor.show_notification"):
        real_editor.save_changes()

    for uuid, total in (("doc-a", "10.00"), ("doc-b", "20.00")):
        doc = real_db.get_document_by_uuid(uuid)
        assert doc.type_tags == ["INVOICE", "CTX_PRIVATE", "CONTRACT", "OUTBOUND"]
        assert doc.semantic_data.direction == "OUTBOUND"
        assert doc.semantic_data.tenant_context == "PRIVATE"
        assert _total(real_db, uuid) == Decimal(total)


def test_single_save_writes_technical_values_with_translated_labels(editor, mock_db):
    doc = _invoice("doc-a", "Sender A", "10.00", ["alpha"], "NEW")
    editor.display_documents([doc])
    # Simulate a translated UI: labels differ from the technical values
    for combo, labels in ((editor.direction_combo, ["Eingang", "Ausgang", "Intern", "Unbekannt"]),
                          (editor.context_combo, ["Privat", "Geschäftlich", "Unbekannt"])):
        for i, label in enumerate(labels):
            combo.setItemText(i, label)
    editor._select_data(editor.direction_combo, "Outbound")
    editor._select_data(editor.context_combo, "Business")

    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()

    _, updates = mock_db.update_document_metadata.call_args.args
    assert "OUTBOUND" in updates["type_tags"] and "CTX_BUSINESS" in updates["type_tags"]
    assert not any(t in updates["type_tags"] for t in ("AUSGANG", "CTX_GESCHÄFTLICH"))
    assert updates["semantic_data"].direction == "OUTBOUND"
    assert updates["semantic_data"].tenant_context == "BUSINESS"


def test_unrecognised_direction_does_not_keep_previous_selection(editor):
    editor.display_documents([_invoice("doc-a", "Sender A", "10.00", [], "NEW")])
    editor._select_data(editor.direction_combo, "Outbound")

    doc = _invoice("doc-b", "Sender B", "20.00", [], "NEW")
    doc.semantic_data.direction = None
    doc.semantic_data.tenant_context = "something-else"
    editor.display_documents([doc], force=True)

    assert editor.direction_combo.currentData() == "Unknown"
    assert editor.context_combo.currentData() == "Unknown"


def test_nested_table_edit_marks_editor_dirty(editor):
    from PyQt6.QtWidgets import QPushButton, QTableWidgetItem

    editor.display_documents([_invoice("doc-a", "Sender A", "10.00", [], "NEW")])
    editor.semantic_table.setRowCount(1)
    editor.semantic_table.setItem(0, 2, QTableWidgetItem('[{"name": "a"}]'))
    editor.semantic_table.setCellWidget(0, 2, QPushButton())
    callback = editor._make_nested_editor_callback("finance.line_items", '[{"name": "a"}]', 0)

    with patch("gui.metadata_editor.NestedTableDialog") as dialog, \
         patch("gui.metadata_editor.show_selectable_message_box") as error_box:
        dialog.return_value.exec.return_value = True
        dialog.return_value.get_data.return_value = [{"name": "a"}, {"name": "b"}]
        callback()

    error_box.assert_not_called()
    assert editor.is_dirty()
    assert editor.semantic_table.cellWidget(0, 2).text() == "Open Table (2 item(s))"
    assert "b" in editor.semantic_table.item(0, 2).text()


def _saved_bodies(mock_db) -> dict:
    _, updates = mock_db.update_document_metadata.call_args.args
    return updates["semantic_data"].bodies


def test_subscription_tab_edit_is_saved(editor, mock_db):
    editor.display_documents([_invoice("doc-a", "Sender A", "10.00", [], "NEW")])
    editor.chk_sub_recurring.setChecked(True)

    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()

    assert _saved_bodies(mock_db)["subscription_info"].is_recurring is True


def test_document_without_contract_data_gets_no_legal_body(editor, mock_db):
    editor.display_documents([_invoice("doc-a", "Sender A", "10.00", [], "NEW")])
    editor.storage_location_edit.setText("Box A")

    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()

    bodies = _saved_bodies(mock_db)
    assert "legal_body" not in bodies
    assert "subscription_info" not in bodies


def test_payment_tab_edit_wins_over_unchanged_subscription_tab(editor, mock_db):
    editor.display_documents([_invoice("doc-a", "Sender A", "10.00", [], "NEW")])
    editor.chk_pay_recurring.setChecked(True)

    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()

    assert _saved_bodies(mock_db)["subscription_info"].is_recurring is True
