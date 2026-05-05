"""Build the on-disk vector index for an expert from their chunks.jsonl.

Usage (run from `backend/`):

    python -m scripts.build_index buffett

Reads:  data/<expert>/chunks.jsonl
Writes: data/<expert>/embeddings.npy   (shape: (N, 1536), float32, L2-normalized)

Embeddings are produced by OpenAI text-embedding-3-small. Cost for the full
Buffett corpus (2657 chunks ~ 1.2M tokens) is ~$0.024 once.

We batch in groups of 100 (well under the 2048-input API limit and the
8192-token-per-input limit). On retry-able errors we let the OpenAI SDK's
default retry handle it; on hard failures we abort with a useful message
so partial state never gets persisted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

import numpy as np

from app.knowledge.store import EMBEDDING_MODEL, _l2_normalize


BATCH_SIZE = 100


def main(expert_id: str) -> int:
    repo_backend = Path(__file__).resolve().parents[1]
    expert_dir = repo_backend / "data" / expert_id
    chunks_path = expert_dir / "chunks.jsonl"
    out_path = expert_dir / "embeddings.npy"

    if not chunks_path.is_file():
        print(f"ERR: {chunks_path} not found. Run the ingestion script first.", file=sys.stderr)
        return 2

    chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not chunks:
        print(f"ERR: {chunks_path} is empty.", file=sys.stderr)
        return 2

    print(f"Embedding {len(chunks)} chunks for {expert_id}...")

    # Lazy import: the build step is the only place we hit the OpenAI API
    # outside the request path, so we keep the import here to fail fast
    # with a clear message if the key is missing.
    from app.core.llm import _get_client
    client = _get_client()

    all_embeddings: List[np.ndarray] = []
    total_tokens = 0
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        try:
            resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        except Exception as e:
            print(f"\nERR: embedding batch starting at {i} failed: {e}", file=sys.stderr)
            print("Aborting without writing partial output.", file=sys.stderr)
            return 1

        arr = np.array([d.embedding for d in resp.data], dtype=np.float32)
        all_embeddings.append(arr)
        total_tokens += getattr(resp.usage, "total_tokens", 0)

        done = min(i + BATCH_SIZE, len(chunks))
        print(f"  {done}/{len(chunks)}", end="\r")

    print()  # finish progress line

    embeddings = np.concatenate(all_embeddings, axis=0)
    embeddings = _l2_normalize(embeddings)

    if embeddings.shape[0] != len(chunks):
        print(
            f"ERR: got {embeddings.shape[0]} embeddings for {len(chunks)} chunks. "
            "Refusing to write a misaligned index.",
            file=sys.stderr,
        )
        return 1

    np.save(out_path, embeddings)
    print(f"Wrote {out_path}  shape={embeddings.shape}  tokens={total_tokens}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.build_index <expert_id>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
