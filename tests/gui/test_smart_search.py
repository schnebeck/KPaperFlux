
import pytest
from core.query_parser import QueryParser
from gui.filter_widget import FilterWidget
from gui.document_list import DocumentListWidget
from core.database import DatabaseManager
from core.document import Document
from PyQt6.QtCore import QDate

def test_query_parser():
    parser = QueryParser()
    
    # Test 1: Date and Text
    q1 = "Amazon 2024"
    res1 = parser.parse(q1)
    assert res1['date_from'] == "2024-01-01"
    assert res1['date_to'] == "2024-12-31"
    assert res1['text_search'] == "amazon"
    
    # Test 2: Type and Text
    q2 = "Rechnung from Vendor"
    res2 = parser.parse(q2)
    assert res2['type'] == "Invoice"
    assert "vendor" in res2['text_search']
    
    # Test 3: Mixed
    q3 = "2023 receipt custom"
    res3 = parser.parse(q3)
    assert res3['date_from'] == "2023-01-01"
    assert res3['type'] == "Receipt"
    assert res3['text_search'] == "custom"

def test_smart_filter_widget(qtbot):
    widget = FilterWidget()
    qtbot.addWidget(widget)
    
    with qtbot.waitSignal(widget.filter_changed) as blocker:
        widget.txt_smart_search.setText("Amazon 2024")
        widget.txt_smart_search.returnPressed.emit()
        # widget.emit_smart_filter()
        
    criteria = blocker.args[0]
    assert criteria['date_from'] == "2024-01-01"
    assert criteria['text_search'] == "amazon"

@pytest.fixture
def db_with_docs(tmp_path):
    db_path = tmp_path / "smart_test.db"
    db = DatabaseManager(str(db_path))
    db.init_db()
    
    d1 = Document(uuid="1", original_filename="inv.pdf", doc_date="2024-05-01", sender="Amazon", doc_type="Invoice")
    d2 = Document(uuid="2", original_filename="rec.pdf", doc_date="2023-05-01", sender="Google", doc_type="Receipt")
    d3 = Document(uuid="3", original_filename="letter.pdf", doc_date="2024-06-01", sender="Ebay", doc_type="Letter", tags="urgent")
    
    db.insert_document(d1)
    db.insert_document(d2)
    db.insert_document(d3)
    return db

def test_smart_list_filtering(qtbot, db_with_docs):
    widget = DocumentListWidget(db_with_docs)
    qtbot.addWidget(widget)
    widget.refresh_list()
    
    assert widget.rowCount() == 3
    
    # Query: "2024"
    widget.apply_filter({'date_from': '2024-01-01', 'date_to': '2024-12-31'})
    # Should hide 2023 (doc2) -> UUID 2
    # Row indices might vary, verify visibility by content or count
    shown = 0
    for r in range(3):
        if not widget.isRowHidden(r): shown += 1
    assert shown == 2 # Amazon (2024), Ebay (2024)
    
    # Query: "Amazon" (Text)
    widget.apply_filter({'text_search': 'amazon'})
    shown = 0
    for r in range(3):
        if not widget.isRowHidden(r): 
            # Verify it is Amazon
            sender = widget.item(r, 1).text()
            assert sender == "Amazon"
            shown += 1
    assert shown == 1
    
    # Query: "Letter urgent" (Type + Tag in text)
    # QueryParser would output: type=Letter, text_search=urgent
    widget.apply_filter({'type': 'Letter', 'text_search': 'urgent'})
    shown = 0
    for r in range(3):
         if not widget.isRowHidden(r):
             assert widget.item(r, 1).text() == "Ebay"
             shown += 1
    assert shown == 1
