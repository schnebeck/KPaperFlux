
from core.document import Document
import uuid

def main():
    try:
        print("Attempting to create Document with original_filename=None")
        doc = Document(uuid=str(uuid.uuid4()), original_filename=None)
        print("Success: Document created.", doc.original_filename)
    except Exception as e:
        print(f"Failed: {e}")

    try:
        print("Attempting to create Document with NO original_filename arg")
        doc2 = Document(uuid=str(uuid.uuid4()))
        print("Success: Document 2 created.", doc2.original_filename)
    except Exception as e:
        print(f"Failed 2: {e}")

if __name__ == "__main__":
    main()
