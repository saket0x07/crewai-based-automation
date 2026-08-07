from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr

# --- Resume Pydantic Schemas ---

class PersonalInfo(BaseModel):
    name: Optional[str] = Field(default=None, description="Full Name of candidate")
    email: Optional[str] = Field(default=None, description="Email address")
    phone: Optional[str] = Field(default=None, description="Phone number")
    linkedin: Optional[str] = Field(default=None, description="LinkedIn URL")
    github: Optional[str] = Field(default=None, description="GitHub URL")
    portfolio: Optional[str] = Field(default=None, description="Portfolio/Personal Website URL")
    location: Optional[str] = Field(default=None, description="City, Country or Location")


class WorkExperience(BaseModel):
    job_title: str = Field(description="Designation or Role Title")
    company: str = Field(description="Company or Organization Name")
    location: Optional[str] = Field(default=None, description="Location of employment")
    start_date: Optional[str] = Field(default=None, description="Start date (Month Year or Year)")
    end_date: Optional[str] = Field(default=None, description="End date or Present")
    achievements: List[str] = Field(default_factory=list, description="Key responsibilities and achievements")
    tech_stack: List[str] = Field(default_factory=list, description="Technologies used in this role")


class Education(BaseModel):
    degree: str = Field(description="Degree title e.g. B.S., M.S., Ph.D.")
    field_of_study: Optional[str] = Field(default=None, description="Major or Field of study")
    institution: str = Field(description="University or College Name")
    graduation_year: Optional[str] = Field(default=None, description="Year of graduation")
    gpa: Optional[str] = Field(default=None, description="GPA if mentioned")


class Project(BaseModel):
    title: str = Field(description="Project title")
    description: str = Field(description="Project description and key functionality")
    technologies_used: List[str] = Field(default_factory=list, description="Tech stack utilized")
    link: Optional[str] = Field(default=None, description="GitHub repository or live demo URL")


class StructuredResumeSchema(BaseModel):
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    professional_summary: str = Field(default="", description="Executive candidate summary")
    work_experience: List[WorkExperience] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list, description="Categorized technical & soft skills")
    education: List[Education] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    total_years_of_experience: float = Field(default=0.0, description="Calculated overall years of experience")


class ResumeUploadResponse(BaseModel):
    document_id: str
    filename: str
    candidate_name: Optional[str] = None
    status: str
    created_at: datetime


# --- Chat Pydantic Schemas ---

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=2, description="Question about the candidate's resume")


class ChatResponse(BaseModel):
    document_id: str
    query: str
    answer: str
    sources: List[str] = Field(default_factory=list)


# --- Mock Interview Pydantic Schemas ---

class InterviewStartRequest(BaseModel):
    document_id: str = Field(..., description="Target document_id of ingested resume")
    num_questions: int = Field(default=5, ge=3, le=10, description="Number of questions to generate (3 to 10)")
    target_role: Optional[str] = Field(default=None, description="Target Job Title e.g. Senior Backend Engineer / AI Engineer")
    job_description: Optional[str] = Field(default=None, description="Optional Job Description text to align question focus")


class InterviewStartResponse(BaseModel):
    interview_id: str
    document_id: str
    total_questions: int
    status: str


class QuestionResponse(BaseModel):
    interview_id: str
    question_number: int
    total_questions: int
    question_text: str
    question_category: str
    is_completed: bool = False


class SubmitAnswerRequest(BaseModel):
    response_text: Optional[str] = Field(default=None, description="Candidate's answer text")
    proceed: bool = Field(default=True, description="True to move to next question")


class EvaluationReportResponse(BaseModel):
    evaluation_id: str
    interview_id: str
    document_id: str
    overall_score: float
    strengths: List[str]
    weaknesses: List[str]
    areas_of_improvement: List[str]
    detailed_report: str
    created_at: datetime
