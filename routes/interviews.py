import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session


from database import get_db
from models import ResumeModel, ParsedResumeModel, MockInterviewModel, InterviewQALogModel, InterviewEvaluationModel
from schemas import (
    InterviewStartRequest, InterviewStartResponse,
    QuestionResponse, SubmitAnswerRequest, EvaluationReportResponse,
    TranscriptionResponse, VoiceAnswerResponse
)
from agents.crew_manager import generate_interview_questions, evaluate_interview_performance
from services.audio_transcriber import transcribe_audio_file

router = APIRouter(prefix="/api/v1/interview", tags=["Mock Interview"])


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_standalone_audio(file: UploadFile = File(...)):
    """
    Standalone Speech-to-Text transcription endpoint.
    Accepts browser recorded audio blobs (.webm, .wav, .mp3, .m4a, .ogg).
    Returns real-time transcription text without modifying interview state.
    """
    file_bytes = await file.read()
    filename = file.filename or "recording.webm"
    result = transcribe_audio_file(file_bytes, filename)
    return TranscriptionResponse(
        filename=filename,
        transcript=result.get("transcript", ""),
        language=result.get("language", "en"),
        duration_seconds=result.get("duration_seconds", 0.0)
    )


@router.post("/start", response_model=InterviewStartResponse, status_code=status.HTTP_201_CREATED)
def start_mock_interview(
    payload: InterviewStartRequest,
    db: Session = Depends(get_db)
):
    """
    Initializes a new mock interview session based on candidate document_id:
    1. Fetches candidate's extracted profile.
    2. Generates 5 to 10 customized interview questions via CrewAI.
    3. Saves interview session & question logs to SQLite.
    """
    parsed_record = db.query(ParsedResumeModel).filter(ParsedResumeModel.document_id == payload.document_id).first()
    if not parsed_record:
        raise HTTPException(status_code=404, detail=f"No candidate profile found for document_id: {payload.document_id}")

    structured_json = parsed_record.structured_json
    num_questions = min(max(payload.num_questions, 1), 10)

    
    diff_level = payload.difficulty_level or "Mid"
    foc_area = payload.focus_area or "Full Mix"

    # Generate dynamic questions via CrewAI LLM
    questions_data = generate_interview_questions(
        structured_resume=structured_json,
        num_questions=num_questions,
        target_role=payload.target_role,
        job_description=payload.job_description,
        difficulty_level=diff_level,
        focus_area=foc_area
    )
    
    interview_id = str(uuid.uuid4())
    mock_interview = MockInterviewModel(
        interview_id=interview_id,
        document_id=payload.document_id,
        total_questions=len(questions_data),
        current_index=0,
        difficulty_level=diff_level,
        focus_area=foc_area,
        status="IN_PROGRESS",
        created_at=datetime.utcnow()
    )
    db.add(mock_interview)
    db.commit()

    # Save questions to InterviewQALogModel
    for idx, q in enumerate(questions_data):
        qa_log = InterviewQALogModel(
            qa_id=str(uuid.uuid4()),
            interview_id=interview_id,
            question_number=idx + 1,
            question_text=q.get("question_text", "Describe your experience."),
            question_category=q.get("category", "Technical"),
            skipped=False
        )
        db.add(qa_log)
    db.commit()

    return InterviewStartResponse(
        interview_id=interview_id,
        document_id=payload.document_id,
        total_questions=len(questions_data),
        difficulty_level=diff_level,
        focus_area=foc_area,
        status="STARTED"
    )


