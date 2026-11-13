# ---------------------------------------------------------------
# Leader–Sub-Agent Multi-LLM Orchestration System — Docker image
# ---------------------------------------------------------------
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for psycopg2 / cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY orchestration/pyproject.toml orchestration/requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Copy application code
COPY orchestration/src ./src
COPY orchestration/.env.example .env.example

# Alembic migrations for the model registry
COPY orchestration/alembic ./alembic

EXPOSE 8000

# Run migrations then start the API
CMD ["sh", "-c", "alembic upgrade head && uvicorn orchestration.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
