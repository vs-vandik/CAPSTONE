"""Quote retrieval for personas.

Two strategies behind one interface (`get_retriever(persona) -> Retriever`):

- `FullCorpusRetriever`: reads `data/<expert>/embeddings.npy` and
  `data/<expert>/chunks.jsonl` from disk, embeds the query via the
  configured embedding provider (DigitalOcean Inference by default),
  returns top-k chunks by cosine similarity. Used for personas with the
  `full` RAG tier (Buffett, Fink, Musk).

- `SeedQuoteRetriever`: in-memory cosine over the persona's `seed_quotes`,
  embedded once and cached on the retriever instance. Used for personas
  with the `curated` RAG tier (Marx, Caesar, Kardashian).

If a `full`-tier persona has no on-disk index yet (e.g. Fink and Musk
before their scrapers are written), `get_retriever` falls back to a
`SeedQuoteRetriever` over the persona's seed_quotes so the demo still
runs end-to-end.

We intentionally do NOT use Chroma: at the demo's scale (a few thousand
chunks per expert) NumPy cosine is faster, has no C build deps, and
deploys identically on every platform.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from app.core.config import settings
from app.core.personas import Persona


# Embedding config is read from settings rather than hardcoded so the
# whole stack can be repointed at OpenAI / a different DO model / a local
# provider by editing .env. The exported constants stay for callers that
# imported them by name (build_index.py).
EMBEDDING_MODEL = settings.EMBEDDING_MODEL
EMBEDDING_DIM = settings.EMBEDDING_DIM


# Resolve the data root from the cwd at import time. Backend is always
# launched from `backend/`, see AGENTS.md.
DATA_ROOT = Path(settings.DATA_DIR).resolve()


# ==================
# Embedding helper
# ==================


def embed(texts: Sequence[str]) -> np.ndarray:
    """Embed a batch of texts with the configured embedding model.

    Returns:
        ndarray of shape (len(texts), EMBEDDING_DIM), L2-normalized so
        cosine similarity reduces to a dot product.
    """
    if not texts:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

    # Lazy import so this module doesn't require the LLM client unless
    # retrieval is actually used.
    from app.core.llm import _get_client  # noqa: WPS437 (private intentionally)

    client = _get_client()
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=list(texts))
    arr = np.array([d.embedding for d in resp.data], dtype=np.float32)
    return _l2_normalize(arr)


def _l2_normalize(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


# ==================
# Retrievers
# ==================


@dataclass
class RetrievedChunk:
    text: str
    score: float
    source: str  # human-readable source label, used for citations later


class Retriever:
    """Common interface."""

    def query(self, text: str, k: int = 4) -> List[RetrievedChunk]:
        raise NotImplementedError


class FullCorpusRetriever(Retriever):
    """Top-k cosine search over a pre-embedded corpus on disk."""

    def __init__(self, expert_id: str, embeddings: np.ndarray, metadata: List[Dict]):
        self.expert_id = expert_id
        self.embeddings = embeddings  # (N, D), L2-normalized
        self.metadata = metadata      # parallel list of chunk dicts

    def query(self, text: str, k: int = 4) -> List[RetrievedChunk]:
        if not text.strip() or len(self.metadata) == 0:
            return []
        q = embed([text])  # (1, D), normalized
        # Cosine sim = dot product since both sides are L2-normalized.
        scores = (self.embeddings @ q[0])  # (N,)
        top_idx = np.argpartition(-scores, kth=min(k, len(scores) - 1))[:k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        return [
            RetrievedChunk(
                text=self.metadata[i]["text"],
                score=float(scores[i]),
                source=self.metadata[i].get("source_title", self.expert_id),
            )
            for i in top_idx
        ]


class SeedQuoteRetriever(Retriever):
    """Cosine over the persona's seed_quotes, embedded lazily once."""

    def __init__(self, persona: Persona):
        self.persona = persona
        self._embeddings: Optional[np.ndarray] = None
        self._lock = threading.Lock()

    def _ensure_embedded(self) -> None:
        if self._embeddings is not None:
            return
        with self._lock:
            if self._embeddings is not None:
                return
            self._embeddings = embed(self.persona.seed_quotes)

    def query(self, text: str, k: int = 4) -> List[RetrievedChunk]:
        if not self.persona.seed_quotes or not text.strip():
            return []
        self._ensure_embedded()
        q = embed([text])
        scores = (self._embeddings @ q[0])
        k = min(k, len(self.persona.seed_quotes))
        top_idx = np.argpartition(-scores, kth=k - 1)[:k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        return [
            RetrievedChunk(
                text=self.persona.seed_quotes[i],
                score=float(scores[i]),
                source=f"{self.persona.name} (seed quote)",
            )
            for i in top_idx
        ]


# ==================
# Factory + per-process cache
# ==================


# Cache retrievers per persona id so we don't reload embeddings.npy on every
# request. The cache survives the lifetime of the worker process; uvicorn
# --reload bounces the process on file change so dev iteration stays fresh.
_retriever_cache: Dict[str, Retriever] = {}
_cache_lock = threading.Lock()


def get_retriever(persona: Persona, *, force_seed_quotes: bool = False) -> Retriever:
    """Return the right retriever for a persona, cached per process.

    Args:
        persona: persona to retrieve for.
        force_seed_quotes: if True, return a `SeedQuoteRetriever` even
            for `full`-tier personas that have a built index. Useful for
            A/B comparison in smoke tests. Bypasses the cache because
            forced and unforced retrievers should not share an entry.
    """
    if force_seed_quotes:
        return SeedQuoteRetriever(persona)

    if persona.id in _retriever_cache:
        return _retriever_cache[persona.id]

    with _cache_lock:
        if persona.id in _retriever_cache:
            return _retriever_cache[persona.id]
        retriever = _build_retriever(persona)
        _retriever_cache[persona.id] = retriever
        return retriever


def _build_retriever(persona: Persona) -> Retriever:
    if persona.rag_tier == "full":
        idx = _try_load_full_index(persona.id)
        if idx is not None:
            return idx
        # Full-tier persona without a built index yet: gracefully fall back
        # so the demo works before all scrapers are written.
        print(
            f"[knowledge] No on-disk index for {persona.id}; "
            f"falling back to seed_quotes."
        )
    return SeedQuoteRetriever(persona)


def _try_load_full_index(expert_id: str) -> Optional[FullCorpusRetriever]:
    expert_dir = DATA_ROOT / expert_id
    emb_path = expert_dir / "embeddings.npy"
    meta_path = expert_dir / "chunks.jsonl"
    if not emb_path.is_file() or not meta_path.is_file():
        return None
    embeddings = np.load(emb_path)
    metadata = [json.loads(line) for line in meta_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if embeddings.shape[0] != len(metadata):
        raise RuntimeError(
            f"Index mismatch for {expert_id}: "
            f"{embeddings.shape[0]} embeddings vs {len(metadata)} chunks. "
            f"Rebuild with `python -m scripts.build_index {expert_id}`."
        )
    if embeddings.shape[1] != EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding-dim mismatch for {expert_id}: index is "
            f"{embeddings.shape[1]} dim but the configured model "
            f"{EMBEDDING_MODEL!r} produces {EMBEDDING_DIM} dim. "
            f"Either change EMBEDDING_MODEL/EMBEDDING_DIM in .env back to "
            f"the model that built this index, or rebuild with "
            f"`python -m scripts.build_index {expert_id}`."
        )
    # Defensive: ensure normalized so query() can use plain dot product.
    embeddings = _l2_normalize(embeddings.astype(np.float32))
    return FullCorpusRetriever(expert_id, embeddings, metadata)


def clear_cache() -> None:
    """For tests: drop cached retrievers."""
    with _cache_lock:
        _retriever_cache.clear()
