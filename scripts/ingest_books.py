"""
Ingest cycling training books into knowledge base
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rag.knowledge_base import KnowledgeBase
import os


# Automatically discover all PDFs in data/books/
books_dir = Path("data/books")
BOOKS = []

print("Scanning for PDF files...")
for pdf_file in sorted(books_dir.glob("*.pdf")):
    # Use filename as name
    BOOKS.append({
        "path": str(pdf_file),
        "name": pdf_file.stem.replace("-", " ").replace("_", " "),
        "author": "Research Papers & Books",
    })

print(f"Found {len(BOOKS)} PDF files to ingest\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Trainer Agent - Book Ingestion")
    print("=" * 60)

    kb = KnowledgeBase()

    # Initialize collection
    print("\n[1/3] Initializing knowledge base...")
    kb.initialize()

    # Ingest books
    print("\n[2/3] Ingesting training books...")
    for book in BOOKS:
        if Path(book["path"]).exists():
            print(f"\n  -> {book['name']}")
            kb.ingest_book(book["path"], book["name"], book["author"])
        else:
            print(f"\n  WARNING: Book not found at {book['path']}")

    # Test query
    print("\n[3/3] Testing retrieval...")
    print("-" * 60)
    results = kb.query("What is FTP and how do you test it?", limit=2)
    print(f"Query: 'What is FTP and how do you test it?'")
    print(f"Found {len(results)} results:\n")

    for i, result in enumerate(results):
        print(f"Result {i+1} (Score: {result['score']:.3f})")
        print(f"Source: {result['metadata'].get('source', 'Unknown')}")
        print(f"Text preview: {result['text'][:200]}...")
        print()

    print("=" * 60)
    print("SUCCESS: Ingestion complete!")
    print("=" * 60)
