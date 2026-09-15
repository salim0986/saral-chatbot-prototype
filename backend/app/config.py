"""
Application configuration loaded from environment variables.
Uses pydantic-settings so every setting is type-checked at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    app_name: str = "saral-chatbot"
    app_version: str = "0.1.0"
    debug: bool = False

    # Groq (generation LLM)
    # Supports both GROQ_API_KEY (standard) and GROK_KEY (legacy alias)
    groq_api_key: str = ""
    grok_key: str = ""  # alias - will be used if groq_api_key is empty

    # OpenAI (primary generation LLM, falls back to Groq)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Qdrant (vector store)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "saral_chunks"

    # SQLite (session store)
    sqlite_db_path: str = "./saral.db"

    # Ingestion
    max_upload_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    chunk_max_tokens: int = 512
    chunk_overlap_tokens: int = 64
    retrieval_score_threshold: float = 0.65
    retrieval_k_floor: int = 3
    retrieval_k_ceiling: int = 10

    # Generation
    groq_model: str = "openai/gpt-oss-20b"
    citation_coverage_threshold: float = 0.80

    # Dev-time Groq response cache
    # Set USE_GROQ_CACHE=true in .env to cache responses to disk during development.
    # This prevents burning quota on repeated identical prompts while iterating.
    # NEVER enable in production (stale cache = wrong output).
    use_groq_cache: bool = False
    groq_cache_dir: str = "./.groq_cache"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def effective_groq_key(self) -> str:
        """Return the active Groq API key, supporting both env var names."""
        return self.groq_api_key or self.grok_key


settings = Settings()
