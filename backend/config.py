"""Configuration management from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration."""
    
    MILVUS_URI = os.getenv("MILVUS_URI", "./data/milvus.db")
    COLLECTION_NAME = os.getenv("COLLECTION_NAME", "papers")
    
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    
    FETCH_K = int(os.getenv("FETCH_K", "20"))
    TOP_K = int(os.getenv("TOP_K", "5"))
    RRF_K = int(os.getenv("RRF_K", "60"))
    
    ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() == "true"
    CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "1000"))

    # Evidence selection and TRACE explainability
    ENABLE_EVIDENCE_DIVERSITY = os.getenv("ENABLE_EVIDENCE_DIVERSITY", "true").lower() == "true"
    EVIDENCE_DIVERSITY_WEIGHT = float(os.getenv("EVIDENCE_DIVERSITY_WEIGHT", "0.25"))
    EXPLANATION_GUARD_ENABLED = os.getenv("EXPLANATION_GUARD_ENABLED", "true").lower() == "true"
    AUTO_EVIDENCE_REPAIR = os.getenv("AUTO_EVIDENCE_REPAIR", "true").lower() == "true"
    AUTO_EVIDENCE_REPAIR_MAX_QUERIES = int(os.getenv("AUTO_EVIDENCE_REPAIR_MAX_QUERIES", "2"))
    ENABLE_SEMANTIC_AUDIT = os.getenv("ENABLE_SEMANTIC_AUDIT", "true").lower() == "true"
    
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "qwen3:32b")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))

    VLM_ENABLED = os.getenv("VLM_ENABLED", "false").lower() == "true"
    VLM_BASE_URL = os.getenv("VLM_BASE_URL", "http://localhost:11434/v1")
    VLM_MODEL = os.getenv("VLM_MODEL", "qwen-vl")
    VLM_API_KEY = os.getenv("VLM_API_KEY", "ollama")

    # RAGAS judge LLM (falls back to main LLM if unset)
    RAGAS_LLM_BASE_URL = os.getenv("RAGAS_LLM_BASE_URL", LLM_BASE_URL)
    RAGAS_LLM_MODEL = os.getenv("RAGAS_LLM_MODEL", LLM_MODEL)
    RAGAS_LLM_API_KEY = os.getenv("RAGAS_LLM_API_KEY", LLM_API_KEY)

    POSTGRES_URI = os.getenv("POSTGRES_URI", "postgresql://postgres:postgres@localhost:5432/ruletrace_scholar")
    # ``postgres`` is recommended in production. ``auto`` provides a
    # zero-configuration SQLite fallback for local preview and tests.
    METADATA_BACKEND = os.getenv("METADATA_BACKEND", "auto").lower()

    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))

    # Keyless arXiv discovery plus optional higher-rate Semantic Scholar access.
    SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "")
    DISCOVERY_MAX_RESULTS = int(os.getenv("DISCOVERY_MAX_RESULTS", "20"))
    DISCOVERY_TIMEOUT_SECONDS = float(os.getenv("DISCOVERY_TIMEOUT_SECONDS", "30"))
    DISCOVERY_DOWNLOAD_TIMEOUT_SECONDS = float(os.getenv("DISCOVERY_DOWNLOAD_TIMEOUT_SECONDS", "180"))

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))
