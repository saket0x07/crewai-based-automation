import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models import ResumeModel, ParsedResumeModel
from schemas import ResumeUploadResponse, StructuredResumeSchema, ChatRequest, ChatResponse
from services.extractor import extract_text_from_file
from services.vector_store import FAISSVectorStoreManager
from agents.crew_manager import extract_structured_resume, chat_with_resume

router = APIRouter(prefix="/api/v1/resumes", tags=["Resumes"])
vector_manager = FAISSVectorStoreManager()


@router.get("", response_model=list[dict])
@router.get("/", response_model=list[dict])
def list_parsed_resumes(db: Session = Depends(get_db)):

    """Lists all stored candidate resumes from SQLite for dropdown selection in UI and CLI."""
    parsed_records = db.query(ParsedResumeModel).order_by(ParsedResumeModel.created_at.desc()).all()
    results = []
    for r in parsed_records:
        resume_meta = db.query(ResumeModel).filter(ResumeModel.document_id == r.document_id).first()
        filename = resume_meta.filename if resume_meta else "Uploaded Resume"
        results.append({
            "document_id": r.document_id,
            "candidate_name": r.candidate_name or "Candidate",
            "email": r.email or "N/A",
            "filename": filename,
            "created_at": r.created_at.isoformat() if r.created_at else None
        })
    return results



@router.post("/upload", response_model=ResumeUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_and_ingest_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Ingests PDF/DOCX resume file:
    1. Extracts text content.
    2. Executes CrewAI ResumeExtractorAgent for structured JSON parsing.
    3. Persists document record & structured profile in SQLite.
    4. Indexes section-aware semantic chunks into FAISS vector database.
    """
    filename = file.filename or "uploaded_resume.pdf"
    file_bytes = await file.read()
    
    # Extract text from file
    try:
        raw_text = extract_text_from_file(filename, file_bytes)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract text from file: {str(e)}")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Extracted text is empty. File may be corrupted or image-only.")

    document_id = str(uuid.uuid4())
    file_path = f"./data/uploads/{document_id}_{filename}"
    
    # Save file to disk
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # 1. Save Resume Model to SQLite
    resume_record = ResumeModel(
        document_id=document_id,
        filename=filename,
        file_path=file_path,
        raw_text=raw_text,
        created_at=datetime.utcnow()
    )
    db.add(resume_record)
    db.commit()

    # 2. Extract Structured Schema via CrewAI
    structured_data: StructuredResumeSchema = extract_structured_resume(raw_text)
    candidate_name = structured_data.personal_info.name if structured_data.personal_info else "Candidate"
    
    parsed_record = ParsedResumeModel(
        parsed_id=str(uuid.uuid4()),
        document_id=document_id,
        candidate_name=candidate_name,
        email=structured_data.personal_info.email if structured_data.personal_info else None,
        phone=structured_data.personal_info.phone if structured_data.personal_info else None,
        structured_json=structured_data.model_dump(),
        created_at=datetime.utcnow()
    )
    db.add(parsed_record)
    db.commit()

    # 3. Index into FAISS Vector DB
    vector_manager.add_resume_document(document_id, raw_text)

    return ResumeUploadResponse(
        document_id=document_id,
        filename=filename,
        candidate_name=candidate_name,
        status="PARSED_AND_INDEXED",
        created_at=resume_record.created_at
    )


@router.get("/{document_id}", response_model=StructuredResumeSchema)
def get_parsed_resume(document_id: str, db: Session = Depends(get_db)):
    """Retrieves structured candidate profile JSON for a document_id."""
    parsed_record = db.query(ParsedResumeModel).filter(ParsedResumeModel.document_id == document_id).first()
    if not parsed_record:
        raise HTTPException(status_code=404, detail=f"No parsed resume profile found for document_id: {document_id}")
    return StructuredResumeSchema(**parsed_record.structured_json)


@router.post("/{document_id}/chat", response_model=ChatResponse)
def chat_with_candidate_resume(
    document_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db)
):
    """Executes CrewAI ResumeChatAgent using FAISS context retrieval for a specific candidate document_id."""
    resume_record = db.query(ResumeModel).filter(ResumeModel.document_id == document_id).first()
    if not resume_record:
        raise HTTPException(status_code=404, detail=f"Document ID {document_id} not found.")

    result = chat_with_resume(payload.query, document_id, vector_manager)
    
    return ChatResponse(
        document_id=document_id,
        query=payload.query,
        answer=result["answer"],
        sources=result["sources"]
    )
