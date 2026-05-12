# AGENTS.md

Capstone demo: "AI Investment Discourse" — six AI personas (Buffett, Fink,
Musk, Thiel, Marx, Caesar) debate finance topics under Plato's
moderation, with Aporia critiquing the result. Backend is working
end-to-end via DigitalOcean Serverless Inference; frontend is still an
empty skeleton.

## Layout

- `backend/` — FastAPI + OpenAI SDK pointed at DigitalOcean Inference,
  NumPy-based retrieval. Run from this dir.
  - `app/main.py` — FastAPI entrypoint, mounts `app/api/routes.py` at `/api/v1`.
  - `app/api/routes.py` — `/personas`, `/personas/{id}`, `/discourse/start`,
    `/discourse/{id}/next`, `/discourse/{id}`, `/discourse/{id}/aporia`.
  - `app/agents/discourse.py` — the real debate loop. One turn per
    `/next` call. Plato opens, experts speak round-robin with Plato
    transitions in between, Plato closes after `max_turns` expert turns.
  - `app/agents/plato.py` — template-based, no LLM. Pre-existing.
  - `app/agents/aporia.py` — post-debate critique. For each expert,
    one LLM call recovers the argument's structure (core claim,
    unstated assumptions, scope limits, named clashes); then one
    synthesis call identifies real cross-cutting disagreements and
    open questions. N+1 LLM calls per click. Returns a flat
    `findings[]` list under Plato's voicing, plus structured
    `experts[]` / `disagreements[]` / `open_questions[]` for richer
    rendering. Degrades to a content-only message (never 500s) if
    the LLM is unavailable or returns unparseable JSON.
  - `app/agents/experts/scraper.py` — old placeholder, **not used at
    runtime**. Real ingestion lives in `scripts/ingest/`.
  - `app/core/personas.py` — six persona definitions (id, voice, refusals,
    seed_quotes, `rag_tier ∈ {full, curated}`).
  - `app/core/llm.py` — single `generate(system, messages)` around the
    OpenAI SDK pointed at `LLM_BASE_URL` (DO Inference by default).
  - `app/knowledge/news.py` — Tavily search, optional, fails open.
  - `app/knowledge/store.py` — `get_retriever(persona)` returning either a
    `FullCorpusRetriever` (NumPy cosine over a saved `embeddings.npy`) or
    a `SeedQuoteRetriever` (in-memory cosine over `persona.seed_quotes`).
