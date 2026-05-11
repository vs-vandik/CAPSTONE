# syntax=docker/dockerfile:1
#
# Backend container for Fly.io.
#
# Design choices:
# - python:3.12-slim base. Slim avoids the ~700 MB hit of the full image
#   while still giving us a working apt for the one or two build-time
#   wheels that need a C compiler.
# - We install requirements.runtime.txt rather than requirements.txt:
#   langchain / llama-index / their dragged-in transitive deps are not
#   imported anywhere live (see AGENTS.md), and dropping them shaves
#   ~150 MB and ~30 s off the build.
# - Single uvicorn worker. The app keeps `discourse_sessions` in
#   process memory (see app/api/routes.py); multiple workers would
#   shard sessions across processes and break the next-turn flow.
# - We copy `app/` and `data/` only. `scripts/`, `.venv/`, `raw/`
#   subdirs, and any local .env are excluded by .dockerignore.

FROM python:3.12-slim AS base

# Build-essential is needed for any pure-Python wheels that miss a
# manylinux build; safe to keep until we know we don't need it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first so this layer is cached across code changes.
COPY requirements.runtime.txt .
RUN pip install --no-cache-dir -r requirements.runtime.txt

# App code + persona data.
COPY app ./app
COPY data ./data

# Fly injects PORT on boot; default to 8000 for local docker runs.
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
