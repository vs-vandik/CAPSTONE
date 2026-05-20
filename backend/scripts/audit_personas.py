"""Audit script: verify the runtime retrieval behavior of every persona.

For each persona, prints:
- The retriever class actually constructed.
- The on-disk corpus size (chunks + embeddings) if any.
- The top-k retrieval for a topic well-suited to that persona.

Run from `backend/`:
    python -m scripts.audit_personas
"""

from __future__ import annotations

import json
from pathlib import Path

from app.knowledge import store
from app.core.personas import PERSONAS


# A topic chosen per-persona to surface their strongest material.
TOPICS = {
    "buffett": "How should a long-term investor think about market crashes?",
    "fink": "How should asset managers approach the energy transition?",
    "musk": "Will artificial intelligence make most jobs obsolete?",
    "marx": "Does capital accumulation benefit or impoverish the working class?",
    "caesar": "How should a leader handle the cost of a long military campaign?",
    "thiel": "Is technological progress meaningfully slowing down?",
    "bieger": (
        "How should alpine tourism adapt to digital analytics, mobility "
        "shifts, and sustainability pressure?"
    ),
}


def _disk_stats(persona_id: str) -> dict:
    base = Path("data") / persona_id
    chunks = base / "chunks.jsonl"
    emb = base / "embeddings.npy"
    out = {"chunks_jsonl": None, "n_chunks": 0, "embeddings_npy": None}
    if chunks.is_file():
        n = sum(1 for line in chunks.read_text(encoding="utf-8").splitlines() if line.strip())
        out["chunks_jsonl"] = chunks.stat().st_size
        out["n_chunks"] = n
    if emb.is_file():
        out["embeddings_npy"] = emb.stat().st_size
    return out


def main() -> int:
    store.clear_cache()

    print(f"{'persona':12s}  {'tier':8s}  retriever                size                 chunks  topic-test")
    print("-" * 110)

    for pid, persona in PERSONAS.items():
        stats = _disk_stats(pid)
        retriever = store.get_retriever(persona)
        rclass = type(retriever).__name__
        size_str = ""
        if stats["chunks_jsonl"]:
            size_str = f"{stats['chunks_jsonl']//1024:>4d} KB jsonl"
            if stats["embeddings_npy"]:
                size_str += f" + {stats['embeddings_npy']//1024:>5d} KB npy"
        else:
            size_str = "(no on-disk corpus)"
        print(
            f"{pid:12s}  {persona.rag_tier:8s}  {rclass:22s}  {size_str:35s}  {stats['n_chunks']:5d}"
        )

        # Run a real retrieval and show the top result so we can see
        # what the persona will actually be grounded with.
        topic = TOPICS.get(pid, persona.bio)
        chunks = retriever.query(topic, k=2)
        print(f"   topic: {topic}")
        if not chunks:
            print("   (no chunks returned)")
        for c in chunks:
            preview = c.text[:160].replace("\n", " ")
            print(f"     [{c.score:.3f}] {c.source[:55]}: {preview}...")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
