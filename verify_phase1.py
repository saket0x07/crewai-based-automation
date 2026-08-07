from database import init_db, engine
from models import ResumeModel, ParsedResumeModel, MockInterviewModel, InterviewQALogModel, InterviewEvaluationModel
from config import settings
import sqlalchemy

print(f"Checking Settings...")
print(f"App Name: {settings.APP_NAME}")
print(f"OpenRouter Model: {settings.OPENROUTER_MODEL}")
print(f"Database URL: {settings.DATABASE_URL}")

print("Initializing database tables...")
init_db()

inspector = sqlalchemy.inspect(engine)
tables = inspector.get_table_names()
print(f"Created tables: {tables}")

assert "resumes" in tables
assert "parsed_resumes" in tables
assert "mock_interviews" in tables
assert "interview_qa_logs" in tables
assert "interview_evaluations" in tables

print("Phase 1 verification successful!")
