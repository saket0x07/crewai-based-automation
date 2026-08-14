#!/usr/bin/env python3
"""
Interactive Terminal Mock Interview CLI for Agentic Hiring System.

This script allows users to take a step-by-step mock interview directly from the command line,
connected to the FastAPI backend and CrewAI Multi-Agent system.
"""

import sys
import os
import time
import requests
from typing import Optional, List, Dict, Any

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")

# Terminal ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner(title: str, color: str = CYAN):
    """Prints a styled terminal banner."""
    line = "=" * 70
    print(f"\n{color}{BOLD}{line}")
    print(f"  {title}")
    print(f"{line}{RESET}\n")


def check_api_server() -> bool:
    """Verifies if the FastAPI backend server is online."""
    try:
        res = requests.get(f"{API_BASE_URL}/", timeout=3)
        return res.status_code == 200
    except Exception:
        return False


def get_stored_resumes() -> List[Dict[str, Any]]:
    """Retrieves uploaded candidate resumes from SQLite database or API."""
    try:
        from database import SessionLocal
        from models import ParsedResumeModel, ResumeModel

        db = SessionLocal()
        try:
            records = db.query(ParsedResumeModel).all()
            resumes = []
            for r in records:
                resume_meta = db.query(ResumeModel).filter(ResumeModel.document_id == r.document_id).first()
                filename = resume_meta.filename if resume_meta else "Unknown File"
                resumes.append({
                    "document_id": r.document_id,
                    "candidate_name": r.candidate_name or "Anonymous Candidate",
                    "email": r.email or "N/A",
                    "filename": filename
                })
            return resumes
        finally:
            db.close()
    except Exception as e:
        print(f"{YELLOW}Warning fetching local DB resumes: {e}{RESET}")
        return []


def upload_resume_interactive() -> Optional[str]:
    """Prompts user for file path and uploads resume to backend."""
    print(f"{BOLD}Upload New Resume File (.pdf, .docx, .txt){RESET}")
    file_path = input(f"{CYAN}Enter full path to resume file: {RESET}").strip().strip('"').strip("'")
    
    if not os.path.exists(file_path):
        print(f"{RED}File not found at path: {file_path}{RESET}")
        return None

    filename = os.path.basename(file_path)
    print(f"{YELLOW}Uploading & Parsing {filename}... Please wait.{RESET}")
    
    try:
        with open(file_path, "rb") as f:
            files = {"file": (filename, f, "application/octet-stream")}
            response = requests.post(f"{API_BASE_URL}/api/v1/resumes/upload", files=files)
            
        if response.status_code == 201:
            data = response.json()
            doc_id = data["document_id"]
            cand_name = data.get("candidate_name") or "Candidate"
            print(f"{GREEN}✔ Resume parsed & indexed successfully! Candidate: {cand_name} (ID: {doc_id}){RESET}")
            return doc_id
        else:
            print(f"{RED}Error uploading resume: {response.text}{RESET}")
            return None
    except Exception as e:
        print(f"{RED}Failed to connect to API server: {e}{RESET}")
        return None


def select_or_upload_resume() -> Optional[str]:
    """Interactive resume selection menu."""
    resumes = get_stored_resumes()
    
    print_banner("INTERACTIVE MOCK INTERVIEW SETUP", CYAN)
    
    if resumes:
        print(f"{BOLD}Existing Candidate Resumes in System:{RESET}")
        for idx, r in enumerate(resumes, 1):
            print(f"  [{idx}] {r['candidate_name']} ({r['filename']}) - ID: {r['document_id'][:8]}...")
        print(f"  [U] Upload a New Resume File")
        print(f"  [Q] Quit")
        
        choice = input(f"\n{CYAN}Select an option (1-{len(resumes)}, U, Q): {RESET}").strip().upper()
        if choice == "Q":
            sys.exit(0)
        elif choice == "U":
            return upload_resume_interactive()
        elif choice.isdigit() and 1 <= int(choice) <= len(resumes):
            selected = resumes[int(choice) - 1]
            print(f"{GREEN}Selected Candidate: {selected['candidate_name']} ({selected['document_id']}){RESET}")
            return selected["document_id"]
        else:
            print(f"{RED}Invalid selection.{RESET}")
            return None
    else:
        print(f"{YELLOW}No existing candidate resumes found in database.{RESET}")
        return upload_resume_interactive()


