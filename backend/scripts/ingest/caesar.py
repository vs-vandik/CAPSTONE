"""Scrape Julius Caesar's Commentaries for the persona corpus.

Caesar's two surviving prose works are public domain in English
translation. Project Gutenberg ebook #10657 (W. A. McDevitte's 1915
Everyman's Library translation) contains both:

- De Bello Gallico (The Gallic War), Books I-VIII
- De Bello Civili (The Civil War), Books I-III

The two works are concatenated in a single plain-text file, separated
by a "THE CIVIL WAR" header. Books are headed by "BOOK I", "BOOK II"
etc. Chapters are headed by Roman-numeral markers like "I.--", "II.--",
"LV.--" at the start of a line, followed by the chapter prose.

We chunk by chapter — each chapter is a self-contained narrative unit
(typically 1-3 paragraphs of hard-wrapped prose) which makes for clean
retrieval boundaries. The existing paragraph-aware chunker then packs
consecutive chapters together until the target token budget is hit.

Two supplementary sources fill in the demo's needs:
- Wikiquote: sourced apocryphal/attributed lines plus context for the
  most-quoted passages, including the famous lines that don't appear
  in his own writing (Veni Vidi Vici, Alea Iacta Est, Et Tu Brute).
- Wikipedia: biography for context grounding (career arc, Rubicon,
  assassination, succession).

Run from `backend/`:

    python -m scripts.ingest.caesar

Output:

    backend/data/caesar/
        chunks.jsonl              # one chunk per line, ready for embedding
        raw/<slug>.txt            # cleaned plain text per source

Polite: 1.5s delay between fetches.

Notes:
- Gutenberg's text contains transcriber-note artifacts in brackets
  (macron / umlaut placeholders like "[=x]" and "['x]") which we strip
  during normalization.
- The introduction by Thomas De Quincey at the front of #10657 is
  *not* Caesar's voice and we drop it: ingestion starts at the first
  "BOOK I" header.
- Each source is independent; partial failures don't abort the run.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from scripts.ingest._chunking import chunk_paragraphs


# ==================
# Source catalog
# ==================

# Project Gutenberg ebook 10657: McDevitte's "De Bello Gallico" and
# Other Commentaries. Single plain-text file, ~960 KB.
GUTENBERG_URL = "https://www.gutenberg.org/cache/epub/10657/pg10657.txt"

WIKIQUOTE_URL = "https://en.wikiquote.org/wiki/Julius_Caesar"
WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Julius_Caesar"

# Marker that separates the two works in #10657. Everything before it
# (after the De Quincey introduction) is De Bello Gallico; everything
# after is De Bello Civili.
CIVIL_WAR_MARKER = "THE CIVIL WAR"

# The first book heading appears multiple times because both works
# start with "BOOK I". We use the first occurrence to mark the start
# of the body (skipping the introduction) and the *second* occurrence
# of "BOOK I" to mark the start of the Civil War.
BOOK_HEADER_PATTERN = re.compile(r"^\s*BOOK\s+([IVX]+)\s*$", re.MULTILINE)

# Chapter markers like "I.--", "LV.--" at the start of a line.
# We capture the roman numeral and the rest of the chapter as a unit.
CHAPTER_HEADER_PATTERN = re.compile(
    r"(?:^|\n)\s*([IVXLCDM]{1,6})\.--",
    re.MULTILINE,
)

WIKIQUOTE_SKIP_SECTIONS = {
    "Quotes about Caesar",
    "Quotes about Julius Caesar",
    "Misattributed",
    "External links",
    "See also",
    "References",
    "Notes",
}


# ==================
# HTTP / parsing config
# ==================

REQUEST_DELAY = 1.5
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Each Caesar chapter is short prose (often 200-2000 chars). We accept
# anything 80+ chars; the chunker will pack short chapters together.
MIN_CHAPTER_CHARS = 80

# Wikiquote individual <li> length filter.
MIN_QUOTE_CHARS = 30
MAX_QUOTE_CHARS = 1200

MIN_PARAGRAPH_CHARS = 80

BOILERPLATE_PATTERNS = [
    re.compile(r"^From Wikipedia", re.IGNORECASE),
    re.compile(r"^This article", re.IGNORECASE),
    re.compile(r"^\[edit\]"),
    re.compile(r"^Retrieved from"),
    re.compile(r"^\*\*\*\s*START\s+OF", re.IGNORECASE),
    re.compile(r"^\*\*\*\s*END\s+OF", re.IGNORECASE),
    re.compile(r"^Project Gutenberg", re.IGNORECASE),
    re.compile(r"^This eBook is", re.IGNORECASE),
    re.compile(r"^Produced by", re.IGNORECASE),
    re.compile(r"^Transcriber's Note", re.IGNORECASE),
    re.compile(r"^EVERYMAN'S LIBRARY", re.IGNORECASE),
    re.compile(r"^EDITED BY", re.IGNORECASE),
]

# Bracketed transcriber annotations like [=x] [:x] ['x] [`x] [^x] [)x] [,x]
# used to encode macrons / accents that the plain-text format can't
# represent. They appear inline and are pure noise for our purposes.
TRANSCRIBER_ARTIFACT = re.compile(r"\[\s*[=:'`^),]\s*[A-Za-z]\s*\]")


# ==================
# Entry point
# ==================


def main() -> int:
    repo_backend = Path(__file__).resolve().parents[2]
    out_dir = repo_backend / "data" / "caesar"
    raw_dir = out_dir / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = out_dir / "chunks.jsonl"
    chunks_written = 0
    sources_ok = 0
    sources_failed: List[str] = []

    seen_paragraphs: set[str] = set()

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=60.0,
        follow_redirects=True,
    ) as client, chunks_path.open("w", encoding="utf-8") as f_out:

        # ----- 1. Project Gutenberg: both Commentaries -----
        n = _ingest_gutenberg(client, f_out, raw_dir, seen_paragraphs)
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            sources_failed.append("gutenberg-commentaries")
        time.sleep(REQUEST_DELAY)

        # ----- 2. Wikiquote -----
        n = _ingest_wikiquote(client, f_out, raw_dir, seen_paragraphs)
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            sources_failed.append("wikiquote")
        time.sleep(REQUEST_DELAY)

        # ----- 3. Wikipedia biography -----
        n = _ingest_wikipedia(client, f_out, raw_dir, seen_paragraphs)
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            sources_failed.append("wikipedia-bio")

    print()
    print(f"OK: {sources_ok} sources, {chunks_written} chunks -> {chunks_path}")
    if sources_failed:
        print(f"SKIPPED/FAILED: {sources_failed}", file=sys.stderr)
    if chunks_written == 0:
        print("ERR: zero chunks written; not viable as a corpus.", file=sys.stderr)
        return 1
    return 0


# ==================
# Project Gutenberg: De Bello Gallico + De Bello Civili
# ==================


def _ingest_gutenberg(
    client: httpx.Client,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    """Fetch Gutenberg #10657 and split it into the two works, then
    chunk by chapter within each book.
    """
    try:
        resp = client.get(GUTENBERG_URL)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  [gutenberg] FAIL: {e}", file=sys.stderr)
        return 0

    text = resp.text
    # Drop everything before the first "BOOK I" header (the De Quincey
    # introduction is not Caesar's voice).
    body_start = _find_first_book_i(text)
    if body_start is None:
        print(
            "  [gutenberg] could not locate first BOOK I header; layout changed?",
            file=sys.stderr,
        )
        return 0

    # Drop everything from the Gutenberg END marker onward.
    end_match = re.search(r"\*\*\*\s*END\s+OF", text)
    body_end = end_match.start() if end_match else len(text)

    body = text[body_start:body_end]

    # Split body at "THE CIVIL WAR" marker.
    civil_match = re.search(r"\n\s*THE\s+CIVIL\s+WAR\s*\n", body, re.IGNORECASE)
    if civil_match is None:
        print(
            "  [gutenberg] could not locate CIVIL WAR marker; layout changed?",
            file=sys.stderr,
        )
        return 0

    gallic_text = body[: civil_match.start()]
    civil_text = body[civil_match.end():]

    n_total = 0

    n_gallic = _emit_book_chunks(
        body_text=gallic_text,
        work_id="bellum-gallicum",
        work_title="De Bello Gallico (The Gallic War)",
        f_out=f_out,
        raw_dir=raw_dir,
        seen=seen,
    )
    n_total += n_gallic
    print(f"  [bellum-gallicum] -> {n_gallic} chunks")

    n_civil = _emit_book_chunks(
        body_text=civil_text,
        work_id="bellum-civile",
        work_title="De Bello Civili (The Civil War)",
        f_out=f_out,
        raw_dir=raw_dir,
        seen=seen,
    )
    n_total += n_civil
    print(f"  [bellum-civile]   -> {n_civil} chunks")

    return n_total


def _find_first_book_i(text: str) -> Optional[int]:
    """Return byte offset of the first 'BOOK I' header line."""
    for m in BOOK_HEADER_PATTERN.finditer(text):
        if m.group(1) == "I":
            return m.start()
    return None


def _emit_book_chunks(
    *,
    body_text: str,
    work_id: str,
    work_title: str,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    """Walk a single work's text, chunking by chapter within each book.

    We iterate the BOOK headers to demarcate book boundaries, then
    within each book split on chapter markers (I.--, II.--, ...).
    Chapter prose is normalized (whitespace collapsed, transcriber
    artifacts stripped) and paragraphs are written via the existing
    chunk_paragraphs packer.
    """
    book_headers = list(BOOK_HEADER_PATTERN.finditer(body_text))
    if not book_headers:
        return 0

    # Persist a cleaned per-work raw dump for debugging.
    raw_lines: List[str] = []

    n = 0
    for i, header in enumerate(book_headers):
        book_roman = header.group(1)
        book_start = header.end()
        book_end = book_headers[i + 1].start() if i + 1 < len(book_headers) else len(body_text)
        book_text = body_text[book_start:book_end]

        chapters = _split_chapters(book_text)
        if not chapters:
            continue

        # Filter and dedupe.
        kept: List[Tuple[str, str]] = []  # (roman, text)
        for roman, ch_text in chapters:
            cleaned = _normalize_prose(ch_text)
            if len(cleaned) < MIN_CHAPTER_CHARS:
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            kept.append((roman, cleaned))

        if not kept:
            continue

        raw_lines.append(f"=== BOOK {book_roman} ===\n")
        for roman, ch in kept:
            raw_lines.append(f"[{roman}] {ch}")
            raw_lines.append("")

        # Pack chapters into chunks via the shared chunker. We feed only
        # the prose (no chapter prefixes) so similarity scores aren't
        # diluted by Roman-numeral noise; the source_title carries the
        # provenance.
        prose_only = [ch for _, ch in kept]
        for chunk_idx, chunk in enumerate(chunk_paragraphs(prose_only, target_tokens=500)):
            record: Dict = {
                "id": f"caesar-{work_id}-bk{book_roman}-{chunk_idx:03d}",
                "expert_id": "caesar",
                "kind": "commentary",
                "work": work_id,
                "book": book_roman,
                "source_url": GUTENBERG_URL,
                "source_title": f"{work_title}: Book {book_roman}",
                "text": chunk,
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1

    if raw_lines:
        (raw_dir / f"{work_id}.txt").write_text(
            "\n".join(raw_lines), encoding="utf-8"
        )

    return n


def _split_chapters(book_text: str) -> List[Tuple[str, str]]:
    """Split a single book's text into (roman_numeral, chapter_prose).

    The McDevitte translation marks chapter boundaries with a line that
    starts with `<roman>.--`. We split on that marker and reattach each
    chapter to its preceding numeral.
    """
    matches = list(CHAPTER_HEADER_PATTERN.finditer(book_text))
    if not matches:
        return []

    out: List[Tuple[str, str]] = []
    for i, m in enumerate(matches):
        roman = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(book_text)
        prose = book_text[start:end]
        out.append((roman, prose))
    return out


def _normalize_prose(text: str) -> str:
    """Strip transcriber artifacts and collapse whitespace.

    Caesar's chapters are hard-wrapped to ~70 columns. Newlines inside
    a chapter are layout artifacts, not paragraph breaks, so we collapse
    runs of whitespace to single spaces.
    """
    text = TRANSCRIBER_ARTIFACT.sub("", text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ==================
# Wikiquote
# ==================


def _ingest_wikiquote(
    client: httpx.Client,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    try:
        resp = client.get(WIKIQUOTE_URL)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  [wikiquote] FAIL: {e}", file=sys.stderr)
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.find("div", {"id": "mw-content-text"})
    if content is None:
        return 0

    for tag in content.find_all(["sup", "table", "style", "script"]):
        tag.decompose()

    current_section = "Top"
    skip = False
    quotes_by_section: Dict[str, List[str]] = {}

    for tag in content.find_all(["h2", "h3", "ul"]):
        if tag.name in ("h2", "h3"):
            heading = re.sub(r"\[edit\]", "", tag.get_text(" ", strip=True)).strip()
            current_section = heading
            skip = any(skip_name in heading for skip_name in WIKIQUOTE_SKIP_SECTIONS)
            continue

        if skip:
            continue

        for li in tag.find_all("li", recursive=False):
            quote = _normalize_prose(li.get_text(" ", strip=True))
            if not (MIN_QUOTE_CHARS <= len(quote) <= MAX_QUOTE_CHARS):
                continue
            if _looks_like_boilerplate(quote):
                continue
            if quote in seen:
                continue
            seen.add(quote)
            quotes_by_section.setdefault(current_section, []).append(quote)

    if not quotes_by_section:
        print("  [wikiquote] zero quotes harvested", file=sys.stderr)
        return 0

    total_quotes = sum(len(qs) for qs in quotes_by_section.values())

    raw_lines: List[str] = []
    for section, quotes in quotes_by_section.items():
        raw_lines.append(f"=== {section} ===\n")
        for q in quotes:
            raw_lines.append(q)
            raw_lines.append("")
    (raw_dir / "wikiquote.txt").write_text("\n".join(raw_lines), encoding="utf-8")

    n = 0
    for section, quotes in quotes_by_section.items():
        for i, chunk in enumerate(chunk_paragraphs(quotes, target_tokens=400)):
            record: Dict = {
                "id": f"caesar-wikiquote-{_slugify(section)}-{i:03d}",
                "expert_id": "caesar",
                "kind": "wikiquote",
                "section": section,
                "source_url": WIKIQUOTE_URL,
                "source_title": f"Wikiquote: Julius Caesar ({section})",
                "text": chunk,
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1

    print(f"  [wikiquote] {total_quotes:4d} quotes across {len(quotes_by_section)} sections -> {n} chunks")
    return n


# ==================
# Wikipedia biography
# ==================


def _ingest_wikipedia(
    client: httpx.Client,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    try:
        resp = client.get(WIKIPEDIA_URL)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  [wikipedia-bio] FAIL: {e}", file=sys.stderr)
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.find("div", {"id": "mw-content-text"})
    if content is None:
        return 0

    for tag in content.find_all(["sup", "table", "style", "script"]):
        tag.decompose()

    raw_paragraphs: List[str] = []
    for p in content.find_all("p"):
        text = p.get_text(" ", strip=True)
        if text:
            raw_paragraphs.append(text)

    cleaned = list(_clean_paragraphs(raw_paragraphs))
    deduped: List[str] = []
    for p in cleaned:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)

    if len(deduped) < 5:
        print(f"  [wikipedia-bio] only {len(deduped)} paragraphs, skipping")
        return 0

    (raw_dir / "wikipedia-bio.txt").write_text(
        "\n\n".join(deduped), encoding="utf-8"
    )

    n = 0
    for i, chunk in enumerate(chunk_paragraphs(deduped)):
        record: Dict = {
            "id": f"caesar-wikipedia-bio-{i:03d}",
            "expert_id": "caesar",
            "kind": "biography",
            "source_url": WIKIPEDIA_URL,
            "source_title": "Wikipedia: Julius Caesar",
            "text": chunk,
        }
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        n += 1

    print(f"  [wikipedia-bio] {len(deduped):4d} paragraphs -> {n} chunks")
    return n


# ==================
# Helpers
# ==================


def _clean_paragraphs(raw_paragraphs: Iterable[str]) -> Iterator[str]:
    for raw in raw_paragraphs:
        para = _normalize_prose(raw)
        if not para:
            continue
        if len(para) < MIN_PARAGRAPH_CHARS:
            continue
        if _looks_like_boilerplate(para):
            continue
        if _looks_like_table(para):
            continue
        yield para


def _looks_like_boilerplate(para: str) -> bool:
    return any(p.search(para) for p in BOILERPLATE_PATTERNS)


def _looks_like_table(para: str) -> bool:
    non_space = [c for c in para if not c.isspace()]
    if not non_space:
        return True
    letters = sum(1 for c in non_space if c.isalpha())
    return letters / len(non_space) < 0.55


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s or "section"


if __name__ == "__main__":
    raise SystemExit(main())
