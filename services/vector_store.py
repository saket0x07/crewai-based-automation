import os
import re
import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional

import faiss
import numpy as np
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

from config import settings


class FAISSVectorStoreManager:
    """
    FAISS Vector Store Manager supporting section-aware chunking,
    dense vector indexing, metadata tagging, and document_id filtering.
    """
    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = Path(storage_dir or settings.FAISS_STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "faiss_index.bin"
        self.metadata_file = self.storage_dir / "documents_metadata.pkl"
        
        # Initialize embeddings model with fallback for testing/offline environments
        api_key = settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY
        if api_key and not api_key.startswith("mock"):
            self.embeddings = OpenAIEmbeddings(
                model=settings.EMBEDDING_MODEL,
                openai_api_key=api_key,
                openai_api_base=settings.OPENROUTER_BASE_URL if settings.OPENROUTER_API_KEY else None
            )
        else:
            from langchain_community.embeddings import FakeEmbeddings
            print("[FAISS] API key not detected or mock key used. Using FakeEmbeddings for vector indexing.")
            self.embeddings = FakeEmbeddings(size=1536)
        
        self.vector_store: Optional[FAISS] = None
        self._load_or_create_store()

    def _load_or_create_store(self):
        """Loads existing FAISS index from disk or creates a new empty index."""
        if (self.storage_dir / "index.faiss").exists() and (self.storage_dir / "index.pkl").exists():
            try:
                self.vector_store = FAISS.load_local(
                    folder_path=str(self.storage_dir),
                    embeddings=self.embeddings,
                    allow_dangerous_deserialization=True
                )
                print(f"[FAISS] Loaded existing index from {self.storage_dir}")
                return
            except Exception as e:
                print(f"[FAISS] Error loading existing index: {e}. Re-initializing.")
                
        # Initialize fresh FAISS vector store
        dummy_doc = Document(page_content="System Initialized", metadata={"document_id": "system"})
        self.vector_store = FAISS.from_documents([dummy_doc], self.embeddings)
        self.save_store()

    def save_store(self):
        """Persists the FAISS index and docstore metadata to disk."""
        if self.vector_store:
            self.vector_store.save_local(folder_path=str(self.storage_dir))
            print(f"[FAISS] Persisted index to {self.storage_dir}")

    def chunk_text_by_sections(self, raw_text: str, document_id: str) -> List[Document]:
        """
        Performs section-aware semantic chunking on resume text.
        Identifies key headers (Work Experience, Skills, Projects, Education)
        and constructs metadata-enriched Document chunks.
        """
        section_patterns = re.compile(
            r'^(WORK EXPERIENCE|EXPERIENCE|EMPLOYMENT HISTORY|PROJECTS|TECHNICAL SKILLS|SKILLS|EDUCATION|CERTIFICATIONS|SUMMARY|OBJECTIVE)',
            re.MULTILINE | re.IGNORECASE
        )
        
        lines = raw_text.splitlines()
        chunks: List[Document] = []
        current_section = "GENERAL"
        current_lines: List[str] = []
        
        for line in lines:
            line_str = line.strip()
            match = section_patterns.match(line_str)
            if match and len(line_str) < 50:
                # Save previous section chunk if populated
                if current_lines:
                    chunk_content = "\n".join(current_lines).strip()
                    if len(chunk_content) > 20:
                        chunks.append(Document(
                            page_content=f"[{current_section}]\n{chunk_content}",
                            metadata={
                                "document_id": document_id,
                                "section": current_section,
                                "length": len(chunk_content)
                            }
                        ))
                    current_lines = []
                current_section = match.group(0).upper()
            else:
                if line_str:
                    current_lines.append(line_str)
                    
        # Flush last section
        if current_lines:
            chunk_content = "\n".join(current_lines).strip()
            if len(chunk_content) > 20:
                chunks.append(Document(
                    page_content=f"[{current_section}]\n{chunk_content}",
                    metadata={
                        "document_id": document_id,
                        "section": current_section,
                        "length": len(chunk_content)
                    }
                ))
                
        # If sectioning produced no chunks (unformatted resume), fallback to sliding window chunking
        if not chunks:
            chunk_size = 400
            overlap = 50
            words = raw_text.split()
            for i in range(0, len(words), chunk_size - overlap):
                chunk_words = words[i:i + chunk_size]
                chunk_str = " ".join(chunk_words)
                chunks.append(Document(
                    page_content=chunk_str,
                    metadata={"document_id": document_id, "section": "GENERAL", "length": len(chunk_str)}
                ))
                
        return chunks

    def add_resume_document(self, document_id: str, raw_text: str) -> int:
        """Chunks resume text, embeds, and indexes into FAISS store."""
        documents = self.chunk_text_by_sections(raw_text, document_id)
        if documents and self.vector_store:
            self.vector_store.add_documents(documents)
            self.save_store()
            return len(documents)
        return 0

    def search_by_document_id(self, query: str, document_id: str, k: int = 4) -> List[Document]:
        """Performs similarity search filtered strictly by document_id."""
        if not self.vector_store:
            return []
            
        # Perform similarity search with metadata filter
        results = self.vector_store.similarity_search(
            query=query,
            k=k * 3,  # Fetch wider set to filter post-retrieval if filter arg not natively applied
            filter={"document_id": document_id}
        )
        
        filtered = [doc for doc in results if doc.metadata.get("document_id") == document_id]
        return filtered[:k]
