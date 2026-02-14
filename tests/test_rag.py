"""
Unit tests for RAG pipeline
"""
import pytest
from src.rag.document_processor import DocumentProcessor


def test_text_chunking():
    """Test document chunking"""
    processor = DocumentProcessor(chunk_size=100, chunk_overlap=20)
    text = "A" * 250
    chunks = processor.chunk_text(text)

    assert len(chunks) > 1
    assert all("text" in chunk for chunk in chunks)
    assert all("metadata" in chunk for chunk in chunks)


def test_chunk_metadata():
    """Test chunk metadata"""
    processor = DocumentProcessor(chunk_size=100, chunk_overlap=20)
    text = "Test " * 100
    metadata = {"source": "Test Book", "author": "Test Author"}
    chunks = processor.chunk_text(text, metadata)

    assert chunks[0]["metadata"]["source"] == "Test Book"
    assert chunks[0]["metadata"]["author"] == "Test Author"
    assert "chunk_id" in chunks[0]["metadata"]
    assert "chunk_count" in chunks[0]["metadata"]


# Note: Embedding and vector store tests require API keys and running services
# These should be run manually or in integration tests

@pytest.mark.skip(reason="Requires OpenAI API key")
def test_embedding_generation():
    """Test embedding generation (requires API key)"""
    from src.rag.embeddings import EmbeddingGenerator

    embedder = EmbeddingGenerator()
    embedding = embedder.generate("What is FTP?")

    assert len(embedding) == 1536  # text-embedding-3-small dimension
    assert all(isinstance(x, float) for x in embedding)


@pytest.mark.skip(reason="Requires Qdrant running")
def test_vector_store_search():
    """Test vector store search (requires Qdrant)"""
    from src.rag.vector_store import QdrantVectorStore

    store = QdrantVectorStore()
    # Test would require populated vector store
    pass
