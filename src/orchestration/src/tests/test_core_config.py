"""Tests for core/config.py — Settings configuration from environment variables."""
import os

import pytest
from pydantic import ValidationError

from orchestration.core.config import Settings, get_settings


def test_settings_defaults():
    """Settings should load with sensible defaults."""
    s = Settings(_env_file=None)
    assert s.app_name == "leader-subagent-orchestration"
    assert s.app_env == "production"
    assert s.log_level == "INFO"
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.workers == 1
    assert s.debug is False


def test_settings_from_environment(monkeypatch):
    """Settings should read values from environment variables."""
    monkeypatch.setenv("APP_NAME", "test-app")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MAX_PARALLEL_SUBAGENTS", "8")
    monkeypatch.setenv("QUALITY_MIN_SCORE", "0.9")

    s = Settings(_env_file=None)
    assert s.app_name == "test-app"
    assert s.port == 9000
    assert s.debug is True
    assert s.log_level == "DEBUG"
    assert s.max_parallel_subagents == 8
    assert s.quality_min_score == 0.9


def test_settings_api_keys_default_none(monkeypatch):
    """API keys should default to None when not set."""
    for key in [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "LLAMA_API_KEY",
        "MISTRAL_API_KEY",
        "DEEPSEEK_API_KEY",
        "QWEN_API_KEY",
        "LOCAL_LLM_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    s = Settings(_env_file=None)
    assert s.openai_api_key is None
    assert s.anthropic_api_key is None
    assert s.gemini_api_key is None
    assert s.llama_api_key is None
    assert s.mistral_api_key is None
    assert s.deepseek_api_key is None
    assert s.qwen_api_key is None
    assert s.local_llm_api_key is None


def test_settings_clamped_values(monkeypatch):
    """Settings should clamp values to valid ranges."""
    monkeypatch.setenv("MAX_PARALLEL_SUBAGENTS", "100")
    monkeypatch.setenv("DEFAULT_MAX_RETRIES", "100")
    monkeypatch.setenv("DEFAULT_REQUEST_TIMEOUT_SEC", "99999")

    s = Settings(_env_file=None)
    # max_parallel_subagents clamped to max 8
    assert s.max_parallel_subagents == 8
    # default_max_retries clamped to max 5
    assert s.default_max_retries == 5
    # default_request_timeout_sec clamped to max 1800
    assert s.default_request_timeout_sec == 1800


def test_get_settings_singleton():
    """get_settings should return a cached Settings instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_database_url_builds_from_parts(monkeypatch):
    """database_url should be constructed from DB parts when not set directly."""
    for k in ["DATABASE_URL", "DB_USER", "DB_PASS", "DB_HOST", "DB_PORT", "DB_NAME"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DB_USER", "myuser")
    monkeypatch.setenv("DB_PASS", "mypass")
    monkeypatch.setenv("DB_HOST", "myhost")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "mydb")

    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg2://myuser:mypass@myhost:5433/mydb"


def test_sandbox_defaults(monkeypatch):
    """Security sandbox defaults should be safe."""
    s = Settings(_env_file=None)
    assert s.sandbox_enabled is True
    assert s.sandbox_timeout_sec == 30
    assert s.sandbox_max_memory_mb == 512


def test_otel_defaults(monkeypatch):
    """Observability defaults should point to local OTel collector."""
    s = Settings(_env_file=None)
    assert s.otel_service_name == "orchestration-system"
    assert s.otel_exporter_otlp_endpoint == "http://localhost:4318"
