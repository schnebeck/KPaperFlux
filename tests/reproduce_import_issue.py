
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core.pipeline import PipelineProcessor
from core.database import DatabaseManager
from core.utils.zugferd_extractor import ZugferdExtractor
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction

def test_repro_document_import():
    file_path = "/home/schnebeck/Transfer/doc00602820260216111753.pdf"
    if not os.path.exists(file_path):
        print(f"Skipping: File not found: {file_path}")
        return

    print(f"--- Diagnosing: {file_path} ---")

    # 1. Test ZUGFeRD extraction directly
    print("\n1. Testing ZUGFeRD Extraction...")
    zugferd = ZugferdExtractor.extract_from_pdf(file_path)
    if zugferd:
        print("SUCCESS: ZUGFeRD XML found and parsed.")
        fin = zugferd.get("finance_data", {})
        print(f"  Sender: {zugferd.get('meta_data', {}).get('sender', {}).get('name')}")
        print(f"  Doc Number: {fin.get('invoice_number')}")
        print(f"  Line Items Count: {len(fin.get('line_items', []))}")
        if fin.get('line_items'):
            print(f"  First item: {fin['line_items'][0]}")
    else:
        print("FAILURE: No ZUGFeRD data found.")

    # 2. Test Pipeline Ingestion (Stage 0)
    print("\n2. Testing Pipeline Ingestion (Stage 0)...")
    db_path = ":memory:"
    # Use a fresh temp vault for each run if needed, but here we just want to see the text
    vault_path = Path("/tmp/kpaperflux_test_vault_" + str(int(time.time())))
    vault_path.mkdir(parents=True, exist_ok=True)
    
    pipeline = PipelineProcessor(base_path=str(vault_path), db_path=db_path)
    
    try:
        is_native = pipeline._is_native_pdf(Path(file_path))
        print(f"  Is Native PDF (Text Layer): {is_native}")
        
        doc = pipeline.process_document(file_path, skip_ai=True)
        print(f"SUCCESS: Document ingested into pipeline. UUID: {doc.uuid}")
        
        # Check source mapping
        print(f"  Source Mapping: {doc.source_mapping}")
        
        # Check Physical File
        pf_uuid = doc.source_mapping[0].file_uuid
        pf = pipeline.physical_repo.get_by_uuid(pf_uuid)
        print(f"  Physical File UUID: {pf.uuid}")
        print(f"  Physical Page Count: {pf.page_count_phys}")
        
        # Analyze Text Density and Layout
        if pf.raw_ocr_data:
            text_1 = pf.raw_ocr_data.get("1", "")
            print(f"  Page 1 Text Length: {len(text_1)} characters")
            print(f"  Page 1 Snippet (Start):\n{text_1[:600]}")
            
            # Check for many single-character lines which might indicate vertical reading of landscape
            lines = text_1.split('\n')
            short_lines = [l for l in lines if len(l.strip()) == 1]
            if len(short_lines) > 20:
                print(f"  WARNING: Detected {len(short_lines)} single-character lines. Possible rotation issue!")
            
            # Check for DigiKey specific markers to see if they are garbled
            if "DigiKey" in text_1:
                print("  INFO: 'DigiKey' found in text layer.")
            else:
                print("  WARNING: 'DigiKey' NOT found in text layer. Extraction might be poor.")
            
    except Exception as e:
        print(f"FAILURE: Ingestion failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_repro_document_import()