@router.get("/{interview_id}/next", response_model=QuestionResponse)
def get_next_question(interview_id: str, db: Session = Depends(get_db)):
    """Serves questions sequentially, one after another."""
    mock_interview = db.query(MockInterviewModel).filter(MockInterviewModel.interview_id == interview_id).first()
    if not mock_interview:
        raise HTTPException(status_code=404, detail=f"Interview session {interview_id} not found.")

    if mock_interview.current_index >= mock_interview.total_questions:
        return QuestionResponse(
            interview_id=interview_id,
            question_number=mock_interview.total_questions,
            total_questions=mock_interview.total_questions,
            question_text="Interview completed! Call /finalize to view evaluation report.",
            question_category="Completed",
            is_completed=True
        )

    current_qa = db.query(InterviewQALogModel).filter(
        InterviewQALogModel.interview_id == interview_id,
        InterviewQALogModel.question_number == mock_interview.current_index + 1
    ).first()

    if not current_qa:
        raise HTTPException(status_code=500, detail="Error fetching current question state.")

    return QuestionResponse(
        interview_id=interview_id,
        question_number=current_qa.question_number,
        total_questions=mock_interview.total_questions,
        question_text=current_qa.question_text,
        question_category=current_qa.question_category or "Technical",
        is_completed=False
    )


@router.post("/{interview_id}/answer")
def submit_answer_and_proceed(
    interview_id: str,
    payload: SubmitAnswerRequest = SubmitAnswerRequest(),
    db: Session = Depends(get_db)
):
    """Records user answer or proceed choice for the current question and advances interview state."""
    mock_interview = db.query(MockInterviewModel).filter(MockInterviewModel.interview_id == interview_id).first()
    if not mock_interview:
        raise HTTPException(status_code=404, detail=f"Interview session {interview_id} not found.")

    if mock_interview.current_index >= mock_interview.total_questions:
        return {"status": "COMPLETED", "message": "Interview already finished."}

    current_qa = db.query(InterviewQALogModel).filter(
        InterviewQALogModel.interview_id == interview_id,
        InterviewQALogModel.question_number == mock_interview.current_index + 1
    ).first()

    if current_qa:
        current_qa.user_response = payload.response_text
        current_qa.skipped = not payload.proceed or not (payload.response_text and payload.response_text.strip())

    # Advance step index
    mock_interview.current_index += 1
    db.commit()

    has_next = mock_interview.current_index < mock_interview.total_questions
    return {
        "status": "RECORDED",
        "question_number": mock_interview.current_index,
        "has_next": has_next,
        "next_question_number": mock_interview.current_index + 1 if has_next else None
    }


