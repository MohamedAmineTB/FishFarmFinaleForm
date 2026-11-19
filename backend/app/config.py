"""Application settings, read from environment variables (and `.env`)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+psycopg://fishfarm:fishfarm@localhost:5432/fishfarm"
    # read-only role used by the assistant (falls back to the main URL in development)
    ai_database_url: str | None = None

    jwt_secret: str = "change-me-in-production-please-32-bytes"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    cookie_secure: bool = False

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # simulator / pipeline
    sim_interval_seconds: float = 6.0
    sim_spike_prob: float = 0.0015  # per 6 s tick ≈ one spike an hour; 0.08 = stress test
    sim_dirty_prob: float = 0.05
    sim_fault_prob: float = 0.0005

    # assistant
    llm_provider: str = ""  # anthropic | openai_compat | mock ; empty = auto
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-5-5"
    openai_base_url: str = "http://localhost:11434/v1"
    openai_api_key: str = ""
    openai_model: str = "llama3.1"
    llm_max_output_tokens: int = 800
    llm_max_tool_iterations: int = 5
    rate_limit_per_minute: int = 10
    rate_limit_per_day: int = 100
    daily_token_budget: int = 200_000
    embedding_backend: str = "hash"  # hash | sentence_transformers | auto
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    model_dir: str = "../ml/artifacts"

    @property
    def effective_llm_provider(self) -> str:
        if self.llm_provider:
            return self.llm_provider
        return "anthropic" if self.anthropic_api_key else "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
