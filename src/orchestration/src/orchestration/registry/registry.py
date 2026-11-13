"""Central Model Registry (PostgreSQL-backed with in-memory cache).

Never assumes every provider supports every modality. Each model entry carries
its capabilities, modalities, pricing, context window, latency, availability,
and fallback configuration. The Leader Agent consults this registry before
assigning any model to a sub-agent.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from ..core.config import get_settings
from ..core.observability import get_observability
from ..core.types import (
    Modality,
    ModelCapability,
    ModelRegistryEntry,
    ProviderName,
)


def _row_to_entry(row: dict) -> ModelRegistryEntry:
    return ModelRegistryEntry(
        provider=ProviderName(row["provider"]),
        model_id=row["model_id"],
        name=row.get("name"),
        capabilities=[ModelCapability(c) for c in (row.get("capabilities") or [])],
        modalities=[Modality(m) for m in (row.get("modalities") or [])],
        context_window=row.get("context_window"),
        pricing_input_per_1m=row.get("pricing_input_per_1m"),
        pricing_output_per_1m=row.get("pricing_output_per_1m"),
        latency_ms=row.get("latency_ms"),
        availability=bool(row.get("availability", True)),
        fallback_models=row.get("fallback_models") or [],
        base_url=row.get("base_url"),
        api_key_env=row.get("api_key_env"),
        enabled=bool(row.get("enabled", True)),
        metadata=row.get("metadata") or {},
    )


class ModelRegistry:
    """Central registry of all providers and models.

    Loaded from PostgreSQL and cached in-memory (with TTL). Provides capability-
    and modality-aware lookups used by the router and the Leader Agent.
    """

    def __init__(self, database_url: Optional[str] = None, cache_ttl_sec: int = 60):
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self.cache_ttl_sec = cache_ttl_sec
        self._pool: Optional[pool.ThreadedConnectionPool] = None
        self._cache: Dict[str, ModelRegistryEntry] = {}
        self._cache_loaded_at: float = 0.0
        self.obs = get_observability()

    # ------------------------------------------------------------------ connection

    def _get_pool(self) -> pool.ThreadedConnectionPool:
        if self._pool is None:
            try:
                self._pool = pool.ThreadedConnectionPool(minconn=1, maxconn=5, dsn=self.database_url)
            except Exception:  # noqa: BLE001
                # DB unreachable: keep pool as None; operations degrade gracefully.
                self._pool = None
        return self._pool

    def _ensure_schema(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS model_registry (
                    provider TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    name TEXT,
                    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
                    modalities JSONB NOT NULL DEFAULT '[]'::jsonb,
                    context_window INTEGER,
                    pricing_input_per_1m DOUBLE PRECISION,
                    pricing_output_per_1m DOUBLE PRECISION,
                    latency_ms INTEGER,
                    availability BOOLEAN NOT NULL DEFAULT TRUE,
                    fallback_models JSONB NOT NULL DEFAULT '[]'::jsonb,
                    base_url TEXT,
                    api_key_env TEXT,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (provider, model_id)
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS model_registry_audit (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    changed_by TEXT NOT NULL DEFAULT 'system',
                    action TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    old_values JSONB,
                    new_values JSONB
                );
                """
            )
            conn.commit()

    def _connect(self):
        p = self._get_pool()
        if p is None:
            raise ConnectionError("PostgreSQL unavailable.")
        return p.getconn()

    def _release(self, conn) -> None:
        try:
            self._get_pool().putconn(conn)
        except Exception:
            pass

    # ------------------------------------------------------------------ cache

    def _cache_stale(self) -> bool:
        # loaded_at == 0 means the cache was populated manually (e.g. in tests
        # or by seed_defaults) and should be treated as fresh.
        if self._cache_loaded_at == 0:
            return False
        return (time.time() - self._cache_loaded_at) > self.cache_ttl_sec or not self._cache

    def _load_cache(self) -> None:
        """Load models from PostgreSQL; degrade gracefully if the DB is unavailable."""
        try:
            conn = self._connect()
        except Exception:  # noqa: BLE001
            # No database available — keep an empty cache. The system still works
            # with whatever entries were seeded into memory via seed_defaults().
            self._cache = {}
            self._cache_loaded_at = time.time()
            return
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT provider, model_id, name, capabilities, modalities, context_window, "
                    "pricing_input_per_1m, pricing_output_per_1m, latency_ms, availability, "
                    "fallback_models, base_url, api_key_env, enabled, metadata "
                    "FROM model_registry WHERE enabled = TRUE"
                )
                rows = cur.fetchall()
            self._cache = {}
            for row in rows:
                entry = _row_to_entry(dict(row))
                self._cache[f"{entry.provider.value}:{entry.model_id}"] = entry
            self._cache_loaded_at = time.time()
        finally:
            self._release(conn)

    def _ensure_loaded(self) -> None:
        if self._cache_stale():
            self._load_cache()

    # ------------------------------------------------------------------ public API

    def seed_defaults(self) -> None:
        """Seed the registry with known provider/model capability metadata.

        Degrades gracefully if PostgreSQL is unavailable; entries are kept in
        the in-memory cache so the system still functions.
        """
        entries = [
            # ---------------- OpenAI ----------------
            ModelRegistryEntry(
                provider=ProviderName.OPENAI,
                model_id="gpt-5",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.JSON_OUTPUT,
                    ModelCapability.MULTIMODAL_INPUT,
                    ModelCapability.LONG_CONTEXT,
                ],
                modalities=[Modality.TEXT, Modality.IMAGE, Modality.MULTIMODAL],
                context_window=400000,
                pricing_input_per_1m=1.25,
                pricing_output_per_1m=10.0,
                latency_ms=1200,
                availability=True,
                fallback_models=["gpt-4o-mini"],
                base_url=None,
                api_key_env="OPENAI_API_KEY",
            ),
            ModelRegistryEntry(
                provider=ProviderName.OPENAI,
                model_id="gpt-4o",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.JSON_OUTPUT,
                    ModelCapability.MULTIMODAL_INPUT,
                ],
                modalities=[Modality.TEXT, Modality.IMAGE, Modality.MULTIMODAL],
                context_window=128000,
                pricing_input_per_1m=2.50,
                pricing_output_per_1m=10.0,
                latency_ms=1000,
                availability=True,
                fallback_models=["gpt-4o-mini"],
                base_url=None,
                api_key_env="OPENAI_API_KEY",
            ),
            ModelRegistryEntry(
                provider=ProviderName.OPENAI,
                model_id="gpt-4o-mini",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.JSON_OUTPUT,
                ],
                modalities=[Modality.TEXT, Modality.IMAGE, Modality.MULTIMODAL],
                context_window=128000,
                pricing_input_per_1m=0.15,
                pricing_output_per_1m=0.60,
                latency_ms=600,
                availability=True,
                fallback_models=[],
                base_url=None,
                api_key_env="OPENAI_API_KEY",
            ),
            ModelRegistryEntry(
                provider=ProviderName.OPENAI,
                model_id="dall-e-3",
                capabilities=[ModelCapability.IMAGE_GENERATION],
                modalities=[Modality.IMAGE],
                context_window=4000,
                pricing_input_per_1m=None,
                pricing_output_per_1m=None,
                latency_ms=5000,
                availability=True,
                fallback_models=[],
                base_url=None,
                api_key_env="OPENAI_API_KEY",
            ),
            # DALL-E does NOT support video, audio, or code generation —
            # those capabilities are deliberately absent.
            # ---------------- Anthropic ----------------
            ModelRegistryEntry(
                provider=ProviderName.ANTHROPIC,
                model_id="claude-3-5-sonnet-20241022",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.MULTIMODAL_INPUT,
                    ModelCapability.JSON_OUTPUT,
                ],
                modalities=[Modality.TEXT, Modality.IMAGE, Modality.MULTIMODAL],
                context_window=200000,
                pricing_input_per_1m=3.00,
                pricing_output_per_1m=15.0,
                latency_ms=1500,
                availability=True,
                fallback_models=["claude-3-haiku-20240307"],
                base_url=None,
                api_key_env="ANTHROPIC_API_KEY",
            ),
            ModelRegistryEntry(
                provider=ProviderName.ANTHROPIC,
                model_id="claude-3-haiku-20240307",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.MULTIMODAL_INPUT,
                ],
                modalities=[Modality.TEXT, Modality.IMAGE, Modality.MULTIMODAL],
                context_window=200000,
                pricing_input_per_1m=0.25,
                pricing_output_per_1m=1.25,
                latency_ms=600,
                availability=True,
                fallback_models=[],
                base_url=None,
                api_key_env="ANTHROPIC_API_KEY",
            ),
            # Anthropic does NOT support image/video/audio GENERATION natively;
            # only text + image input (multimodal). Generation capabilities are
            # deliberately absent.
            # ---------------- Google Gemini ----------------
            ModelRegistryEntry(
                provider=ProviderName.GEMINI,
                model_id="gemini-2.0-flash",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.MULTIMODAL_INPUT,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.JSON_OUTPUT,
                ],
                modalities=[Modality.TEXT, Modality.IMAGE, Modality.AUDIO, Modality.MULTIMODAL],
                context_window=1000000,
                pricing_input_per_1m=0.10,
                pricing_output_per_1m=0.40,
                latency_ms=800,
                availability=True,
                fallback_models=["gemini-1.5-flash"],
                base_url=None,
                api_key_env="GEMINI_API_KEY",
            ),
            ModelRegistryEntry(
                provider=ProviderName.GEMINI,
                model_id="gemini-1.5-pro",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.MULTIMODAL_INPUT,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.JSON_OUTPUT,
                    ModelCapability.LONG_CONTEXT,
                ],
                modalities=[Modality.TEXT, Modality.IMAGE, Modality.AUDIO, Modality.MULTIMODAL],
                context_window=2000000,
                pricing_input_per_1m=1.25,
                pricing_output_per_1m=5.0,
                latency_ms=1500,
                availability=True,
                fallback_models=["gemini-2.0-flash"],
                base_url=None,
                api_key_env="GEMINI_API_KEY",
            ),
            ModelRegistryEntry(
                provider=ProviderName.GEMINI,
                model_id="imagen-3",
                capabilities=[ModelCapability.IMAGE_GENERATION],
                modalities=[Modality.IMAGE],
                context_window=1024,
                pricing_input_per_1m=None,
                pricing_output_per_1m=None,
                latency_ms=6000,
                availability=True,
                fallback_models=[],
                base_url=None,
                api_key_env="GEMINI_API_KEY",
            ),
            # Gemini does NOT support native video or audio generation; only
            # text/image/audio input (multimodal) and image generation via Imagen.
            # ---------------- Meta Llama ----------------
            ModelRegistryEntry(
                provider=ProviderName.LLAMA,
                model_id="llama-3.1-405b",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.JSON_OUTPUT,
                ],
                modalities=[Modality.TEXT],
                context_window=128000,
                pricing_input_per_1m=1.00,
                pricing_output_per_1m=3.00,
                latency_ms=2000,
                availability=True,
                fallback_models=["llama-3.1-70b"],
                base_url=None,
                api_key_env="LLAMA_API_KEY",
            ),
            # Llama (via API providers) supports text/code/reasoning only.
            # No native image/video/audio generation.
            # ---------------- Mistral ----------------
            ModelRegistryEntry(
                provider=ProviderName.MISTRAL,
                model_id="mistral-large-2",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.JSON_OUTPUT,
                ],
                modalities=[Modality.TEXT],
                context_window=128000,
                pricing_input_per_1m=1.00,
                pricing_output_per_1m=3.00,
                latency_ms=1500,
                availability=True,
                fallback_models=["mistral-small-latest"],
                base_url=None,
                api_key_env="MISTRAL_API_KEY",
            ),
            ModelRegistryEntry(
                provider=ProviderName.MISTRAL,
                model_id="mistral-small-latest",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                ],
                modalities=[Modality.TEXT],
                context_window=128000,
                pricing_input_per_1m=0.20,
                pricing_output_per_1m=0.60,
                latency_ms=800,
                availability=True,
                fallback_models=[],
                base_url=None,
                api_key_env="MISTRAL_API_KEY",
            ),
            # ---------------- DeepSeek ----------------
            ModelRegistryEntry(
                provider=ProviderName.DEEPSEEK,
                model_id="deepseek-chat",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.JSON_OUTPUT,
                ],
                modalities=[Modality.TEXT],
                context_window=128000,
                pricing_input_per_1m=0.27,
                pricing_output_per_1m=1.10,
                latency_ms=1000,
                availability=True,
                fallback_models=["deepseek-reasoner"],
                base_url=None,
                api_key_env="DEEPSEEK_API_KEY",
            ),
            ModelRegistryEntry(
                provider=ProviderName.DEEPSEEK,
                model_id="deepseek-reasoner",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.JSON_OUTPUT,
                    ModelCapability.LONG_CONTEXT,
                ],
                modalities=[Modality.TEXT],
                context_window=128000,
                pricing_input_per_1m=0.55,
                pricing_output_per_1m=2.19,
                latency_ms=3000,
                availability=True,
                fallback_models=["deepseek-chat"],
                base_url=None,
                api_key_env="DEEPSEEK_API_KEY",
            ),
            # DeepSeek supports text/code/reasoning only (no media generation).
            # ---------------- Qwen ----------------
            ModelRegistryEntry(
                provider=ProviderName.QWEN,
                model_id="qwen2.5-72b-instruct",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.JSON_OUTPUT,
                ],
                modalities=[Modality.TEXT],
                context_window=131000,
                pricing_input_per_1m=0.40,
                pricing_output_per_1m=1.20,
                latency_ms=1200,
                availability=True,
                fallback_models=["qwen-turbo"],
                base_url=None,
                api_key_env="QWEN_API_KEY",
            ),
            ModelRegistryEntry(
                provider=ProviderName.QWEN,
                model_id="qwen-vl-max",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.MULTIMODAL_INPUT,
                ],
                modalities=[Modality.TEXT, Modality.IMAGE, Modality.MULTIMODAL],
                context_window=32000,
                pricing_input_per_1m=0.20,
                pricing_output_per_1m=0.60,
                latency_ms=1500,
                availability=True,
                fallback_models=["qwen2.5-72b-instruct"],
                base_url=None,
                api_key_env="QWEN_API_KEY",
            ),
            ModelRegistryEntry(
                provider=ProviderName.QWEN,
                model_id="qwen-audio",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.SPEECH_TO_TEXT,
                ],
                modalities=[Modality.AUDIO, Modality.TEXT],
                context_window=32000,
                pricing_input_per_1m=0.20,
                pricing_output_per_1m=0.60,
                latency_ms=2000,
                availability=True,
                fallback_models=["qwen2.5-72b-instruct"],
                base_url=None,
                api_key_env="QWEN_API_KEY",
            ),
            # Qwen supports text/code/image-input/audio but not native image or
            # video GENERATION.
            # ---------------- Local models (OpenAI-compatible) ----------------
            ModelRegistryEntry(
                provider=ProviderName.LOCAL,
                model_id="local-llm",
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.JSON_OUTPUT,
                ],
                modalities=[Modality.TEXT],
                context_window=32768,
                pricing_input_per_1m=None,
                pricing_output_per_1m=None,
                latency_ms=500,
                availability=True,
                fallback_models=[],
                base_url=None,  # set via env LOCAL_LLM_BASE_URL
                api_key_env="LOCAL_LLM_API_KEY",
            ),
        ]
        conn = None
        try:
            conn = self._connect()
            self._ensure_schema(conn)
            with conn.cursor() as cur:
                for entry in entries:
                    cur.execute(
                        """
                        INSERT INTO model_registry
                            (provider, model_id, name, capabilities, modalities,
                             context_window, pricing_input_per_1m, pricing_output_per_1m,
                             latency_ms, availability, fallback_models, base_url,
                             api_key_env, enabled, metadata, updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                        ON CONFLICT (provider, model_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            capabilities = EXCLUDED.capabilities,
                            modalities = EXCLUDED.modalities,
                            context_window = EXCLUDED.context_window,
                            pricing_input_per_1m = EXCLUDED.pricing_input_per_1m,
                            pricing_output_per_1m = EXCLUDED.pricing_output_per_1m,
                            latency_ms = EXCLUDED.latency_ms,
                            availability = EXCLUDED.availability,
                            fallback_models = EXCLUDED.fallback_models,
                            base_url = EXCLUDED.base_url,
                            api_key_env = EXCLUDED.api_key_env,
                            enabled = EXCLUDED.enabled,
                            metadata = EXCLUDED.metadata,
                            updated_at = NOW()
                        """,
                        (
                            entry.provider.value,
                            entry.model_id,
                            entry.name,
                            [c.value for c in entry.capabilities],
                            [m.value for m in entry.modalities],
                            entry.context_window,
                            entry.pricing_input_per_1m,
                            entry.pricing_output_per_1m,
                            entry.latency_ms,
                            entry.availability,
                            entry.fallback_models,
                            entry.base_url,
                            entry.api_key_env,
                            entry.enabled,
                            entry.metadata,
                        ),
                    )
            conn.commit()
        except Exception:  # noqa: BLE001
            # PostgreSQL unavailable — keep entries in memory only.
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn:
                self._release(conn)
        # Populate the in-memory cache from the seeded entries so the system
        # works even when PostgreSQL is unavailable.
        self._cache = {f"{e.provider.value}:{e.model_id}": e for e in entries}
        self._cache_loaded_at = time.time()

    # ------------------------------------------------------------------ lookups

    def list_models(
        self,
        provider: Optional[ProviderName] = None,
        capability: Optional[ModelCapability] = None,
        modality: Optional[Modality] = None,
        enabled_only: bool = True,
    ) -> List[ModelRegistryEntry]:
        self._ensure_loaded()
        results = []
        for entry in self._cache.values():
            if provider and entry.provider != provider:
                continue
            if capability and capability not in entry.capabilities:
                continue
            if modality and modality not in entry.modalities:
                continue
            results.append(entry)
        return results

    def get(self, provider: ProviderName, model_id: str) -> Optional[ModelRegistryEntry]:
        self._ensure_loaded()
        return self._cache.get(f"{provider.value}:{model_id}")

    def get_capable_models(
        self,
        capability: ModelCapability,
        modality: Optional[Modality] = None,
        provider: Optional[ProviderName] = None,
    ) -> List[ModelRegistryEntry]:
        """Models that support a given capability (and optionally modality/provider)."""
        self._ensure_loaded()
        out = []
        for entry in self._cache.values():
            if capability not in entry.capabilities:
                continue
            if provider and entry.provider != provider:
                continue
            if modality and modality not in entry.modalities:
                continue
            out.append(entry)
        return out

    def is_capable(self, provider: ProviderName, model_id: str, capability: ModelCapability) -> bool:
        entry = self.get(provider, model_id)
        return bool(entry and capability in entry.capabilities)

    def supports_modality(self, provider: ProviderName, model_id: str, modality: Modality) -> bool:
        entry = self.get(provider, model_id)
        return bool(entry and modality in entry.modalities)

    def get_fallbacks(self, entry: ModelRegistryEntry) -> List[ModelRegistryEntry]:
        out = []
        for fid in entry.fallback_models:
            # fallback_models stores model_id strings; look up same provider
            fb = self.get(entry.provider, fid)
            if fb:
                out.append(fb)
        return out


_registry: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


def registry_entry_from_db_row(row: dict) -> ModelRegistryEntry:
    return _row_to_entry(row)
