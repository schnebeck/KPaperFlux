import pytest
import os
import json
import fitz
from core.filter_tree import FilterTree, NodeType
from core.exchange import ExchangeService, ExchangePayload

def test_filter_tree_exchange_persistence(tmp_path):
    """Test that the entire FilterTree can be saved and loaded via ExchangeService."""
    tree = FilterTree()
    folder = tree.add_folder(tree.root, "Accounting")
    tree.add_filter(folder, "Tax Returns", {"year": 2023})
    
    # Path for exchange file
    target = os.path.join(tmp_path, "filters.kpfx")
    
    # 1. Save using ExchangeService
    # We save the full data
    tree_data = json.loads(tree.to_json())
    ExchangeService.save_to_file("filter_tree", tree_data, target)
    
    assert os.path.exists(target)
    
    # 2. Load and verify
    with open(target, "r") as f:
        payload = ExchangePayload.model_validate_json(f.read())
        
    assert payload.type == "filter_tree"
    assert payload.payload["root"]["children"][0]["name"] == "Accounting"
    
    # 3. Restore to a new tree
    new_tree = FilterTree()
    new_tree.load(payload.payload)
    assert len(new_tree.root.children) == 1
    assert new_tree.root.children[0].name == "Accounting"

def test_filter_node_exchange_embedding(tmp_path):
    """Test embedding an individual filter node into a PDF."""
    tree = FilterTree()
    node = tree.add_filter(tree.root, "ExportMe", {"op": "equal"})
    
    # Create dummy PDF
    doc = fitz.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()
    
    # Embed as 'smart_list' (individual filter)
    embedded_pdf = ExchangeService.embed_in_pdf(pdf_bytes, "smart_list", node.to_dict())
    
    pdf_path = os.path.join(tmp_path, "embedded_filter.pdf")
    with open(pdf_path, "wb") as f:
        f.write(embedded_pdf)
        
    # Extract
    payload = ExchangeService.extract_from_pdf(pdf_path)
    assert payload is not None
    assert payload.type == "smart_list"
    assert payload.payload["name"] == "ExportMe"
    assert payload.payload["type"] == "filter"
