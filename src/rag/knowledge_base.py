"""
High-level knowledge base interface for RAG pipeline
"""
from .embeddings import EmbeddingGenerator
from .vector_store import QdrantVectorStore
from .document_processor import DocumentProcessor
from typing import List, Dict, Any


class KnowledgeBase:
    """High-level interface for cycling training knowledge base"""

    def __init__(self):
        self.embedder = EmbeddingGenerator()
        self.vector_store = QdrantVectorStore()
        self.processor = DocumentProcessor()

    def initialize(self):
        """Initialize knowledge base (create collection)"""
        self.vector_store.create_collection()

    def ingest_book(self, pdf_path: str, book_name: str, author: str):
        """
        Ingest a training book into the knowledge base

        Args:
            pdf_path: Path to PDF file
            book_name: Name of the book
            author: Author name
        """
        # Process book into chunks
        documents = self.processor.process_book(pdf_path, book_name, author)

        # Generate embeddings
        texts = [doc["text"] for doc in documents]
        embeddings = self.embedder.generate_batch(texts)

        # Store in Qdrant
        self.vector_store.upsert_documents(documents, embeddings)

    def query(self, question: str, limit: int = 5, score_threshold: float = 0.0, metadata_filter: dict = None) -> List[Dict[str, Any]]:
        """
        Query the knowledge base

        Args:
            question: User question
            limit: Number of results to return
            score_threshold: Minimum similarity score (0.0-1.0), 0.0 = no filtering
            metadata_filter: Optional filter on metadata fields, e.g. {"type": "workout"}

        Returns:
            List of relevant passages with metadata and scores
        """
        # Generate query embedding
        query_embedding = self.embedder.generate(question)

        # Search in vector store
        results = self.vector_store.search(query_embedding, limit=limit, metadata_filter=metadata_filter)

        # Filter by score threshold
        if score_threshold > 0:
            results = [r for r in results if r.get("score", 0) >= score_threshold]

        return results
