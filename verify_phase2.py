from services.extractor import clean_text, extract_text_from_file
from services.vector_store import FAISSVectorStoreManager
import os

print("--- Testing Text Extraction Utilities ---")
sample_resume_text = """
JOHN DOE
Software Engineer | john.doe@example.com | +1-555-0199 | San Francisco, CA
https://linkedin.com/in/johndoe | https://github.com/johndoe

SUMMARY
Experienced Software Engineer specializing in Python, FastAPI, Microservices, and Distributed Systems.

WORK EXPERIENCE
Senior Backend Engineer | TechCorp Inc | San Francisco, CA | 2021 - Present
- Designed and implemented asynchronous REST APIs using FastAPI and Pydantic v2.
- Optimized Database query performance on SQLite and PostgreSQL, reducing latency by 40%.
- Integrated FAISS vector database for semantic search across 500k candidate documents.

Software Developer | CodeLabs | Austin, TX | 2019 - 2021
- Developed REST microservices with Flask and Docker.
- Built automated test suites using pytest and CI/CD pipelines.

TECHNICAL SKILLS
Languages: Python, JavaScript, SQL
Frameworks & Libraries: FastAPI, CrewAI, PyTorch, LangChain, SQLAlchemy
Databases & Vector Stores: SQLite, PostgreSQL, FAISS, Redis
DevOps & Tools: Docker, Git, Linux, Kubernetes

EDUCATION
B.S. in Computer Science | University of Texas at Austin | 2019

PROJECTS
Agentic Hiring System: Autonomous CrewAI agents for resume parsing and candidate mock interviews.
"""

cleaned = clean_text(sample_resume_text)
assert "JOHN DOE" in cleaned
assert "TechCorp Inc" in cleaned
print("Text cleaning verification successful!")

print("\n--- Testing FAISS Vector Store Manager ---")
manager = FAISSVectorStoreManager(storage_dir="./data/test_faiss")
doc_id = "test-doc-12345"

# Test section-aware chunking
chunks = manager.chunk_text_by_sections(cleaned, document_id=doc_id)
print(f"Generated {len(chunks)} section chunks:")
for c in chunks:
    print(f" - [{c.metadata['section']}]: {c.page_content[:60]}...")

assert len(chunks) >= 3
assert any(c.metadata["section"] == "WORK EXPERIENCE" for c in chunks)
assert any(c.metadata["section"] == "TECHNICAL SKILLS" for c in chunks)

print("\nPhase 2 extraction & chunking verification successful!")
