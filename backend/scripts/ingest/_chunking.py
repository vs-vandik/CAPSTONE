"""Paragraph-aware chunker for ingestion scripts.

Most expert corpora (annual letters, transcripts, public-domain books) are
prose with clear paragraph boundaries. Splitting on those boundaries
preserves the speaker's argument structure, which matters for voice
fidelity in retrieval.

Strategy:
- Treat each input paragraph as the atomic unit.
- Pack consecutive paragraphs into a chunk until adding the next one would
  exceed `target_tokens`.
- Carry the last paragraph of the previous chunk forward as the first
  paragraph of the next chunk (one-paragraph overlap).
- Drop chunks below `min_chunk_chars`.

Token counting is approximate: we use len(text) / 4 as a proxy. The actual
embedding API truncates at its own limit anyway, and ~500 tokens is well
under text-embedding-3-small's 8192 cap.
"""

from typing import Iterable, List


def approx_tokens(text: str) -> int:
    """Cheap token estimate. Good enough for sizing chunks."""
    return max(1, len(text) // 4)


def chunk_paragraphs(
    paragraphs: Iterable[str],
    *,
    target_tokens: int = 500,
    min_chunk_chars: int = 200,
) -> List[str]:
    """Pack paragraphs into chunks of ~target_tokens with 1-paragraph overlap.

    Args:
        paragraphs: Iterable of paragraph strings, already cleaned (no
            internal line wrapping, no empty strings).
        target_tokens: Soft cap on tokens per chunk. We may exceed by one
            paragraph because we always include the next paragraph fully
            rather than splitting mid-paragraph.
        min_chunk_chars: Drop chunks shorter than this. Filters out the
            trailing chunk when the corpus runs out mid-pack.

    Returns:
        List of chunk strings.
    """
    paragraphs = [p.strip() for p in paragraphs if p and p.strip()]
    if not paragraphs:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = approx_tokens(para)

        # If a single paragraph exceeds target_tokens, emit it on its own
        # rather than try to split it.
        if not current and para_tokens > target_tokens:
            chunks.append(para)
            continue

        if current and current_tokens + para_tokens > target_tokens:
            chunks.append("\n\n".join(current))
            # Carry the last paragraph forward as overlap.
            current = [current[-1], para]
            current_tokens = approx_tokens(current[0]) + para_tokens
        else:
            current.append(para)
            current_tokens += para_tokens

    if current:
        chunks.append("\n\n".join(current))

    return [c for c in chunks if len(c) >= min_chunk_chars]
