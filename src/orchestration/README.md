# Leader–Sub-Agent Multi-LLM Model Orchestration System

Production-ready Python/FastAPI orchestration system in which the **Leader Agent
holds exclusive authority over all Sub-Agent model selection and assignment**.
Sub-Agents cannot independently select, replace, or switch their assigned models.

```
User Request → Leader Agent → Task Analysis → Capability & Model Router →
Central Model Registry → Specialized Sub-Agents → Leader Agent → Quality Control → Final Response
```

## Tech stack

Python · FastAPI · LangGraph · LiteLLM · PostgreSQL · Redis · Qdrant · Docker · OpenTelemetry

## Directory structure

```
orchestration/
├── README.md                      # this file
├── .env.example                   # environment variable template (copy to .env)
├── requirements.txt               # Python dependencies
├── pyproject.toml                 # project metadata
├── Dockerfile                     # container image
├── docker-compose.yml             # Postgres + Redis + Qdrant + API + OTel
├── alembic.ini                    # Alembic config
├── alembic/env.py                 # Alembic environment
├── alembic/versions/0001_initial_schema.py
├── otel-collector-config.yaml     # OpenTelemetry collector config
├── src/orchestration/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # settings from env vars (API keys never hardcoded)
│   │   ├── types.py               # shared types (tasks, assignments, results, audit)
│   │   ├── security.py            # permissions, tool validation, sandbox, audit
│   │   └── observability.py       # OpenTelemetry tracing + metrics
│   ├── registry/
│   │   ├── __init__.py
│   │   └── registry.py            # Central Model Registry (PostgreSQL + cache)
│   ├── router/
│   │   ├── __init__.py
│   │   └── router.py              # Dynamic Model Router (advisory only)
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py                # adapter interface + registry
│   │   └── litellm_adapter.py     # LiteLLM-backed adapter for all providers
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py          # Sub-Agent base (no model authority)
│   │   ├── leader.py              # Leader Agent (exclusive model authority)
│   │   └── sub_agents.py          # 7 specialized Sub-Agents
│   ├── orchestration/
│   │   ├── __init__.py
│   │   └── engine.py              # LangGraph orchestration engine
│   ├── quality/
│   │   ├── __init__.py
│   │   └── quality.py             # Quality control + fallback
│   └── api/
│       ├── __init__.py
│       └── app.py                 # FastAPI endpoints
└── src/tests/
    ├── conftest.py
    ├── test_registry.py
    ├── test_router.py
    ├── test_leader_authority.py
    ├── test_fallback.py
    └── test_integration.py
```

## Quick start

```bash
cd orchestration
cp .env.example .env
# Edit .env and add your API keys (only for providers you use)
pip install -r requirements.txt

# Run with PostgreSQL available (recommended)
alembic upgrade head
uvicorn orchestration.api.app:app --host 0.0.0.0 --port 8000

# Or with Docker (bring up Postgres, Redis, Qdrant and the API)
docker compose up --build
```

### Without a database (dev/demo)

`seed_defaults()` degrades gracefully when PostgreSQL is unreachable: the
registry keeps its default model metadata in memory and the system still routes
and assigns models. No real provider calls are made unless you set API keys.

## Environment variables

See `.env.example`. The most important:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`, `QWEN_API_KEY`, `LLAMA_API_KEY`, `LOCAL_LLM_API_KEY` | Provider API keys (env only, never hardcoded) |
| `DATABASE_URL` | PostgreSQL for the model registry + audit log |
| `REDIS_URL` | Redis cache / shared task context |
| `QDRANT_HOST` / `QDRANT_PORT` | Qdrant for research embeddings |
| `API_AUTH_TOKEN` | Bearer token protecting the API |
| `ENCRYPTION_KEY` | Key for encrypting stored secrets |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry trace endpoint |
| `QUALITY_ENABLED`, `QUALITY_MIN_SCORE` | Quality control thresholds |

## API endpoints

All mutating/read endpoints require `Authorization: Bearer <API_AUTH_TOKEN>`
(when `API_AUTH_TOKEN` is set to a non-default value).

- `GET /health` — health check
- `POST /orchestrate` — full Leader orchestration (`user_request`, `context`, `sequential`)
- `POST /tasks` — analyze + decompose a request into tasks
- `POST /route` — router recommendation (advisory; Leader decides)
- `POST /assign` — Leader issues a model assignment to a sub-agent
- `POST /reassign` — Leader reassigns a model (fallback/switch)
- `POST /execute` — execute a sub-agent task with its assigned model
- `GET /registry` — list registry models (filter by provider/capability/modality)
- `GET /registry/{provider}/{model_id}` — get a single model entry
- `POST /registry/seed` — seed default model metadata
- `GET /quality/summary` — quality control summary
- `GET /audit` — audit log
- `GET /agents` — leader + registered sub-agents and their assignments

## Core design guarantees

1. **Leader-exclusive model authority.** `LeaderAgent.assign_model()` and
   `reassign_model()` are the only places a `ModelAssignment` is created or
   changed. `SubAgent.set_assignment()` rejects any caller that is not the
   Leader, and `SubAgent._enforce_model_authority()` raises `PermissionError`
   if a sub-agent attempts to select/switch its own model. Every rejected
   attempt is written to the audit log.
2. **Sub-Agents use only their assigned model.** `SubAgent.execute()` calls the
   provider adapter with exactly `assignment.provider` / `assignment.model_id`
   bound by the Leader. There is no sub-agent method to choose a model.
3. **Router is advisory.** `ModelRouter.route()` recommends a model + fallback
   chain but never assigns. The Leader converts the recommendation into an
   authoritative `ModelAssignment`.
4. **Never assume every provider supports every modality.** The registry stores
   per-model capabilities and modalities. E.g. DALL-E 3 advertises image
   generation only (no text/code/video/audio generation); Anthropic advertises
   text + image *input* (multimodal) but no native media generation; Gemini
   advertises no native video generation. Unsupported capabilities are simply
   absent from the model entry.

## Unsupported provider capabilities (documented)

| Provider | Not supported natively |
|---|---|
| Anthropic | Image/video/audio **generation** (text + image input only) |
| Google Gemini | Native **video** and **audio** generation (text/image/audio *input* + image gen via Imagen) |
| Meta Llama | Image/video/audio generation (text/code/reasoning only) |
| Mistral | Image/video/audio generation (text/code/reasoning only) |
| DeepSeek | Image/video/audio generation (text/code/reasoning only) |
| Qwen | Native image/video **generation** (image/audio *input* supported) |
| Local models | Depends on the local endpoint; defaults to text/code/reasoning |

When a requested task has no capable model, the router returns
`model_id = "unsupported"` with a clear rationale and the Leader surfaces this
rather than silently picking an incapable model.

## Testing

```bash
cd orchestration
pip install -r requirements.txt   # includes pytest
python -m pytest src/tests/ -q
```

24 unit + integration tests cover: registry capability/modality filtering,
router recommendations and provider blocking, Leader-exclusive assignment
authority (sub-agent switch attempts rejected), model fallback on error, and
full orchestration flow with stubbed providers.

## Security notes

- API keys are read from environment variables at startup and held in memory
  only. Never commit `.env`.
- `SecurityManager` validates tool calls (blocks path traversal and shell
  metacharacters) and gates sandboxed code execution.
- All model assignments, quality reviews, and errors are recorded in an
  immutable audit log (`SecurityManager.make_audit` + PostgreSQL audit table).
