
import fitz
import os
from pathlib import Path

def check_demos():
    orig_dir = Path("/home/schnebeck/Dokumente/Projects/KPaperFlux/tests/resources/demo_invoices_complex")
    if not orig_dir.exists():
        print(f"Directory {orig_dir} does not exist.")
        return

    for i in range(1, 30):
        found = list(orig_dir.glob(f"Demo_{i:02d}_*.pdf"))
        if not found:
            continue
        
        pdf_path = found[0]
        doc = fitz.open(pdf_path)
        img_count = 0
        for page in doc:
            img_count += len(page.get_images(full=True))
        
        print(f"{pdf_path.name}: {img_count} images found.")
        doc.close()

if __name__ == "__main__":
    check_demos()
