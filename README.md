# Agi Super Harness (baton)

A desktop agent harness: a lead agent that plans, uses tools, and delegates work to parallel sub-agents across workspaces.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](package.json)
[![Node.js](https://img.shields.io/badge/node-%3E%3D22.12.0-green.svg)](package.json)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue.svg)](src/orchestration/pyproject.toml)
[![Electron](https://img.shields.io/badge/electron-45-blue.svg)](package.json)
[![TypeScript](https://img.shields.io/badge/typescript-strict-blue.svg)](tsconfig.json)

## Description

**Agi Super Harness** (repo: `baton`) is a desktop agent orchestration system built with Electron, React, TypeScript, Python, FastAPI, and LangGraph. It provides a lead-agent architecture in which a lead agent plans work, uses tools, and delegates tasks to parallel sub-agents across isolated workspaces.

The system is split into three layers:

* **Desktop app (Electron + React + TypeScript)** — the user-facing frontend and the Node.js backend core that manages settings, secrets, workspaces, threads, and provider connections.
* **Orchestration engine (Python + FastAPI + LangGraph)** — a Leader–Sub-Agent multi-LLM orchestration system in which the Leader Agent holds exclusive authority over all model selection and assignment. Sub-Agents cannot independently select or switch their models; the dynamic model router only advises.
* **Build & packaging (Vite + esbuild + electron-builder)** — produces distributable desktop installers for Windows (NSIS), Linux (AppImage, deb), and macOS (DMG, zip).

## Features

* **Leader–Sub-Agent orchestration** — a lead agent plans, executes, and delegates work to parallel sub-agents across workspaces.
* **Exclusive model authority** — only the Leader Agent can create or change model assignments; sub-agents use only their assigned model and cannot switch it themselves.
* **Dynamic model routing** — a model router recommends models and fallback chains (advisory only); the Leader converts recommendations into authoritative assignments.
* **Model registry** — central registry of provider models with per-model capabilities and modalities (OpenAI, Anthropic, Gemini, Mistral, DeepSeek, Qwen, Llama, local models, and more via LiteLLM adapters).
* **Provider adapters** — pluggable LLM provider adapters with a LiteLLM-backed implementation.
* **Desktop application** — Electron shell with a React + TypeScript frontend (Vite), Zustand state management, and Geist/Geist Mono typography.
* **Settings & secrets store** — persistent settings, provider configuration, and an obfuscating secrets codec for API keys.
* **Workspaces & threads** — workspace management with thread send/stop/retry and conversation history.
* **Quality control** — quality scoring with fallback on low-quality results.
* **REST API** — FastAPI endpoints for orchestration, routing, assignment, registry, quality, audit, and agent management.
* **Cross-platform packaging** — Windows NSIS, Linux AppImage and deb, macOS DMG and zip via electron-builder.
* **Tested** — Python test suite covering the orchestration engine, registry, router, leader authority, adapters, quality, and API endpoints.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, Zustand, Geist / Geist Mono |
| Desktop shell | Electron 45, esbuild, electron-builder |
| Node backend | Node.js (>=22.12.0), TypeScript, @lydell/node-pty |
| Orchestration | Python 3.10+, FastAPI, LangGraph, LiteLLM, Uvicorn |
| Data & caching | PostgreSQL, Redis, Qdrant |
| Observability | OpenTelemetry |
| DevOps | Docker, Docker Compose, Alembic (migrations) |
| Packaging | electron-builder — NSIS (Windows), AppImage & deb (Linux), DMG & zip (macOS) |
| Testing | pytest (Python), node --test (Node) |

## Project Structure

```
.
├── README.md                      # this file
├── index.html                     # Vite entry HTML
├── package.json                   # Node project metadata + scripts
├── tsconfig.json                  # TypeScript config
├── vite.config.mts                # Vite config
├── scripts/                       # Build and dev helper scripts
│   ├── build-node.mjs
│   ├── dev.mjs
│   └── export-icons.mjs
├── assets/                        # App icons and branding
│   └── icons/
│       └── icon.svg
├── release/                       # Packaged release artifacts
│   ├── Agi Super Harness-0.1.0.AppImage
│   ├── agi-super-harness_0.1.0_amd64.deb
│   ├── agi-super-harness-0.1.0-x64.nsis.7z
│   └── win-unpacked.zip
├── src/
│   ├── core/                      # Node.js backend core
│   │   ├── agent/
│   │   │   ├── permissions.ts
│   │   │   ├── prompts.ts
│   │   │   └── runner.ts          # AgentRunner (thread send/stop/retry)
│   │   ├── llm/
│   │   │   ├── demo.ts
│   │   │   ├── index.ts
│   │   │   └── types.ts
│   │   ├── secrets/
│   │   ├── settings/
│   │   ├── tools/
│   │   │   ├── index.ts
│   │   │   ├── meta.ts
│   │   │   ├── orchestrate.ts
│   │   │   └── types.ts
│   │   ├── index.ts               # Core class (settings, workspaces, threads, providers)
│   │   ├── mcp.ts
│   │   ├── secrets.ts             # ObfuscatingCodec
│   │   ├── settings.ts            # SettingsStore
│   │   ├── store.ts
│   │   ├── threads.ts             # ThreadStore
│   │   ├── util.ts
│   │   └── workspaces.ts          # WorkspaceStore
│   ├── electron/                  # Electron main + preload
│   │   ├── main.ts
│   │   └── preload.ts
│   ├── orchestration/             # Python orchestration engine
│   │   ├── pyproject.toml
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   ├── docker-compose.yml
│   │   ├── alembic.ini
│   │   ├── alembic/env.py
│   │   ├── alembic/versions/
│   │   ├── otel-collector-config.yaml
│   │   ├── src/orchestration/
│   │   │   ├── core/              # config, security, observability, types
│   │   │   ├── registry/          # Central Model Registry
│   │   │   ├── router/            # Dynamic Model Router (advisory)
│   │   │   ├── adapters/          # Provider adapters (LiteLLM-backed)
│   │   │   ├── agents/            # Leader Agent + Sub-Agents
│   │   │   ├── orchestration/     # LangGraph engine
│   │   │   ├── quality/           # Quality control + fallback
│   │   │   └── api/               # FastAPI endpoints
│   │   └── src/tests/             # Python test suite (pytest)
│   ├── renderer/                  # React frontend (Vite)
│   │   ├── components/
│   │   │   ├── App.tsx
│   │   │   ├── common.tsx
│   │   │   ├── RefactorPanel.tsx
│   │   │   ├── Settings.tsx
│   │   │   ├── SettingsParts.tsx
│   │   │   ├── TaskBoard.tsx
│   │   │   └── ui.tsx
│   │   ├── lib/format.ts
│   │   ├── store/                 # Zustand stores (appearance, index)
│   │   ├── api.ts
│   │   ├── index.css
│   │   └── main.tsx
│   ├── server/
│   └── shared/                    # Shared types, defaults, branding
│       ├── brand.ts
│       ├── defaults.ts
│       └── types.ts
└── tests/
```

## Installation

### Prerequisites

* **Node.js** >= 22.12.0
* **Python** >= 3.10 (for the orchestration engine)
* **npm** (bundled with Node)
* **Docker** (optional, for running the orchestration stack with PostgreSQL, Redis, and Qdrant)

### Clone

```bash
git clone https://github.com/agi-super-harness/desktop.git
cd desktop   # repo: baton
```

### Install Node dependencies

```bash
npm install
```

### Install Python dependencies (orchestration)

```bash
cd src/orchestration
cp .env.example .env
# Edit .env and add your API keys (only for providers you use)
pip install -r requirements.txt
cd ../..
```

### Build

```bash
npm run build
```

This runs the Vite frontend build and the esbuild Node backend build, outputting to `dist/`.

## Usage

### Development mode

Start the Electron app with the Vite dev server:

```bash
npm run dev
```

Web-only dev mode (no Electron):

```bash
npm run dev:web
```

### Run the desktop app

```bash
npm start
```

### Typecheck

```bash
npm run typecheck
```

### Package for distribution

```bash
npm run dist
```

Produces platform installers in `out/` / `release/`:

* macOS: DMG, zip
* Windows: NSIS installer (+ 7z)
* Linux: AppImage, deb

### Run the orchestration API (Python)

```bash
cd src/orchestration
cp .env.example .env
pip install -r requirements.txt

# Run with PostgreSQL available (recommended)
alembic upgrade head
uvicorn orchestration.api.app:app --host 0.0.0.0 --port 8000

# Or with Docker (Postgres + Redis + Qdrant + API + OTel)
docker compose up --build
```

### Run tests

**Node tests:**

```bash
npm test
```

**Python tests (orchestration):**

```bash
cd src/orchestration
pip install -r requirements.txt   # includes pytest
python -m pytest src/tests/ -q
```

## Contributing

Contributions are welcome. Please open an issue or pull request on GitHub.

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Make your changes and add or update tests as needed.
4. Run the test suites and typecheck (`npm test`, `npm run typecheck`, `python -m pytest`).
5. Commit your changes (`git commit -m "feat: your feature"`).
6. Push to your branch (`git push origin feature/your-feature`).
7. Open a pull request.

### Code style

* TypeScript: strict mode, run `tsc --noEmit` before committing.
* Python: follow the existing module layout under `src/orchestration/src/orchestration/`; keep provider adapters pluggable via the adapter base class.
* API keys: never commit `.env`; keys are read from environment variables only.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