@router.post("/{interview_id}/answer/voice", response_model=VoiceAnswerResponse)
async def submit_voice_answer_and_proceed(
    interview_id: str,
    file: UploadFile = File(...),
    live_transcript: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Submits in-browser recorded audio blob for current interview question:
    1. Transcribes audio in real-time via OpenAI Whisper or live browser speech recognition.
    2. Saves transcribed response text into SQLite.
    3. Advances question state machine.
    4. Returns real-time transcript JSON to browser UI.
    """
    mock_interview = db.query(MockInterviewModel).filter(MockInterviewModel.interview_id == interview_id).first()
    if not mock_interview:
        raise HTTPException(status_code=404, detail=f"Interview session {interview_id} not found.")

    if mock_interview.current_index >= mock_interview.total_questions:
        raise HTTPException(status_code=400, detail="Interview is already completed.")

    file_bytes = await file.read()
    filename = file.filename or "recording.webm"
    transcribe_result = transcribe_audio_file(file_bytes, filename, live_transcript=live_transcript)
    transcript_text = transcribe_result.get("transcript", "").strip()


    current_qa = db.query(InterviewQALogModel).filter(
        InterviewQALogModel.interview_id == interview_id,
        InterviewQALogModel.question_number == mock_interview.current_index + 1
    ).first()

    if current_qa:
        current_qa.user_response = transcript_text
        current_qa.skipped = not transcript_text

    question_num = mock_interview.current_index + 1
    mock_interview.current_index += 1
    db.commit()

    has_next = mock_interview.current_index < mock_interview.total_questions
    return VoiceAnswerResponse(
        status="RECORDED",
        interview_id=interview_id,
        question_number=question_num,
        transcript=transcript_text,
        has_next=has_next,
        next_question_number=mock_interview.current_index + 1 if has_next else None
    )



@router.post("/{interview_id}/finalize", response_model=EvaluationReportResponse)
def finalize_interview_and_evaluate(interview_id: str, db: Session = Depends(get_db)):
    """
    Evaluates candidate responses:
    1. Collects all Q&A responses from SQLite logs.
    2. Executes CrewAI InterviewEvaluatorAgent to compute score, strengths, weaknesses, and study recommendations.
    3. Persists complete evaluation in SQLite linked to document_id.
    """
    mock_interview = db.query(MockInterviewModel).filter(MockInterviewModel.interview_id == interview_id).first()
    if not mock_interview:
        raise HTTPException(status_code=404, detail=f"Interview session {interview_id} not found.")

    parsed_record = db.query(ParsedResumeModel).filter(ParsedResumeModel.document_id == mock_interview.document_id).first()
    candidate_profile = parsed_record.structured_json if parsed_record else {}

    qa_logs = db.query(InterviewQALogModel).filter(InterviewQALogModel.interview_id == interview_id).all()
    qa_transcript = [
        {
            "question_number": log.question_number,
            "category": log.question_category,
            "question_text": log.question_text,
            "user_response": log.user_response or "Skipped / No Answer",
            "skipped": log.skipped
        }
        for log in qa_logs
    ]

    # Evaluate via CrewAI Agent
    eval_report = evaluate_interview_performance(qa_transcript, candidate_profile)
    
    evaluation_id = str(uuid.uuid4())
    eval_record = InterviewEvaluationModel(
        evaluation_id=evaluation_id,
        interview_id=interview_id,
        document_id=mock_interview.document_id,
        overall_score=float(eval_report.get("overall_score", 70.0)),
        strengths=eval_report.get("strengths", []),
        weaknesses=eval_report.get("weaknesses", []),
        areas_of_improvement=eval_report.get("areas_of_improvement", []),
        detailed_report=eval_report.get("detailed_report", "Evaluation report."),
        created_at=datetime.utcnow()
    )
    db.add(eval_record)
    mock_interview.status = "COMPLETED"
    db.commit()

    return EvaluationReportResponse(
        evaluation_id=evaluation_id,
        interview_id=interview_id,
        document_id=mock_interview.document_id,
        overall_score=eval_record.overall_score,
        strengths=eval_record.strengths,
        weaknesses=eval_record.weaknesses,
        areas_of_improvement=eval_record.areas_of_improvement,
        detailed_report=eval_record.detailed_report,
        qa_transcript=qa_transcript,
        created_at=eval_record.created_at
    )


@router.get("/{interview_id}/report", response_model=EvaluationReportResponse)
def get_interview_report(interview_id: str, db: Session = Depends(get_db)):
    """Retrieves stored mock interview evaluation report from SQLite."""
    eval_record = db.query(InterviewEvaluationModel).filter(InterviewEvaluationModel.interview_id == interview_id).first()
    if not eval_record:
        raise HTTPException(status_code=404, detail=f"No evaluation report found for interview_id: {interview_id}")

    qa_logs = db.query(InterviewQALogModel).filter(InterviewQALogModel.interview_id == interview_id).all()
    qa_transcript = [
        {
            "question_number": log.question_number,
            "category": log.question_category,
            "question_text": log.question_text,
            "user_response": log.user_response or "Skipped / No Answer",
            "skipped": log.skipped
        }
        for log in qa_logs
    ]

    return EvaluationReportResponse(
        evaluation_id=eval_record.evaluation_id,
        interview_id=eval_record.interview_id,
        document_id=eval_record.document_id,
        overall_score=eval_record.overall_score,
        strengths=eval_record.strengths,
        weaknesses=eval_record.weaknesses,
        areas_of_improvement=eval_record.areas_of_improvement,
        detailed_report=eval_record.detailed_report,
        qa_transcript=qa_transcript,
        created_at=eval_record.created_at
    )

