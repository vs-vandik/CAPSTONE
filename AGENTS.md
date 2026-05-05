# AGENTS.md

Early-stage capstone: an "AI Investment Discourse" app where AI agents
(experts moderated by `Plato`, critiqued by `Aporia`) hold Socratic
debates. Backend is partially scaffolded; frontend is an empty skeleton.

## Layout

- `backend/` — FastAPI app, LangChain + LlamaIndex + Chroma, edge-tts.
  - `app/main.py` — FastAPI entrypoint, mounts `app/api/routes.py` at `/api/v1`.
  - `app/agents/plato.py` — template-based facilitator (no LLM yet).
  - `app/agents/aporia.py` — debate-critique system (algorithmic mode works;
    `deep`/LLM mode is a stub).
  - `app/agents/experts/scraper.py` — expert-data scraper; HTTP calls are
    placeholders (`_scrape_query` returns fake data).
  - `app/core/config.py` — `pydantic-settings` reading `.env`.
  - `app/knowledge/` — empty package, intended for RAG / Chroma.
- `frontend/` — only empty dirs (`src/{components,services,stores,views}`).
  No `package.json` yet. CORS + `.env.example` imply Vite on `:5173`.

There is no monorepo tooling, no tests, no lint/format/typecheck config,
no CI, and no lockfiles. `README.md` is one line.

## Run / dev

All backend commands assume **cwd = `backend/`** because imports are
absolute (`from app.api ...`) and `Settings` reads `./.env`.

```powershell
# from backend/
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then fill in keys
uvicorn app.main:app --reload --port 8000
```

- API base: `http://localhost:8000/api/v1`, health: `/health` (also at root).
- No test runner is configured. Don't invent `pytest` commands; add the
  dep + config first if tests are needed.

## Conventions / gotchas

- **Settings vs hardcoded CORS**: `app/main.py` hardcodes
  `allow_origins=["http://localhost:5173", "http://localhost:3000"]` and
  ignores `settings.CORS_ORIGINS`. Update both if changing origins.
- **Pinned deps, old stack**: `requirements.txt` pins exact versions
  (e.g. `langchain==0.1.4`, `llama-index==0.10.12`, `pydantic==2.5.3`).
  Don't casually upgrade — these versions are mutually compatible and
  span breaking-change boundaries.
- **Most routes are placeholders**: `/personas*` and `/discourse/*/next`
  return `"not yet implemented"`. Discourse sessions live in an in-memory
  `dict` (`routes.py:11`) — restarts wipe state.
- **Scraper is a stub**: `ExpertScraper._scrape_query` returns fabricated
  `ScrapedData`. Treat it as a structural placeholder, not a working
  integration with SerpAPI / YouTube / NewsAPI.
- **Plato has no LLM**: `plato.py` is pure templates returning dicts; do
  not assume it calls a model.
- **`AGENT_CONFIG` in `core/config.py`** is a separate constant from
  `settings`; the `Settings` instance does not feed it.

## When extending

- New routes go in `app/api/routes.py` (single router, prefix `/api/v1`).
- New agents go in `app/agents/`; experts in `app/agents/experts/`.
- Persisted scraper data is written under `./data/<expert_slug>/` (cwd
  = `backend/`); no `.gitignore` exists, so be deliberate about checking
  generated data into git.
- Frontend: no scaffolding yet — confirm framework choice with the user
  before generating one (CORS/env hints suggest Vue + Vite).
