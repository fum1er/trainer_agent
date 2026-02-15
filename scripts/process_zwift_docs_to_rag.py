"""
Process Zwift workout documents and add them to the RAG knowledge base
"""
import sys
from pathlib import Path
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rag.document_processor import DocumentProcessor
from src.rag.knowledge_base import KnowledgeBase


def main():
    parser = argparse.ArgumentParser(description='Process Zwift workout documents into RAG')
    parser.add_argument('--source', type=str, default='data/zwift_rag_docs',
                        help='Source directory containing workout text files')
    parser.add_argument('--chunk-size', type=int, default=800,
                        help='Chunk size for text splitting')
    parser.add_argument('--chunk-overlap', type=int, default=200,
                        help='Chunk overlap')

    args = parser.parse_args()

    print("=" * 60)
    print("PROCESS ZWIFT WORKOUTS INTO RAG")
    print("=" * 60)

    source_path = Path(args.source)

    if not source_path.exists():
        print(f"\nError: Source directory not found: {source_path}")
        print("Run generate_rag_docs_from_zwift.py first!")
        return

    # Count files
    txt_files = list(source_path.glob("*.txt"))
    if not txt_files:
        print(f"\nNo .txt files found in {source_path}")
        return

    print(f"\nFound {len(txt_files)} workout documents")
    print(f"Chunk size: {args.chunk_size}")
    print(f"Chunk overlap: {args.chunk_overlap}\n")

    # Initialize processor and knowledge base
    processor = DocumentProcessor(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap
    )
    kb = KnowledgeBase()

    print("Processing documents...")

    # Process all documents in batches
    processed_count = 0
    error_count = 0
    all_documents = []
    all_texts = []

    # First pass: chunk all documents
    for txt_file in txt_files:
        try:
            # Read document
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Process (chunk)
            chunks = processor.chunk_text(
                content,
                metadata={'source': 'zwift_workout', 'filename': txt_file.name, 'type': 'workout'}
            )

            all_documents.extend(chunks)
            all_texts.extend([c['text'] for c in chunks])

            processed_count += 1

            if processed_count % 100 == 0:
                print(f"  Chunked {processed_count}/{len(txt_files)}...")

        except Exception as e:
            print(f"  Error processing {txt_file.name}: {e}")
            error_count += 1
            continue

    # Second pass: embed and store in batches
    print(f"\nGenerating embeddings for {len(all_documents)} chunks...")
    embeddings = kb.embedder.generate_batch(all_texts)

    print(f"Storing in Qdrant in batches...")
    batch_size = 100
    total_batches = (len(all_documents) + batch_size - 1) // batch_size

    for i in range(0, len(all_documents), batch_size):
        batch_docs = all_documents[i:i + batch_size]
        batch_embeddings = embeddings[i:i + batch_size]

        batch_num = (i // batch_size) + 1
        print(f"  Uploading batch {batch_num}/{total_batches} ({len(batch_docs)} chunks)...")

        kb.vector_store.upsert_documents(batch_docs, batch_embeddings)

    print(f"\n{'='*60}")
    print("DONE!")
    print(f"{'='*60}")
    print(f"Processed: {processed_count} documents")
    print(f"Errors: {error_count}")
    print(f"\nZwift workouts are now searchable in the RAG!")


if __name__ == "__main__":
    main()