- `backend/scripts/` — out-of-band one-shots, run manually:
  - `ingest/buffett.py` — scrapes Berkshire shareholder letters
    (1977–2001) into `data/buffett/chunks.jsonl`.
  - `ingest/fink.py` — scrapes BlackRock CEO letters (2012, 2014–2022),
    Annual Chairman's Letters (2023+), and the Wikipedia biography into
    `data/fink/chunks.jsonl`. Each source is independent; partial
    failures don't abort the run. Uses cross-source dedupe to drop the
    recurring "Mega forces" sidebar.
  - `ingest/musk.py` — assembles a Musk corpus from the Kaggle dataset
    "Elon Musk Tweets 2010 to 2025 (March)" by dadalyndell (CSV must
    be downloaded manually to `backend/data/musk/raw/` since Kaggle
    requires login), Wikiquote (~280 sourced quotes 2005–present),
    the Lex Fridman podcast transcripts (#400 + Neuralink team), the
    Joe Rogan Experience #1470 transcript via singjupost.com, the
    Wikipedia biography, and the "Views of Elon Musk" page. Per-source
    speaker filtering keeps only Musk's lines from podcast transcripts;
    the Kaggle CSV ingestion drops retweets, replies-to-others, and
    sub-40-char tweets, then year-buckets the survivors. The Kaggle
    source is optional — if the CSV is missing the script logs and
    skips, falling back to the other sources.
  - `ingest/marx.py` — scrapes Marx's economic and political core from
    marxists.org: Communist Manifesto, Capital Vol. I (33 chapters +
    appendix), Wage Labour and Capital, Value Price and Profit,
    Critique of the Gotha Programme, Theses on Feuerbach, Economic and
    Philosophic Manuscripts of 1844, plus the Wikipedia biography.
    ~1850 chunks. Per-source independent like fink.py; cross-source
    dedupe drops repeated prefatory matter.
  - `ingest/thiel.py` — assembles Thiel's corpus from Wikiquote, the
    Cato Unbound essay "The Education of a Libertarian" (which the
    site renders inline with his reply post in the same exchange),
    First Things' "Against Edenism," the Founders Fund "Hereticon /
    The Future" manifesto, six Singjupost-hosted speaker-attributed
    transcripts (Antichrist talk, Jordan Peterson podcast, AI/Mars/
    Immortality, Apocalypse Now I & II, Trump-administration talk),
    the 2016 Hamilton commencement monologue, and the Wikipedia
    biography. ~200 chunks. Per-source independent; cross-post
    duplicates between Singjupost URLs are silently dropped by the
    paragraph-level dedupe rather than failing the run.
  - `ingest/caesar.py` — fetches Project Gutenberg ebook #10657
    (McDevitte's English translation containing both De Bello Gallico
    Books I-VIII and De Bello Civili Books I-III), splits the
    concatenated plain text at the "THE CIVIL WAR" marker, then chunks
    by chapter (`I.--`, `II.--`, ...) within each book. Adds the
    Wikiquote and Wikipedia pages on top. ~670 chunks. The De Quincey
    introduction at the front of the file is dropped because it is not
    Caesar's voice.
  - `ingest/_chunking.py` — paragraph-aware chunker, reusable.
  - `build_index.py` — embeds a chunks.jsonl into `embeddings.npy`.
  - `smoke_fink.py` — drives a short Buffett↔Fink discourse end-to-end
    and prints the retrieved quotes per persona. Useful as a regression
    test after touching the discourse loop or knowledge store.
  - `smoke_musk.py` — same idea for a Fink↔Musk debate on AI and the
    labor market.
  - `smoke_marx.py` — same idea for a Buffett↔Marx debate on whether
    capital accumulation benefits workers.
  - `smoke_thiel.py` — same idea for a Fink↔Thiel debate on
    technological stagnation.
  - `smoke_caesar.py` — same idea for a Fink↔Caesar debate on
    committing decisively to expensive long-term projects.
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
Copy-Item .env.example .env       # add your MODEL_ACCESS_KEY (DO key)
python -m scripts.ingest.buffett  # ~1 minute, hits berkshirehathaway.com
python -m scripts.build_index buffett   # tiny embedding cost on DO
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
- **In-memory sessions**: `routes.py` `discourse_sessions: Dict`.
  Restarts wipe everything (accepted trade-off for the demo; deploy
  off-hours or warn users). Cached on the session: `news` (Tavily
  results) and `quotes_by_persona` (top-k retrieval per persona) — both
  populated lazily.
- **Sync routes, on purpose**: `next_turn` and `trigger_aporia` are
  `def`, not `async def`. The OpenAI SDK call inside `llm.generate` is
  synchronous and would block the event loop for the entire 5-15 second
  LLM round-trip if these routes were async. With sync routes, FastAPI
  runs them in starlette's threadpool, so concurrent users don't block
  each other. Do NOT convert to `async def` without first switching
  `llm.generate` to `openai.AsyncOpenAI` and awaiting it — see the
  header comment in `app/api/routes.py`.
- **Fly deployment is single-machine, always-on**: `fly.toml` sets
  `auto_stop_machines = false` because in-memory sessions can't survive
  a stop. Do not enable auto-stop until session storage moves out of
  process memory.
- **Plato has no LLM**: pure templates. Don't assume model calls.
- **Plato's `create_context` has a bug**: it indexes `speakers` by
  `turn_number` and dies once `turn_number > len(speakers)`. The
  discourse loop avoids it by building `TurnContext` directly. If you
  use `create_context` for a new caller, fix it first.
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
