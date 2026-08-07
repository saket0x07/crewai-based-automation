from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from routes.resumes import router as resumes_router
from routes.interviews import router as interviews_router

app = FastAPI(
    title=settings.APP_NAME,
    description="Agentic Resume Ingestion, Structured Extraction, RAG Chat & Interactive Mock Interview Platform",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(resumes_router)
app.include_router(interviews_router)

@app.on_event("startup")
def on_startup():
    """Initializes database tables on application launch."""
    init_db()

@app.get("/")
def root():
    return {
        "message": "Welcome to Agentic Resume & Mock Interview API",
        "docs": "/docs",
        "status": "active"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
