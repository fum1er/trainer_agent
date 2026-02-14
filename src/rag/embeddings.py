"""
OpenAI embedding generation for RAG pipeline
"""
from openai import OpenAI
from config import settings
from typing import List


class EmbeddingGenerator:
    """Generate embeddings using OpenAI's API"""

    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_embedding_model

    def generate(self, text: str) -> List[float]:
        """
        Generate embedding for a single text

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding
        """
        response = self.client.embeddings.create(model=self.model, input=text)
        return response.data[0].embedding

    def generate_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches

        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process in each batch (default: 100)

        Returns:
            List of embeddings
        """
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self.client.embeddings.create(model=self.model, input=batch)
            embeddings.extend([data.embedding for data in response.data])
            print(f"Processed {i + len(batch)}/{len(texts)} texts")

        return embeddings
