import json
import re
import uuid
import asyncio
import concurrent.futures
from typing import List, Dict, Any, Optional

from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

from config import settings, get_openrouter_llm
from schemas import StructuredResumeSchema
from services.vector_store import FAISSVectorStoreManager


def run_crew_safely(crew: Crew):
    """Executes crew.kickoff safely whether inside or outside an active asyncio event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
        
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(crew.kickoff).result()
    else:
        return crew.kickoff()


def get_llm():
    """Returns CrewAI LLM instance configured for OpenRouter or OpenAI."""
    cfg = get_openrouter_llm()
    model_name = cfg["model"]
    if not model_name.startswith("openrouter/") and "openrouter" in cfg["base_url"]:
        model_name = f"openrouter/{model_name}"
        
    return LLM(
        model=model_name,
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        temperature=0.2
    )


# --- Custom FAISS Retrieval Tool Generator ---

def create_faiss_search_tool(document_id: str, vector_manager: FAISSVectorStoreManager):
    """Creates a custom tool for querying FAISS vectors scoped to a document_id."""
    
    @tool("search_candidate_resume")
    def search_candidate_resume(query: str) -> str:
        """Search the ingested candidate resume for relevant text context using semantic search."""
        docs = vector_manager.search_by_document_id(query, document_id=document_id, k=4)
        if not docs:
            return "No matching sections found in resume."
        return "\n\n".join([f"[{d.metadata.get('section', 'GENERAL')}]\n{d.page_content}" for d in docs])
        
    return search_candidate_resume


# --- CrewAI Agents ---

def create_resume_extractor_agent(llm=None):
    llm = llm or get_llm()
    return Agent(
        role="Senior Resume Parsing & Data Extraction Specialist",
        goal="Parse unstructured resume text into a strict, comprehensive structured JSON format.",
        backstory="You are an expert HR Tech AI agent specialized in analyzing resumes across technical, executive, and non-technical roles. You extract facts accurately without hallucination.",
        verbose=False,
        allow_delegation=False,
        llm=llm
    )


def create_resume_chat_agent(llm=None):
    llm = llm or get_llm()
    return Agent(
        role="Candidate Career Advisor & Technical Recruiter",
        goal="Provide constructive, detailed analysis and answer questions about candidate experience, skill gaps, and resume improvements.",
        backstory="You are an expert technical recruiter and career coach. You analyze candidate resumes to answer questions and give actionable advice on where candidates need to improve to land target roles.",
        verbose=False,
        allow_delegation=False,
        llm=llm
    )


def create_interview_generator_agent(llm=None):
    llm = llm or get_llm()
    return Agent(
        role="Lead Technical & Behavioral Interviewer",
        goal="Generate 5 to 10 highly relevant, targeted technical and behavioral interview questions based on the candidate's resume profile.",
        backstory="You are a veteran engineering manager and technical interviewer. You formulate probing questions that test the candidate's actual depth in tools, projects, and work history listed on their resume.",
        verbose=False,
        allow_delegation=False,
        llm=llm
    )


def create_interview_evaluator_agent(llm=None):
    llm = llm or get_llm()
    return Agent(
        role="Technical Assessment Evaluator & Career Coach",
        goal="Evaluate candidate interview responses against target question complexity and resume claims, providing a score, strengths, weaknesses, and key areas where the candidate needs to work more.",
        backstory="You are an expert technical evaluator who reviews candidate interview answers, identifies shallow or missing concepts, and provides constructive feedback and actionable study plans.",
        verbose=False,
        allow_delegation=False,
        llm=llm
    )


# --- Workflow Operations ---

def extract_structured_resume(raw_text: str) -> StructuredResumeSchema:
    """Uses CrewAI Extractor Agent to parse raw resume text into StructuredResumeSchema."""
    cfg = get_openrouter_llm()
    if cfg["api_key"].startswith("mock") or not cfg["api_key"]:
        # Fallback structured extraction for testing/mock environments
        print("[CrewAI] Mock key active. Returning structured fallback resume schema.")
        return StructuredResumeSchema(
            personal_info={"name": "Alice Smith", "email": "alice.smith@example.com", "phone": "+1-555-9876", "location": "New York, NY"},
            professional_summary="Senior Data Engineer with 6 years of experience building data pipelines.",
            work_experience=[{
                "job_title": "Lead Data Engineer",
                "company": "DataCloud Inc",
                "start_date": "2021",
                "end_date": "Present",
                "achievements": ["Architected PySpark pipelines", "Built FastAPI REST services"],
                "tech_stack": ["Python", "PySpark", "FastAPI", "PostgreSQL"]
            }],
            skills=["Python", "SQL", "FastAPI", "PySpark", "SQLite", "FAISS"],
            education=[{"degree": "M.S. in Data Science", "institution": "Columbia University", "graduation_year": "2020"}],
            projects=[{"title": "Realtime Stream Processor", "description": "Spark log processor", "technologies_used": ["Python", "Spark"]}],
            certifications=["AWS Certified Data Engineer"],
            total_years_of_experience=6.0
        )

    try:
        llm = get_llm()
        extractor_agent = create_resume_extractor_agent(llm)
        
        extraction_prompt = f"""
        Analyze the following raw resume text and extract the candidate profile into valid JSON matching this exact structure:
        {{
            "personal_info": {{
                "name": "Full Name or null",
                "email": "Email or null",
                "phone": "Phone or null",
                "linkedin": "LinkedIn URL or null",
                "github": "GitHub URL or null",
                "portfolio": "Portfolio URL or null",
                "location": "Location or null"
            }},
            "professional_summary": "Executive summary string",
            "work_experience": [
                {{
                    "job_title": "Role title",
                    "company": "Company Name",
                    "location": "Location or null",
                    "start_date": "Start Date or null",
                    "end_date": "End Date or null",
                    "achievements": ["Achievement 1", "Achievement 2"],
                    "tech_stack": ["Tech 1", "Tech 2"]
                }}
            ],
            "skills": ["Skill 1", "Skill 2"],
            "education": [
                {{
                    "degree": "Degree",
                    "field_of_study": "Major or null",
                    "institution": "University",
                    "graduation_year": "Year or null",
                    "gpa": "GPA or null"
                }}
            ],
            "projects": [
                {{
                    "title": "Project Title",
                    "description": "Project Description",
                    "technologies_used": ["Tech 1"],
                    "link": "URL or null"
                }}
            ],
            "certifications": ["Cert 1"],
            "total_years_of_experience": 3.5
        }}

        RAW RESUME TEXT:
        ---
        {raw_text}
        ---

        Respond ONLY with valid JSON. No markdown codeblock wrapper, no introductory commentary.
        """

        task = Task(
            description=extraction_prompt,
            expected_output="Valid JSON string representing StructuredResumeSchema",
            agent=extractor_agent
        )
        
        crew = Crew(agents=[extractor_agent], tasks=[task], process=Process.sequential)
        result = run_crew_safely(crew)

        raw_output = str(result).strip()
        raw_output = re.sub(r'^```json\s*', '', raw_output)
        raw_output = re.sub(r'^```\s*', '', raw_output)
        raw_output = re.sub(r'\s*```$', '', raw_output)

        parsed_json = json.loads(raw_output)
        return StructuredResumeSchema(**parsed_json)
    except Exception as e:
        print(f"[CrewAI Extraction Fallback]: {e}")
        return StructuredResumeSchema(
            professional_summary=raw_text[:400],
            skills=["Extracted from resume"]
        )


def chat_with_resume(query: str, document_id: str, vector_manager: FAISSVectorStoreManager) -> Dict[str, Any]:
    """Runs Resume Chat Agent to answer queries using FAISS retrieval tool."""
    cfg = get_openrouter_llm()
    sources = [doc.page_content for doc in vector_manager.search_by_document_id(query, document_id, k=3)]
    
    if cfg["api_key"].startswith("mock") or not cfg["api_key"]:
        print("[CrewAI] Mock key active. Returning search-based response.")
        context_str = "\n\n".join(sources) if sources else "Candidate has technical engineering experience."
        return {
            "answer": f"Based on your resume:\n\n{context_str}",
            "sources": sources
        }

    try:
        llm = get_llm()
        chat_agent = create_resume_chat_agent(llm)
        search_tool = create_faiss_search_tool(document_id, vector_manager)
        chat_agent.tools = [search_tool]
        
        task = Task(
            description=f"Use search_candidate_resume tool to find relevant resume context, then answer this question:\nQuery: {query}",
            expected_output="Grounded, evidence-backed answer providing career feedback based on candidate's resume.",
            agent=chat_agent
        )
        
        crew = Crew(agents=[chat_agent], tasks=[task], process=Process.sequential)
        result = run_crew_safely(crew)
        
        return {
            "answer": str(result).strip(),
            "sources": sources
        }
    except Exception as e:
        print(f"[CrewAI Chat Error]: {e}. Falling back to retrieved context.")
        context_str = "\n\n".join(sources) if sources else "Resume context retrieved successfully."
        return {
            "answer": f"Based on your resume context:\n\n{context_str}",
            "sources": sources
        }


def generate_interview_questions(
    structured_resume: Dict[str, Any],
    num_questions: int = 5,
    target_role: Optional[str] = None,
    job_description: Optional[str] = None,
    difficulty_level: Optional[str] = "Mid",
    focus_area: Optional[str] = "Full Mix"
) -> List[Dict[str, str]]:
    """Generates customized technical/behavioral interview questions dynamically based on candidate profile, target role, difficulty level, and focus area."""
    import random
    from datetime import datetime
    
    cfg = get_openrouter_llm()
    
    role_str = target_role or "Software Engineering Position"
    diff_str = difficulty_level or "Mid"
    focus_str = focus_area or "Full Mix"
    jd_str = f"\nTARGET JOB DESCRIPTION:\n{job_description}" if job_description else ""
    session_id_hash = str(uuid.uuid4())[:8]

    if not isinstance(structured_resume, dict):
        if hasattr(structured_resume, "model_dump"):
            structured_resume = structured_resume.model_dump()
        elif hasattr(structured_resume, "dict"):
            structured_resume = structured_resume.dict()
        else:
            structured_resume = {}

    if cfg["api_key"].startswith("mock") or not cfg["api_key"]:
        print(f"[CrewAI] Dynamic session {session_id_hash} starting: Generating {num_questions} [{diff_str} / {focus_str}] questions for {role_str}.")
        skills = structured_resume.get("skills", ["Python", "System Design", "SQL"])
        projects = structured_resume.get("projects", [])
        
        skill_1 = skills[0] if isinstance(skills, list) and skills else "Software Engineering"
        skill_2 = skills[1] if isinstance(skills, list) and len(skills) > 1 else "Database Systems"
        skill_3 = skills[2] if isinstance(skills, list) and len(skills) > 2 else "Cloud Architecture"
        
        first_proj = projects[0] if isinstance(projects, list) and projects else {}
        proj_title = first_proj.get("title", "Core Architecture") if isinstance(first_proj, dict) else getattr(first_proj, "title", "Core Architecture")

        question_pool = [
            {"category": "Technical", "question_text": f"Applying as a {diff_str} candidate for {role_str}, how do you leverage {skill_1} to solve performance bottlenecks in high-throughput applications?"},
            {"category": "Project Deep-Dive", "question_text": f"Walk me through your implementation of '{proj_title}'. At a {diff_str} level, what architectural trade-offs did you evaluate during design?"},
            {"category": "Technical", "question_text": f"In production environments using {skill_2}, how do you manage database indexing, connection pooling, and query latency?"},
            {"category": "Behavioral", "question_text": "Tell me about a complex production outage or bug you diagnosed. What debugging strategy did you execute under pressure?"},
            {"category": "System Design", "question_text": f"For a {diff_str} {role_str}, how would you design a fault-tolerant, scalable microservices architecture incorporating {skill_3}?"},
            {"category": "Technical", "question_text": f"How do you approach automated testing, CI/CD pipeline deployment, and code review standards for {skill_1} projects?"},
            {"category": "Behavioral", "question_text": "Describe a scenario where you had to negotiate technical debt or scope cutbacks with product managers under a tight deadline."},
            {"category": "Project Deep-Dive", "question_text": f"What security, authentication, and data validation practices did you implement in '{proj_title}'?"},
            {"category": "System Design", "question_text": f"How do you optimize vector embeddings, RAG retrieval quality, and memory usage when scaling LLM applications for a {role_str}?"},
            {"category": "Behavioral", "question_text": "How do you stay up-to-date with emerging technical frameworks and mentor team members on best practices?"}
        ]
        
        # Shuffle pool randomly per session to guarantee unique questions every start
        random.seed(f"{session_id_hash}_{datetime.utcnow().timestamp()}")
        shuffled = random.sample(question_pool, min(num_questions, len(question_pool)))
        for idx, q in enumerate(shuffled):
            q["question_number"] = idx + 1
        return shuffled

    llm = get_llm()
    gen_agent = create_interview_generator_agent(llm)
    
    prompt = f"""
    You are a Lead Technical Interviewer evaluating a candidate for the target role: "{role_str}".
    Seniority Level: {diff_str}
    Interview Focus Area: {focus_str}

    Generate a fresh, unique set of {num_questions} customized interview questions for this specific session (Session Seed: {session_id_hash}).

    Analyze the candidate's structured resume JSON below{jd_str} and generate exactly {num_questions} customized interview questions.

    Requirements:
    1. Adjust question depth strictly according to Seniority Level ({diff_str}):
       - Junior: Focus on core syntax, algorithms, framework fundamentals, and learning agility.
       - Mid: Focus on production practices, design patterns, database query tuning, and code maintainability.
       - Senior: Focus on high concurrency, distributed systems trade-offs, performance tuning, and technical debt management.
       - Lead / Staff: Focus on cross-team technical strategy, system scalability, architectural decisions, and mentoring.
    2. Tailor question mix according to Focus Area ({focus_str}):
       - Full Mix: Balanced mix of Technical, Project Deep-Dive, System Design, and Behavioral.
       - Technical Deep-Dive: Focus predominantly on programming languages, frameworks, APIs, and tools listed on resume.
       - System Design & Architecture: Focus predominantly on scalable architecture, data modeling, microservices, and caching.
       - Behavioral & Leadership: Focus predominantly on STAR method scenarios, team conflict, product trade-offs, and project leadership.
    3. Make each question specific, distinct, and directly relevant to the candidate's background.

    CANDIDATE RESUME JSON:
    {json.dumps(structured_resume, indent=2)}

    Format output as a valid JSON array of objects:
    [
        {{
            "question_number": 1,
            "category": "Technical",
            "question_text": "Detailed tailored question text..."
        }},
        ...
    ]
    Respond ONLY with valid JSON. No markdown wrappers.
    """
    
    task = Task(
        description=prompt,
        expected_output=f"JSON array of {num_questions} dynamic interview question objects",
        agent=gen_agent
    )
    
    crew = Crew(agents=[gen_agent], tasks=[task], process=Process.sequential)
    result = run_crew_safely(crew)
    
    raw_output = str(result).strip()
    raw_output = re.sub(r'^```json\s*', '', raw_output)
    raw_output = re.sub(r'^```\s*', '', raw_output)
    raw_output = re.sub(r'\s*```$', '', raw_output)
    
    try:
        questions = json.loads(raw_output)
        return questions
    except Exception as e:
        print(f"[Interview Gen Fallback] JSON parsing error: {e}. Raw output: {raw_output[:200]}")
        skills = structured_resume.get("skills", ["Software Engineering"])
        skills_str = ", ".join(skills[:3]) if isinstance(skills, list) else str(skills)
        return [
            {"question_number": i + 1, "category": "Technical" if i % 2 == 0 else "Behavioral", "question_text": f"For the role of {role_str}, can you explain your experience with {skills_str} and how you applied it in your recent projects?"}
            for i in range(num_questions)
        ]


def evaluate_interview_performance(
    qa_transcript: List[Dict[str, Any]],
    candidate_profile: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluates full interview transcript and generates scorecard, strengths, weaknesses, and study recommendations."""
    cfg = get_openrouter_llm()
    if cfg["api_key"].startswith("mock") or not cfg["api_key"]:
        print("[CrewAI] Mock key active. Returning detailed evaluation report.")
        return {
            "overall_score": 8.5,
            "strengths": [
                "Demonstrated strong practical understanding of PySpark, Kafka, and FastAPI",
                "Clear explanations of asynchronous REST microservices and distributed data pipelines"
            ],
            "weaknesses": [
                "Skipped question on system design and low-latency RAG caching",
                "Could provide deeper quantitative metrics on pipeline throughput improvements"
            ],
            "areas_of_improvement": [
                "Practice system design for FAISS vector database indexing and Redis caching",
                "Prepare structured STAR method answers for behavioral questions on technical debt management"
            ],
            "detailed_report": "The candidate exhibited excellent technical competencies in core Python data engineering and API development. Key strengths include clear articulation of streaming architectures and relational database usage. To improve, the candidate should practice vector retrieval caching and system design questions."
        }

    llm = get_llm()
    eval_agent = create_interview_evaluator_agent(llm)
    
    prompt = f"""
    Analyze the following completed candidate mock interview Q&A transcript alongside their original resume profile.

    CANDIDATE RESUME PROFILE:
    {json.dumps(candidate_profile, indent=2)}

    MOCK INTERVIEW TRANSCRIPT:
    {json.dumps(qa_transcript, indent=2)}

    Produce a comprehensive evaluation report in strict JSON format matching:
    {{
        "overall_score": 8.5,
        "strengths": [
            "Strong understanding of FastAPI async handlers",
            "Clear architectural explanation of distributed vector indexing"
        ],
        "weaknesses": [
            "Vague on database transaction isolation levels",
            "Skipped question on Kubernetes deployment"
        ],
        "areas_of_improvement": [
            "Deepen knowledge of ACID transactions in SQLite and PostgreSQL",
            "Practice Kubernetes manifest setup and pod deployment strategies"
        ],
        "detailed_report": "Detailed narrative feedback evaluating candidate answers against resume claims and industry standards."
    }}

    IMPORTANT: "overall_score" MUST be a float between 0.0 and 100.0 (e.g. 85.0 out of 100.0).

    Respond ONLY with valid JSON.
    """
    
    task = Task(
        description=prompt,
        expected_output="JSON object containing overall_score (0.0 to 100.0 float), strengths, weaknesses, areas_of_improvement, detailed_report",
        agent=eval_agent
    )
    
    crew = Crew(agents=[eval_agent], tasks=[task], process=Process.sequential)
    result = run_crew_safely(crew)
    
    raw_output = str(result).strip()
    raw_output = re.sub(r'^```json\s*', '', raw_output)
    raw_output = re.sub(r'^```\s*', '', raw_output)
    raw_output = re.sub(r'\s*```$', '', raw_output)
    
    try:
        eval_data = json.loads(raw_output)
        score = float(eval_data.get("overall_score", 85.0))
        if score <= 10.0:
            score = score * 10.0
        eval_data["overall_score"] = min(max(round(score, 1), 0.0), 100.0)
        return eval_data
    except Exception as e:
        print(f"[Evaluation Fallback] JSON error: {e}")
        return {
            "overall_score": 7.5,
            "strengths": ["Completed mock interview questions"],
            "weaknesses": ["Further technical depth needed"],
            "areas_of_improvement": ["Review core algorithms & system design"],
            "detailed_report": "Candidate completed interview questions. Review technical concepts for target role."
        }
