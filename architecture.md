# Architecture & Technical Specification: Agentic Hiring & Mock Interview System

## 1. High-Level Architecture Overview

The **Agentic Hiring & Mock Interview System** is an end-to-end AI platform built with **FastAPI**, **CrewAI**, **FAISS**, and **SQLite**, configured to operate seamlessly with **OpenRouter** LLMs.

The platform provides two primary intelligent workflows:
1. **Resume Ingestion & RAG Chat**: Ingesting PDF/DOCX resumes, parsing them into structured Pydantic schemas using CrewAI, indexing section-aware vector chunks into FAISS, and enabling context-aware Q&A via a dedicated CrewAI RAG agent.
2. **Dynamic Mock Interview & Performance Evaluation**: Generating 5–10 customized technical and behavioral interview questions based on the candidate's resume and target job role/description, serving questions sequentially, logging candidate answers, and generating comprehensive scorecard evaluations stored in SQLite.

---

## 2. Executed Features Architecture

```
[ User / REST API Client ]
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI API Layer                           │
│  ├── /api/v1/resumes/upload                                     │
│  ├── /api/v1/resumes/{document_id}/chat                        │
│  ├── /api/v1/interview/start                                   │
│  ├── /api/v1/interview/{interview_id}/next                     │
│  ├── /api/v1/interview/{interview_id}/answer                   │
│  └── /api/v1/interview/{interview_id}/finalize                 │
└────────────────────────────────┬────────────────────────────────┘
                                 │
         ┌───────────────────────┴───────────────────────┐
         │                                               │
         ▼                                               ▼
┌────────────────────────────────┐               ┌────────────────────────────────┐
│      SQLite Database           │               │       FAISS Vector Store       │
│  ├── resumes                   │               │  ├── Section-Aware Chunks      │
│  ├── parsed_resumes            │               │  ├── Dense Vector Embeddings   │
│  ├── mock_interviews           │               │  └── document_id Tag Filter    │
│  ├── interview_qa_logs         │               └────────────────┬───────────────┘
│  └── interview_evaluations     │                                │
└────────────────────────────────┘                                │
                                                                  │
                 ┌────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│             CrewAI Multi-Agent System (OpenRouter)              │
│  ├── ResumeExtractorAgent (Structured Pydantic Output)          │
│  ├── ResumeChatAgent (FAISS Search Tool Integration)            │
│  ├── InterviewGeneratorAgent (Dynamic Resume + Role Prompting)  │
│  └── InterviewEvaluatorAgent (Scoring, Strengths & Gaps)        │
└─────────────────────────────────────────────────────────────────┘
```

---

### Component Deep-Dive

#### 1. Multi-Stage Ingestion & Dual Storage
- **File Parsing & Normalization** (`services/extractor.py`): Parses `.pdf` and `.docx` files using `pdfplumber` and `python-docx`, maintaining header hierarchies while cleaning layout noise.
- **Agentic Structured Parsing** (`agents/crew_manager.py`): `ResumeExtractorAgent` transforms raw text into a strict `StructuredResumeSchema` (Personal Info, Summary, Work History, Skills, Projects, Education, Certifications).
- **SQLite Relational Persistence** (`models.py`, `database.py`): Stores raw document records in `resumes` and structured candidate JSON profiles in `parsed_resumes`.
- **Section-Aware FAISS Vector Indexing** (`services/vector_store.py`): Partitions resumes into semantic section chunks (`[WORK EXPERIENCE]`, `[PROJECTS]`, `[SKILLS]`, `[EDUCATION]`) and embeds them into a persistent FAISS vector store tagged with `document_id`.

#### 2. Context-Aware "Chat with Resume" RAG Agent
- **CrewAI RAG Agent** (`ResumeChatAgent`): Equipped with custom `@tool("search_candidate_resume")`.
- **Strict Document Isolation**: Queries FAISS vectors using metadata filters restricted to the specific `document_id`.
- **Grounded Answer Generation**: Formulates grounded answers and career feedback backed by resume evidence.

#### 3. Dynamic Mock Interview & Evaluation Engine
- **Dynamic Question Generator** (`InterviewGeneratorAgent`): Analyzes candidate skills and projects alongside optional `target_role` (e.g. *"Senior AI Architect"*) and `job_description` to synthesize 5 to 10 customized technical, behavioral, and project architecture questions.
- **Sequential State Machine**:
  - `POST /start`: Initializes session, generates questions, and logs them in `interview_qa_logs`.
  - `GET /next`: Serves current question sequentially (`is_completed`, `question_number`, `question_text`).
  - `POST /answer`: Records response text / proceed signal and advances session index.
- **AI Performance Evaluator** (`InterviewEvaluatorAgent`): Evaluates full candidate transcript against original resume claims; computes overall score (0–100), key strengths, weaknesses, and actionable study recommendations (**"Areas to Work More On"**), persisted in SQLite `interview_evaluations`.

---

## 3. Database Schema Overview (SQLite)

```sql
-- Resumes Metadata
CREATE TABLE resumes (
    document_id VARCHAR(36) PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    raw_text TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Parsed Structured Profiles
CREATE TABLE parsed_resumes (
    parsed_id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) UNIQUE NOT NULL,
    candidate_name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    structured_json JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES resumes(document_id) ON DELETE CASCADE
);

-- Mock Interview Sessions
CREATE TABLE mock_interviews (
    interview_id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) NOT NULL,
    total_questions INTEGER NOT NULL,
    current_index INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'IN_PROGRESS',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES resumes(document_id) ON DELETE CASCADE
);

-- Q&A Transcript Logs
CREATE TABLE interview_qa_logs (
    qa_id VARCHAR(36) PRIMARY KEY,
    interview_id VARCHAR(36) NOT NULL,
    question_number INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    question_category VARCHAR(100),
    user_response TEXT,
    skipped BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (interview_id) REFERENCES mock_interviews(interview_id) ON DELETE CASCADE
);

-- Scorecards & Evaluations
CREATE TABLE interview_evaluations (
    evaluation_id VARCHAR(36) PRIMARY KEY,
    interview_id VARCHAR(36) UNIQUE NOT NULL,
    document_id VARCHAR(36) NOT NULL,
    overall_score FLOAT NOT NULL,
    strengths JSON NOT NULL,
    weaknesses JSON NOT NULL,
    areas_of_improvement JSON NOT NULL,
    detailed_report TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (interview_id) REFERENCES mock_interviews(interview_id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES resumes(document_id) ON DELETE CASCADE
);
```

---

## 4. Pending Updates & Future Roadmap

The following updates remain for future development:

### 1. Interactive Web UI / Frontend Dashboard
- **Web Interface**: Build a frontend dashboard (React / Next.js / Streamlit) for resume drag-and-drop upload, interactive candidate profile viewing, live RAG chat interface, and step-by-step mock interview wizard.

### 2. Real-Time Audio / Voice Mock Interview
- **Speech-to-Text & Text-to-Speech**: Integrate OpenAI Whisper (STT) and ElevenLabs/TTS for real-time voice-driven mock interviews.

### 3. Historical Candidate Progress & Score Tracking
- **Multi-Session Analytics**: Analytics endpoints comparing candidate scores across multiple interview sessions over time to measure skill growth.

### 4. Enterprise Vector Database Adapters
- **Multi-Vector DB Support**: Add plug-and-play vector storage adapters for Pinecone, Qdrant, or Weaviate alongside FAISS.

### 5. Async Job Queue for Heavy Batch Ingestion
- **Celery / Redis Queue**: Offload high-volume PDF parsing and vector indexing to background worker processes.
