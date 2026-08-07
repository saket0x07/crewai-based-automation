import io
import pytest
from fastapi.testclient import TestClient
from main import app
from database import Base, engine

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "active"

def test_resume_upload_and_mock_interview_flow():
    sample_resume_content = """
    ALICE SMITH
    Senior Data Engineer | alice.smith@example.com | +1-555-9876 | New York, NY
    https://linkedin.com/in/alicesmith | https://github.com/alicesmith

    SUMMARY
    Senior Data Engineer with 6 years of experience building scalable data pipelines using Apache Spark, Python, FastAPI, and PostgreSQL.

    WORK EXPERIENCE
    Lead Data Engineer | DataCloud Inc | 2021 - Present
    - Architected real-time streaming pipelines using PySpark and Kafka processing 2TB/day.
    - Designed relational databases and SQLite embedded analytics engines.
    - Built REST APIs in FastAPI for data querying.

    TECHNICAL SKILLS
    Languages: Python, SQL, Scala
    Frameworks: PySpark, FastAPI, Airflow, SQLAlchemy, PyTest
    Databases: PostgreSQL, SQLite, FAISS, Redis

    EDUCATION
    M.S. in Data Science | Columbia University | 2020

    PROJECTS
    Realtime Stream Processor: Open-source Spark streaming engine for log analysis.
    """
    
    # 1. Upload Resume
    file_bytes = sample_resume_content.encode("utf-8")
    files = {"file": ("alice_smith_resume.txt", io.BytesIO(file_bytes), "text/plain")}
    
    upload_res = client.post("/api/v1/resumes/upload", files=files)
    assert upload_res.status_code == 201
    upload_data = upload_res.json()
    assert "document_id" in upload_data
    doc_id = upload_data["document_id"]
    assert upload_data["status"] == "PARSED_AND_INDEXED"

    # 2. Get Parsed Profile
    profile_res = client.get(f"/api/v1/resumes/{doc_id}")
    assert profile_res.status_code == 200
    profile_data = profile_res.json()
    assert "personal_info" in profile_data
    assert "skills" in profile_data

    # 3. Start Mock Interview
    start_payload = {"document_id": doc_id, "num_questions": 3}
    start_res = client.post("/api/v1/interview/start", json=start_payload)
    assert start_res.status_code == 201
    start_data = start_res.json()
    interview_id = start_data["interview_id"]
    assert start_data["total_questions"] == 3
    assert start_data["status"] == "STARTED"

    # 4. Get Question 1
    q1_res = client.get(f"/api/v1/interview/{interview_id}/next")
    assert q1_res.status_code == 200
    q1_data = q1_res.json()
    assert q1_data["question_number"] == 1
    assert not q1_data["is_completed"]

    # 5. Answer Question 1
    ans1_payload = {
        "response_text": "I used PySpark and Kafka to build distributed pipelines handling micro-batches with minimal latency.",
        "proceed": True
    }
    ans1_res = client.post(f"/api/v1/interview/{interview_id}/answer", json=ans1_payload)
    assert ans1_res.status_code == 200
    assert ans1_res.json()["status"] == "RECORDED"

    # 6. Get Question 2
    q2_res = client.get(f"/api/v1/interview/{interview_id}/next")
    assert q2_res.status_code == 200
    assert q2_res.json()["question_number"] == 2

    # 7. Answer Question 2
    ans2_payload = {
        "response_text": "FastAPI async endpoints allowed non-blocking I/O queries to database pools.",
        "proceed": True
    }
    client.post(f"/api/v1/interview/{interview_id}/answer", json=ans2_payload)

    # 8. Get Question 3
    q3_res = client.get(f"/api/v1/interview/{interview_id}/next")
    assert q3_res.status_code == 200

    # 9. Skip Question 3
    ans3_payload = {"response_text": "", "proceed": False}
    client.post(f"/api/v1/interview/{interview_id}/answer", json=ans3_payload)

    # 10. Verify Completed State
    q_end_res = client.get(f"/api/v1/interview/{interview_id}/next")
    assert q_end_res.status_code == 200
    assert q_end_res.json()["is_completed"]

    # 11. Finalize Interview & Evaluate
    eval_res = client.post(f"/api/v1/interview/{interview_id}/finalize")
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert "overall_score" in eval_data
    assert "strengths" in eval_data
    assert "weaknesses" in eval_data
    assert "areas_of_improvement" in eval_data

    # 12. Retrieve Saved Report from SQLite
    report_res = client.get(f"/api/v1/interview/{interview_id}/report")
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert report_data["evaluation_id"] == eval_data["evaluation_id"]
    assert report_data["overall_score"] == eval_data["overall_score"]
    print("\nEnd-to-End Test Completed Successfully!")
