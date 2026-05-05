# AGENTS.md

Capstone demo: "AI Investment Discourse" — six AI personas (Buffett, Fink,
Musk, Marx, Caesar, Kardashian) debate finance topics under Plato's
moderation, with Aporia critiquing the result. Backend is working
end-to-end; frontend is still an empty skeleton.

## Layout

- `backend/` — FastAPI + OpenAI, NumPy-based retrieval. Run from this dir.
  - `app/main.py` — FastAPI entrypoint, mounts `app/api/routes.py` at `/api/v1`.
  - `app/api/routes.py` — `/personas`, `/personas/{id}`, `/discourse/start`,
    `/discourse/{id}/next`, `/discourse/{id}`, `/discourse/{id}/aporia`.
  - `app/agents/discourse.py` — the real debate loop. One turn per
    `/next` call. Plato opens, experts speak round-robin with Plato
    transitions in between, Plato closes after `max_turns` expert turns.
  - `app/agents/plato.py` — template-based, no LLM. Pre-existing.
  - `app/agents/aporia.py` — algorithmic critique (regex over history).
  - `app/agents/experts/scraper.py` — old placeholder, **not used at
    runtime**. Real ingestion lives in `scripts/ingest/`.
  - `app/core/personas.py` — six persona definitions (id, voice, refusals,
    seed_quotes, `rag_tier ∈ {full, curated}`).
  - `app/core/llm.py` — single `generate(system, messages)` around OpenAI.
  - `app/knowledge/news.py` — Tavily search, optional, fails open.
  - `app/knowledge/store.py` — `get_retriever(persona)` returning either a
    `FullCorpusRetriever` (NumPy cosine over a saved `embeddings.npy`) or
    a `SeedQuoteRetriever` (in-memory cosine over `persona.seed_quotes`).
- `backend/scripts/` — out-of-band one-shots, run manually:
  - `ingest/buffett.py` — scrapes Berkshire shareholder letters
    (1977–2001) into `data/buffett/chunks.jsonl`.
  - `ingest/_chunking.py` — paragraph-aware chunker, reusable.
  - `build_index.py` — embeds a chunks.jsonl into `embeddings.npy`.
- `backend/data/<expert>/` — `chunks.jsonl` (committed) + `raw/` and
  `embeddings.npy` (gitignored).
- `frontend/` — still just empty `src/{components,services,stores,views}`.
  No package.json. CORS hint: Vite on `:5173`.

No tests, no lint/format/typecheck, no CI, no lockfiles.

## Run / dev

```powershell
# from backend/
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env       # add your OPENAI_API_KEY
python -m scripts.ingest.buffett  # ~1 minute, hits berkshirehathaway.com
python -m scripts.build_index buffett   # ~$0.024 in OpenAI embeddings
uvicorn app.main:app --reload --port 8000
```

The build_index step is optional — without it, `full`-tier personas fall
back to seed_quotes and the demo still runs. The fallback is logged.

## Conventions / gotchas

- **cwd matters**: imports are absolute (`from app...`), `Settings` reads
  `./.env`, ingestion scripts resolve `data/` relative to the backend dir.
  Always run from `backend/`.
- **Hardcoded CORS in `main.py`** ignores `settings.CORS_ORIGINS`. Update
  both if changing origins.
- **Pinned deps**: `requirements.txt` pins exact versions because
  `langchain==0.1.4` + `llama-index==0.10.12` + `pydantic==2.5.3` are
  mutually compatible across known breaking changes. Don't casually
  upgrade. Note: `langchain` and `llama-index` are listed but **not
  imported** anywhere — kept for now in case they're needed later, but
  safe to drop.
- **No Chroma**: `requirements.txt` does NOT include `chromadb`. We ship
  retrieval as `numpy.dot` over a saved `.npy` — no C build deps, deploys
  the same on Windows / Railway / Fly. Don't reintroduce Chroma without
  a real reason; on Windows + Python 3.12 it requires MSVC to build
  `chroma-hnswlib`.
- **Brotli is mandatory for ingestion**: `berkshirehathaway.com` is
  fronted by Sucuri and serves Brotli regardless of `Accept-Encoding`.
  `requirements.txt` includes `brotli==1.1.0` for that reason.
- **In-memory sessions**: `routes.py:11` `discourse_sessions: Dict`.
  Restarts wipe everything. Cached on the session: `news` (Tavily
  results) and `quotes_by_persona` (top-k retrieval per persona) — both
  populated lazily.
- **Plato has no LLM**: pure templates. Don't assume model calls.
- **Plato's `create_context` has a bug**: it indexes `speakers` by
  `turn_number` and dies once `turn_number > len(speakers)`. The
  discourse loop avoids it by building `TurnContext` directly. If you
  use `create_context` for a new caller, fix it first.
- **Kardashian seed_quotes are paraphrases, not verbatim**, flagged with
  a comment in `personas.py`. Replace before any non-demo use.
- **`AGENT_CONFIG` in `core/config.py`** is a separate constant from
  `settings`; the `Settings` instance does not feed it.
- **Old `app/agents/experts/scraper.py`** is the original placeholder
  scaffolding. Not imported by anything live. Real ingestion is in
  `backend/scripts/ingest/`. Delete or rewrite when you next touch it.

## Adding a new full-tier expert

1. Add a `Persona` to `app/core/personas.py` with `rag_tier="full"`.
2. Write `backend/scripts/ingest/<expert>.py` that produces
   `backend/data/<expert>/chunks.jsonl` with records shaped
   `{id, expert_id, source_url, source_title, text, ...}`.
3. `python -m scripts.ingest.<expert>` then
   `python -m scripts.build_index <expert>`.
4. Add a smoke test that hits `/discourse/start` with the new id.

## Frontend

Not built. Confirm framework choice (Vue 3 + Vite is implied by existing
empty dirs and CORS) before generating one.
