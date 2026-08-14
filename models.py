import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base

class ResumeModel(Base):
    __tablename__ = "resumes"

    document_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    raw_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    parsed_profile = relationship("ParsedResumeModel", back_populates="resume", uselist=False, cascade="all, delete-orphan")
    interviews = relationship("MockInterviewModel", back_populates="resume", cascade="all, delete-orphan")


class ParsedResumeModel(Base):
    __tablename__ = "parsed_resumes"

    parsed_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("resumes.document_id", ondelete="CASCADE"), unique=True, nullable=False)
    candidate_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    structured_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    resume = relationship("ResumeModel", back_populates="parsed_profile")


class MockInterviewModel(Base):
    __tablename__ = "mock_interviews"

    interview_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("resumes.document_id", ondelete="CASCADE"), nullable=False)
    total_questions = Column(Integer, nullable=False, default=5)
    current_index = Column(Integer, nullable=False, default=0)
    difficulty_level = Column(String(50), nullable=True, default="Mid")
    focus_area = Column(String(100), nullable=True, default="Full Mix")
    status = Column(String(50), nullable=False, default="IN_PROGRESS")  # IN_PROGRESS, COMPLETED, ABORTED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    resume = relationship("ResumeModel", back_populates="interviews")
    qa_logs = relationship("InterviewQALogModel", back_populates="interview", cascade="all, delete-orphan", order_by="InterviewQALogModel.question_number")
    evaluation = relationship("InterviewEvaluationModel", back_populates="interview", uselist=False, cascade="all, delete-orphan")


class InterviewQALogModel(Base):
    __tablename__ = "interview_qa_logs"

    qa_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id = Column(String(36), ForeignKey("mock_interviews.interview_id", ondelete="CASCADE"), nullable=False)
    question_number = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    question_category = Column(String(100), nullable=True, default="Technical")
    user_response = Column(Text, nullable=True)
    skipped = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    interview = relationship("MockInterviewModel", back_populates="qa_logs")


class InterviewEvaluationModel(Base):
    __tablename__ = "interview_evaluations"

    evaluation_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id = Column(String(36), ForeignKey("mock_interviews.interview_id", ondelete="CASCADE"), unique=True, nullable=False)
    document_id = Column(String(36), ForeignKey("resumes.document_id", ondelete="CASCADE"), nullable=False)
    overall_score = Column(Float, nullable=False)
    strengths = Column(JSON, nullable=False)
    weaknesses = Column(JSON, nullable=False)
    areas_of_improvement = Column(JSON, nullable=False)
    detailed_report = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    interview = relationship("MockInterviewModel", back_populates="evaluation")