def conduct_interview(document_id: str):
    """Executes the interactive terminal interview session."""
    print_banner("INTERVIEW CONFIGURATION", CYAN)
    
    target_role = input(f"{BOLD}Enter Target Job Title (optional, e.g. 'Senior Backend Engineer') [Press Enter to skip]: {RESET}").strip()
    job_desc = input(f"{BOLD}Enter Job Description context (optional) [Press Enter to skip]: {RESET}").strip()
    
    num_q_str = input(f"{BOLD}How many questions would you like? (1-10, default 5): {RESET}").strip()
    try:
        num_questions = int(num_q_str) if num_q_str else 5
        num_questions = min(max(num_questions, 1), 10)
    except ValueError:
        num_questions = 5

    print(f"\n{BOLD}Select Seniority Level:{RESET}")
    print("  [1] Junior Level (Fundamentals & Core Syntax)")
    print("  [2] Mid Level (Production Patterns & Query Tuning) [Default]")
    print("  [3] Senior Level (High Concurrency & Architecture Trade-offs)")
    print("  [4] Lead / Staff Level (Strategy & Scalability)")
    diff_choice = input(f"{CYAN}Choice (1-4, default 2): {RESET}").strip()
    diff_map = {"1": "Junior", "2": "Mid", "3": "Senior", "4": "Lead / Staff"}
    difficulty_level = diff_map.get(diff_choice, "Mid")

    print(f"\n{BOLD}Select Interview Focus Area:{RESET}")
    print("  [1] Full Mix (Balanced 360° Assessment) [Default]")
    print("  [2] Technical Deep-Dive (Coding & Framework Internals)")
    print("  [3] System Design & Architecture (Microservices & Caching)")
    print("  [4] Behavioral & Leadership (STAR Method & Scenarios)")
    focus_choice = input(f"{CYAN}Choice (1-4, default 1): {RESET}").strip()
    focus_map = {"1": "Full Mix", "2": "Technical Deep-Dive", "3": "System Design & Architecture", "4": "Behavioral & Leadership"}
    focus_area = focus_map.get(focus_choice, "Full Mix")

    # 1. Start Interview Session
    print(f"\n{YELLOW}Initializing [{difficulty_level} / {focus_area}] interview session via CrewAI...{RESET}")
    start_payload = {
        "document_id": document_id,
        "num_questions": num_questions,
        "target_role": target_role if target_role else None,
        "job_description": job_desc if job_desc else None,
        "difficulty_level": difficulty_level,
        "focus_area": focus_area
    }
    
    try:
        res = requests.post(f"{API_BASE_URL}/api/v1/interview/start", json=start_payload)
        if res.status_code != 201:
            print(f"{RED}Failed to start interview: {res.text}{RESET}")
            return
        
        start_data = res.json()
        interview_id = start_data["interview_id"]
        total_questions = start_data["total_questions"]
        print(f"{GREEN}✔ Interview session started! Session ID: {interview_id}{RESET}\n")
    except Exception as e:
        print(f"{RED}API connection error: {e}{RESET}")
        return

    # 2. Sequential Question & Answer Loop
    question_count = 0
    while True:
        try:
            next_res = requests.get(f"{API_BASE_URL}/api/v1/interview/{interview_id}/next")
            if next_res.status_code != 200:
                print(f"{RED}Error fetching next question.{RESET}")
                break
                
            q_data = next_res.json()
            if q_data.get("is_completed"):
                print(f"\n{GREEN}✔ All questions answered! Proceeding to evaluation...{RESET}")
                break
                
            q_num = q_data["question_number"]
            q_cat = q_data.get("question_category", "Technical")
            q_text = q_data["question_text"]
            
            print_banner(f"QUESTION {q_num} OF {total_questions}  [{q_cat.upper()}]", YELLOW)
            print(f"{BOLD}{q_text}{RESET}\n")
            print(f"{CYAN}Commands: Type your answer below, or type ':skip' to skip, ':exit' to quit.{RESET}")
            
            user_ans = input(f"{BOLD}Your Answer > {RESET}").strip()
            
            if user_ans.lower() == ":exit":
                print(f"\n{YELLOW}Interview session ended early by user.{RESET}")
                return
            elif user_ans.lower() == ":skip" or not user_ans:
                ans_payload = {"response_text": "", "proceed": False}
                print(f"{YELLOW}Skipped Question {q_num}.{RESET}")
            else:
                ans_payload = {"response_text": user_ans, "proceed": True}
                print(f"{GREEN}✔ Answer recorded for Question {q_num}.{RESET}")

            # Send answer
            ans_res = requests.post(f"{API_BASE_URL}/api/v1/interview/{interview_id}/answer", json=ans_payload)
            if ans_res.status_code != 200:
                print(f"{RED}Error submitting answer: {ans_res.text}{RESET}")
                break

        except KeyboardInterrupt:
            print(f"\n{YELLOW}\nInterview interrupted by user.{RESET}")
            return
        except Exception as e:
            print(f"{RED}Error during question loop: {e}{RESET}")
            break

    # 3. Finalize & Display Scorecard Evaluation Report
    print_banner("EVALUATING CANDIDATE PERFORMANCE", GREEN)
    print(f"{YELLOW}CrewAI InterviewEvaluatorAgent is analyzing transcript and generating scorecard... Please wait.{RESET}\n")
    
    start_time = time.time()
    try:
        eval_res = requests.post(f"{API_BASE_URL}/api/v1/interview/{interview_id}/finalize")
        elapsed = round(time.time() - start_time, 1)
        
        if eval_res.status_code == 200:
            report = eval_res.json()
            display_scorecard(report, elapsed)
        else:
            print(f"{RED}Error generating evaluation report: {eval_res.text}{RESET}")
    except Exception as e:
        print(f"{RED}Error communicating with evaluation endpoint: {e}{RESET}")


