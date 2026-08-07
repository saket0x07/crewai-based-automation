import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Agentic Resume & Interview System"
    DEBUG: bool = True
    
    # OpenRouter Config
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openrouter/openai/gpt-4o-mini")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    
    # OpenAI Fallback / Direct Config
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Embedding Config
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    
    # Persistence Paths
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    FAISS_STORAGE_DIR: str = os.getenv("FAISS_STORAGE_DIR", "./data/faiss_index")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./data/uploads")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure directories exist
Path(settings.FAISS_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

def get_openrouter_llm():
    """
    Returns configured LLM instance for CrewAI / LangChain using OpenRouter.
    CrewAI natively supports openrouter/ prefixes or custom api_base & api_key.
    """
    api_key = settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        api_key = "mock_api_key"
        
    return {
        "model": settings.OPENROUTER_MODEL,
        "api_key": api_key,
        "base_url": settings.OPENROUTER_BASE_URL
    }
