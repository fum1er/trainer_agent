"""
Document processing for RAG: PDF parsing and chunking
"""
from pypdf import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List, Dict, Any
from pathlib import Path


class DocumentProcessor:
    """Process PDF documents and chunk text for embedding"""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        """
        Initialize document processor

        Args:
            chunk_size: Target size of each chunk in characters
            chunk_overlap: Overlap between consecutive chunks
        """
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n## ", "\n### ", "\n\n", ".\n", ". ", " ", ""],
        )

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extract text from PDF file

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text
        """
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text

    def chunk_text(self, text: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Split text into chunks with metadata

        Args:
            text: Text to split
            metadata: Optional metadata to attach to each chunk

        Returns:
            List of document dicts with text and metadata
        """
        chunks = self.text_splitter.split_text(text)

        documents = []
        for i, chunk in enumerate(chunks):
            doc = {
                "text": chunk,
                "metadata": {
                    **(metadata or {}),
                    "chunk_id": i,
                    "chunk_count": len(chunks),
                },
            }
            documents.append(doc)

        return documents

    def process_book(self, pdf_path: str, book_name: str, author: str) -> List[Dict[str, Any]]:
        """
        Process a complete book: extract text and chunk

        Args:
            pdf_path: Path to PDF file
            book_name: Name of the book
            author: Author name

        Returns:
            List of chunked documents with metadata
        """
        print(f"Processing book: {book_name}")

        # Extract text
        text = self.extract_text_from_pdf(pdf_path)

        # Create metadata
        metadata = {"source": book_name, "author": author, "type": "training_book"}

        # Chunk text
        documents = self.chunk_text(text, metadata)

        print(f"Created {len(documents)} chunks from {book_name}")
        return documents