def display_scorecard(report: Dict[str, Any], elapsed_seconds: float):
    """Renders a formatted evaluation scorecard in the terminal."""
    score = float(report.get("overall_score", 0.0))
    if score <= 10.0:
        score = score * 10.0
    strengths = report.get("strengths", [])
    weaknesses = report.get("weaknesses", [])
    areas = report.get("areas_of_improvement", [])
    detailed_report = report.get("detailed_report", "")

    color_score = GREEN if score >= 75 else (YELLOW if score >= 50 else RED)

    print_banner("CANDIDATE MOCK INTERVIEW EVALUATION SCORECARD", BOLD + CYAN)
    print(f"  {BOLD}OVERALL ACCURACY SCORE:{RESET} {color_score}{BOLD}{score:.1f} / 100{RESET}")
    print(f"  {BOLD}Evaluation Completed In:{RESET} {elapsed_seconds} seconds\n")

    print(f"{GREEN}{BOLD}✔ KEY STRENGTHS DEMONSTRATED:{RESET}")
    if isinstance(strengths, list) and strengths:
        for s in strengths:
            print(f"  • {s}")
    else:
        print(f"  • {strengths}")

    print(f"\n{RED}{BOLD}✖ KNOWLEDGE GAPS & WEAKNESSES IDENTIFIED:{RESET}")
    if isinstance(weaknesses, list) and weaknesses:
        for w in weaknesses:
            print(f"  • {w}")
    else:
        print(f"  • {weaknesses}")

    print(f"\n{YELLOW}{BOLD}📌 ACTIONABLE STUDY RECOMMENDATIONS (WHERE TO WORK MORE):{RESET}")
    if isinstance(areas, list) and areas:
        for a in areas:
            print(f"  • {a}")
    else:
        print(f"  • {areas}")

    if detailed_report:
        print(f"\n{BOLD}DETAILED ASSESSMENT SUMMARY:{RESET}")
        print(f"{detailed_report}")

    line = "=" * 70
    print(f"\n{CYAN}{BOLD}{line}{RESET}\n")


def main():
    """Main CLI entrypoint."""
    if not check_api_server():
        print(f"{RED}ERROR: FastAPI backend server is not running at {API_BASE_URL}{RESET}")
        print(f"Please start the server first in another terminal window:")
        print(f"{CYAN}  .\\venv\\Scripts\\python main.py{RESET}\n")
        sys.exit(1)

    document_id = select_or_upload_resume()
    if document_id:
        conduct_interview(document_id)


if __name__ == "__main__":
    main()
