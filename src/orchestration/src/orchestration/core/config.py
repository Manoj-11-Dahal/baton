"""Application configuration loaded from environment variables.

API keys and secrets are read from environment variables (or a secrets manager
in production). They are held in memory only and never written to disk or logs.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ---- Application ----
    app_name: str = Field(default="leader-subagent-orchestration", env="APP_NAME")
    app_env: str = Field(default="production", env="APP_ENV")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    workers: int = Field(default=1, env="WORKERS")
    debug: bool = Field(default=False, env="DEBUG")

    # ---- PostgreSQL ----
    db_host: str = Field(default="localhost", env="DB_HOST")
    db_port: int = Field(default=5432, env="DB_PORT")
    db_name: str = Field(default="orchestration", env="DB_NAME")
    db_user: str = Field(default="orch_user", env="DB_USER")
    db_pass: Optional[str] = Field(default=None, env="DB_PASS")
    database_url: Optional[str] = Field(default=None, env="DATABASE_URL")

    # ---- Redis ----
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_db: int = Field(default=0, env="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")

    # ---- Qdrant ----
    qdrant_host: str = Field(default="localhost", env="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, env="QDRANT_PORT")
    qdrant_api_key: Optional[str] = Field(default=None, env="QDRANT_API_KEY")
    qdrant_collection: str = Field(default="research_embeddings", env="QDRANT_COLLECTION")

    # ---- LLM Provider API keys (env only) ----
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    google_api_key: Optional[str] = Field(default=None, env="GOOGLE_API_KEY")
    gemini_api_key: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    llama_api_key: Optional[str] = Field(default=None, env="LLAMA_API_KEY")
    mistral_api_key: Optional[str] = Field(default=None, env="MISTRAL_API_KEY")
    deepseek_api_key: Optional[str] = Field(default=None, env="DEEPSEEK_API_KEY")
    qwen_api_key: Optional[str] = Field(default=None, env="QWEN_API_KEY")

    # Optional OpenAI-compatible base URLs (local models, Llama, etc.)
    openai_base_url: Optional[str] = Field(default="https://api.openai.com/v1", env="OPENAI_BASE_URL")
    anthropic_base_url: Optional[str] = Field(default="https://api.anthropic.com", env="ANTHROPIC_BASE_URL")
    google_base_url: Optional[str] = Field(default="https://generativelanguage.googleapis.com/v1", env="GOOGLE_BASE_URL")
    llama_base_url: Optional[str] = Field(default=None, env="LLAMA_BASE_URL")
    mistral_base_url: Optional[str] = Field(default="https://api.mistral.ai/v1", env="MISTRAL_BASE_URL")
    deepseek_base_url: Optional[str] = Field(default="https://api.deepseek.com/v1", env="DEEPSEEK_BASE_URL")
    qwen_base_url: Optional[str] = Field(default="https://dashscope.aliyuncs.com/api/v1", env="QWEN_BASE_URL")

    # Local model support (Ollama / llama.cpp / vLLM / TGI OpenAI-compatible)
    local_llm_base_url: Optional[str] = Field(default="http://localhost:11434/v1", env="LOCAL_LLM_BASE_URL")
    local_llm_api_key: Optional[str] = Field(default=None, env="LOCAL_LLM_API_KEY")

    # ---- Security ----
    encryption_key: str = Field(default="change-me-in-production", env="ENCRYPTION_KEY")
    api_auth_token: str = Field(default="change-me-in-production", env="API_AUTH_TOKEN")
    sandbox_enabled: bool = Field(default=True, env="SANDBOX_ENABLED")
    sandbox_timeout_sec: int = Field(default=30, env="SANDBOX_TIMEOUT_SEC")
    sandbox_max_memory_mb: int = Field(default=512, env="SANDBOX_MAX_MEMORY_MB")

    # ---- Observability ----
    otel_service_name: str = Field(default="orchestration-system", env="OTEL_SERVICE_NAME")
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4318", env="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_exporter_otlp_protocol: str = Field(default="http/protobuf", env="OTEL_EXPORTER_OTLP_PROTOCOL")
    otel_log_level: str = Field(default="INFO", env="OTEL_LOG_LEVEL")

    # ---- Model Router defaults ----
    default_max_retries: int = Field(default=3, env="DEFAULT_MAX_RETRIES")
    default_request_timeout_sec: int = Field(default=120, env="DEFAULT_REQUEST_TIMEOUT_SEC")
    default_context_budget: int = Field(default=4000, env="DEFAULT_CONTEXT_BUDGET")
    max_parallel_subagents: int = Field(default=5, env="MAX_PARALLEL_SUBAGENTS")

    # ---- Quality Control ----
    quality_enabled: bool = Field(default=True, env="QUALITY_ENABLED")
    quality_min_score: float = Field(default=0.7, env="QUALITY_MIN_SCORE")
    quality_max_review_attempts: int = Field(default=2, env="QUALITY_MAX_REVIEW_ATTEMPTS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    @field_validator("database_url", mode="before")
    @classmethod
    def _build_database_url(cls, v, info):
        if v:
            return v
        data = info.data or {}
        user = data.get("db_user") or "orch_user"
        password = data.get("db_pass") or "orch_pass"
        host = data.get("db_host") or "localhost"
        port = data.get("db_port") or 5432
        name = data.get("db_name") or "orchestration"
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"

    @model_validator(mode="after")
    def _clamp_values(self) -> "Settings":
        self.default_max_retries = min(max(self.default_max_retries, 0), 5)
        self.default_request_timeout_sec = min(max(self.default_request_timeout_sec, 10), 1800)
        self.default_context_budget = min(max(self.default_context_budget, 4000), 2_000_000)
        self.max_parallel_subagents = min(max(self.max_parallel_subagents, 1), 8)
        self.quality_max_review_attempts = min(max(self.quality_max_review_attempts, 0), 10)
        if not self.database_url:
            self.database_url = (
                f"postgresql+psycopg2://{self.db_user}:{self.db_pass or 'orch_pass'}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()
