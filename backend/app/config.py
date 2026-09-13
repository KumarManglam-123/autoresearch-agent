import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if available
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Models
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

# AWS Settings
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "autoresearch-sessions")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "autoresearch-reports")

# Application Settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
VECTOR_STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "vector_stores"
VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_STORAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "local_storage"
LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
