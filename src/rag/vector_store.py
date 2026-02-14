"""
Qdrant vector store for knowledge base
"""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from config import settings
from typing import List, Dict, Any
import uuid


class QdrantVectorStore:
    """Manage vector storage in Qdrant"""

    def __init__(self):
        self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        self.collection_name = settings.qdrant_collection_name

    def create_collection(self, vector_size: int = 1536):
        """
        Create collection for cycling knowledge base

        Args:
            vector_size: Dimension of vectors (1536 for text-embedding-3-small)
        """
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            print(f"OK: Collection '{self.collection_name}' created")
        except Exception as e:
            print(f"Collection may already exist: {e}")

    def upsert_documents(self, documents: List[Dict[str, Any]], embeddings: List[List[float]]):
        """
        Insert documents with embeddings into Qdrant

        Args:
            documents: List of document dicts with 'text' and 'metadata'
            embeddings: Corresponding embeddings for each document
        """
        points = []
        for doc, embedding in zip(documents, embeddings):
            points.append(
                PointStruct(id=str(uuid.uuid4()), vector=embedding, payload=doc)
            )

        self.client.upsert(collection_name=self.collection_name, points=points)
        print(f"OK: Upserted {len(points)} documents")

    def search(self, query_embedding: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar documents

        Args:
            query_embedding: Query vector
            limit: Number of results to return

        Returns:
            List of results with text, metadata, and similarity score
        """
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=limit,
        )

        return [
            {
                "text": hit.payload.get("text", ""),
                "metadata": hit.payload.get("metadata", {}),
                "score": hit.score,
            }
            for hit in results
        ]
