"""Scrape Peter Thiel's public corpus.

Thiel has no single archive but a long trail of essays, talks, and
podcast transcripts that quote him verbatim. We assemble:

1. Wikiquote (en.wikiquote.org/wiki/Peter_Thiel). Sourced verbatim
   quotes, including a section on Zero to One. Smaller than Musk's
   Wikiquote (only ~26 entries) but high signal.
2. Cato Unbound's "The Education of a Libertarian" (April 2009). His
   most-cited essay; the source of the often-quoted "I no longer
   believe that freedom and democracy are compatible" line.
3. Cato Unbound's reply post in the same exchange.
4. First Things' "Against Edenism" (April 2015). His most-cited
   theological essay.
5. Founders Fund manifestos / "The Future" landing page. Short but
   signature voice.
6. Singjupost-hosted speaker-attributed transcripts of:
   - The "Political Theology of the Antichrist" talk
   - Jordan B. Peterson podcast "Why We Stopped Progressing"
   - Joe Rogan-hosted "AI, Mars, and Immortality"
   - "Apocalypse Now" Parts I and II
   - "What the Trump Administration Must Do Instead of Revenge"
7. Singjupost commencement address transcript (Hamilton College
   2016) — a monologue with no speaker prefix; ingested with a
   different parser that treats the whole article as Thiel.
8. Wikipedia biography for context.

Run from `backend/`:

    python -m scripts.ingest.thiel

Output:

    backend/data/thiel/
        chunks.jsonl       # one chunk per line, ready for embedding
        raw/<slug>.txt     # cleaned plain text per source

Polite: 1.5s delay between fetches.

Notes:
- Singjupost cross-posts the same transcript to multiple URLs. Two
  pairs of URLs are detected as duplicates by our cross-source
  paragraph dedupe, so the second of each pair contributes nothing
  new — we still include them so the script self-documents.
- Some Singjupost pages have full Q&A format (Speaker: line); the
  Hamilton commencement has no prefix. We try the speaker-filtered
  parser first and fall back to the monologue parser if it returns
  too few hits.
- Each source is independent. Hard failures of a single source don't
  abort the run; we only fail the script if zero chunks were written.
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

WIKIQUOTE_URL = "https://en.wikiquote.org/wiki/Peter_Thiel"
WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Peter_Thiel"

# Long-form essays. (url, slug, title, kind)
# Note: Cato Unbound's exchange pages render every post in the thread
# inside the article DOM. Scraping "The Education of a Libertarian"
# already captures Thiel's reply post ("Your Suffrage Isn't in
# Danger") as well, so we don't list the reply URL separately.
ESSAY_SOURCES: List[Tuple[str, str, str, str]] = [
    (
        "https://www.cato-unbound.org/2009/04/13/peter-thiel/education-libertarian/",
        "cato-education-libertarian",
        'Cato Unbound: "The Education of a Libertarian" (April 2009)',
        "essay",
    ),
    (
        "https://www.firstthings.com/article/2015/04/against-edenism",
        "firstthings-against-edenism",
        'First Things: "Against Edenism" (April 2015)',
        "essay",
    ),
    (
        "https://foundersfund.com/the-future/",
        "foundersfund-the-future",
        "Founders Fund: The Future / Hereticon manifesto",
        "manifesto",
    ),
]

# Singjupost transcripts that follow the speaker-prefix pattern
# (e.g. "Peter Thiel: ..."). Per-source filtering keeps only Thiel's
# turns. (url, slug, title)
SINGJUPOST_QA_SOURCES: List[Tuple[str, str, str]] = [
    (
        "https://singjupost.com/peter-thiel-on-political-theology-of-the-antichrist-transcript/",
        "thiel-antichrist",
        "Peter Thiel on the Political Theology of the Antichrist",
    ),
    (
        "https://singjupost.com/transcript-why-we-stopped-progressing-peter-thiel-on-dr-jordan-b-peterson-podcast/",
        "thiel-peterson-stagnation",
        'Peter Thiel on the Jordan B. Peterson Podcast: "Why We Stopped Progressing"',
    ),
    (
        "https://singjupost.com/a-i-mars-and-immortality-are-we-dreaming-big-enough-peter-thiel-transcript/",
        "thiel-ai-mars-immortality",
        'Peter Thiel: "AI, Mars, and Immortality — Are We Dreaming Big Enough?"',
    ),
    (
        "https://singjupost.com/transcript-of-apocalypse-now-peter-thiel-on-ancient-prophecies-and-modern-tech/",
        "thiel-apocalypse-1",
        "Peter Thiel: Apocalypse Now — Ancient Prophecies and Modern Tech (Part I)",
    ),
    (
        "https://singjupost.com/transcript-of-part-ii-apocalypse-now-peter-thiel-on-ancient-prophecies-and-modern-tech/",
        "thiel-apocalypse-2",
        "Peter Thiel: Apocalypse Now — Ancient Prophecies and Modern Tech (Part II)",
    ),
    (
        "https://singjupost.com/transcript-of-what-the-trump-administration-must-do-instead-of-revenge-peter-thiel/",
        "thiel-trump-revenge",
        "Peter Thiel: What the Trump Administration Must Do Instead of Revenge",
    ),
]

# Monologues / commencement-style speeches with no speaker prefix.
# We parse every paragraph as Thiel-attributed.
SINGJUPOST_MONOLOGUE_SOURCES: List[Tuple[str, str, str]] = [
    (
        "https://singjupost.com/peter-thiels-2016-hamilton-college-commencement-address-full-transcript/",
        "thiel-hamilton-commencement-2016",
        "Peter Thiel: 2016 Hamilton College Commencement Address",
    ),
]

WIKIQUOTE_SKIP_SECTIONS = {
    "Quotes about Thiel",
    "Quotes about Peter Thiel",
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

# Wikiquote individual <li> length filter.
MIN_QUOTE_CHARS = 40
MAX_QUOTE_CHARS = 1200

# Long-form prose paragraphs.
MIN_PARAGRAPH_CHARS = 80

BOILERPLATE_PATTERNS = [
    re.compile(r"^From Wikipedia", re.IGNORECASE),
    re.compile(r"^This article", re.IGNORECASE),
    re.compile(r"^Jump to navigation", re.IGNORECASE),
    re.compile(r"^\[edit\]"),
    re.compile(r"^Retrieved from"),
    # Singjupost frequently appends a 'Related Posts' / 'For more' block
    # at the bottom of every transcript.
    re.compile(r"^Related Posts", re.IGNORECASE),
    re.compile(r"^For more transcripts", re.IGNORECASE),
    re.compile(r"^Also Read", re.IGNORECASE),
    # Cato Unbound author-credit boilerplate.
    re.compile(r"^Peter Thiel is a partner", re.IGNORECASE),
    # Hamilton commencement intro paragraph from singjupost.
    re.compile(r"^Read the full transcript", re.IGNORECASE),
]

# Speaker-prefix patterns for Singjupost Q&A transcripts.
THIEL_SPEAKER_PATTERN = re.compile(
    r"^\s*(?:Peter Thiel|Mr\.?\s*Thiel|Thiel|Peter)\s*[:\-]\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
OTHER_SPEAKER_PATTERN = re.compile(
    r"^\s*(?:\[[^\]]{1,40}\]|[A-Z][A-Za-z\.\s]{1,30})\s*[:\-]\s*",
)


# ==================
# Entry point
# ==================


def main() -> int:
    repo_backend = Path(__file__).resolve().parents[2]
    out_dir = repo_backend / "data" / "thiel"
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
        timeout=30.0,
        follow_redirects=True,
    ) as client, chunks_path.open("w", encoding="utf-8") as f_out:

        # ----- 1. Wikiquote -----
        n = _ingest_wikiquote(client, f_out, raw_dir, seen_paragraphs)
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            sources_failed.append("wikiquote")
        time.sleep(REQUEST_DELAY)

        # ----- 2. Long-form essays -----
        for url, slug, title, kind in ESSAY_SOURCES:
            n = _ingest_essay(
                client=client,
                url=url,
                slug=slug,
                title=title,
                kind=kind,
                f_out=f_out,
                raw_dir=raw_dir,
                seen=seen_paragraphs,
            )
            if n > 0:
                chunks_written += n
                sources_ok += 1
            else:
                sources_failed.append(slug)
            time.sleep(REQUEST_DELAY)

        # ----- 3. Speaker-attributed transcripts -----
        for url, slug, title in SINGJUPOST_QA_SOURCES:
            n = _ingest_qa_transcript(
                client=client,
                url=url,
                slug=slug,
                title=title,
                f_out=f_out,
                raw_dir=raw_dir,
                seen=seen_paragraphs,
            )
            if n > 0:
                chunks_written += n
                sources_ok += 1
            else:
                # Cross-posted duplicates legitimately produce zero new
                # paragraphs — that isn't a failure.
                pass
            time.sleep(REQUEST_DELAY)

        # ----- 4. Monologue transcripts (Hamilton commencement etc.) -----
        for url, slug, title in SINGJUPOST_MONOLOGUE_SOURCES:
            n = _ingest_monologue_transcript(
                client=client,
                url=url,
                slug=slug,
                title=title,
                f_out=f_out,
                raw_dir=raw_dir,
                seen=seen_paragraphs,
            )
            if n > 0:
                chunks_written += n
                sources_ok += 1
            else:
                sources_failed.append(slug)
            time.sleep(REQUEST_DELAY)

        # ----- 5. Wikipedia biography -----
        n = _ingest_wikipedia(
            client=client,
            url=WIKIPEDIA_URL,
            slug="wikipedia-bio",
            title="Wikipedia: Peter Thiel",
            f_out=f_out,
            raw_dir=raw_dir,
            seen=seen_paragraphs,
        )
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
            quote = _normalize(li.get_text(" ", strip=True))
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
        year = _parse_year(section)
        for i, chunk in enumerate(chunk_paragraphs(quotes, target_tokens=400)):
            record: Dict = {
                "id": f"thiel-wikiquote-{_slugify(section)}-{i:03d}",
                "expert_id": "thiel",
                "kind": "wikiquote",
                "section": section,
                "source_url": WIKIQUOTE_URL,
                "source_title": f"Wikiquote: Peter Thiel ({section})",
                "text": chunk,
            }
            if year is not None:
                record["year"] = year
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1

    print(f"  [wikiquote] {total_quotes:4d} quotes across {len(quotes_by_section)} sections -> {n} chunks")
    return n


# ==================
# Long-form essays
# ==================


def _ingest_essay(
    *,
    client: httpx.Client,
    url: str,
    slug: str,
    title: str,
    kind: str,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    """Pull prose paragraphs from an essay-style HTML page.

    Works for Cato Unbound, First Things, and Founders Fund — all three
    use a standard <article> / <main> / .entry-content container with
    the body in <p> tags.
    """
    try:
        resp = client.get(url)
    except httpx.HTTPError as e:
        print(f"  [{slug}] FAIL: {e}", file=sys.stderr)
        return 0

    if resp.status_code != 200:
        print(f"  [{slug}] HTTP {resp.status_code}, skipping")
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    article = (
        soup.find("article")
        or soup.find("div", class_="entry-content")
        or soup.find("main")
        or soup.find("body")
    )
    if article is None:
        return 0

    for tag in article.find_all(["script", "style", "nav", "aside", "header", "footer"]):
        tag.decompose()

    raw_paragraphs: List[str] = []
    for p in article.find_all("p"):
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

    if len(deduped) < 3:
        print(f"  [{slug}] only {len(deduped)} paragraphs, skipping")
        return 0

    (raw_dir / f"{slug}.txt").write_text(
        "\n\n".join(deduped), encoding="utf-8"
    )

    n = 0
    for i, chunk in enumerate(chunk_paragraphs(deduped)):
        record: Dict = {
            "id": f"thiel-{slug}-{i:03d}",
            "expert_id": "thiel",
            "kind": kind,
            "source_url": url,
            "source_title": title,
            "text": chunk,
        }
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        n += 1

    print(f"  [{slug}] {len(deduped):4d} paragraphs -> {n} chunks")
    return n


# ==================
# Singjupost Q&A transcripts (speaker-attributed)
# ==================


def _ingest_qa_transcript(
    *,
    client: httpx.Client,
    url: str,
    slug: str,
    title: str,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    """Extract Thiel's lines from a speaker-prefixed transcript."""
    try:
        resp = client.get(url)
    except httpx.HTTPError as e:
        print(f"  [{slug}] FAIL: {e}", file=sys.stderr)
        return 0

    if resp.status_code != 200:
        print(f"  [{slug}] HTTP {resp.status_code}, skipping")
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    article = (
        soup.find("article")
        or soup.find("div", class_="entry-content")
        or soup.find("main")
        or soup.find("body")
    )
    if article is None:
        return 0

    for tag in article.find_all(["script", "style", "nav", "aside", "header", "footer"]):
        tag.decompose()

    paragraphs = article.find_all("p")
    thiel_lines: List[str] = []
    in_thiel = False
    for p in paragraphs:
        raw = p.get_text(" ", strip=True)
        if not raw:
            continue
        m = THIEL_SPEAKER_PATTERN.match(raw)
        if m:
            line = _normalize(m.group(1))
            in_thiel = True
            if len(line) >= 40 and not _looks_like_boilerplate(line) and line not in seen:
                seen.add(line)
                thiel_lines.append(line)
            continue
        if OTHER_SPEAKER_PATTERN.match(raw):
            in_thiel = False
            continue
        if in_thiel:
            line = _normalize(raw)
            if len(line) >= 40 and not _looks_like_boilerplate(line) and line not in seen:
                seen.add(line)
                thiel_lines.append(line)

    if len(thiel_lines) < 5:
        # Either a dud transcript or a duplicate of one we already
        # ingested. Neither is a hard failure.
        print(f"  [{slug}] only {len(thiel_lines)} new Thiel lines (likely cross-post duplicate)")
        return 0

    (raw_dir / f"{slug}.txt").write_text(
        "\n\n".join(thiel_lines), encoding="utf-8"
    )

    n = 0
    for i, chunk in enumerate(chunk_paragraphs(thiel_lines)):
        record: Dict = {
            "id": f"thiel-{slug}-{i:03d}",
            "expert_id": "thiel",
            "kind": "transcript",
            "source_url": url,
            "source_title": title,
            "text": chunk,
        }
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        n += 1

    print(f"  [{slug}] {len(thiel_lines):4d} Thiel lines -> {n} chunks")
    return n


# ==================
# Monologue transcripts (no speaker prefix; whole article is Thiel)
# ==================


def _ingest_monologue_transcript(
    *,
    client: httpx.Client,
    url: str,
    slug: str,
    title: str,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    """Treat every prose paragraph in the article as Thiel-attributed.

    Only safe for genuinely solo-speech content (commencement
    addresses, prepared remarks). The first few paragraphs are usually
    editorial intro from the host site; we drop them via the boilerplate
    filter and short-paragraph filter, plus a 'first prose paragraph
    that exceeds N chars and looks like Thiel speaking' heuristic isn't
    needed because the boilerplate strings are stable across the site.
    """
    try:
        resp = client.get(url)
    except httpx.HTTPError as e:
        print(f"  [{slug}] FAIL: {e}", file=sys.stderr)
        return 0

    if resp.status_code != 200:
        print(f"  [{slug}] HTTP {resp.status_code}, skipping")
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    article = (
        soup.find("article")
        or soup.find("div", class_="entry-content")
        or soup.find("main")
        or soup.find("body")
    )
    if article is None:
        return 0

    for tag in article.find_all(["script", "style", "nav", "aside", "header", "footer"]):
        tag.decompose()

    raw_paragraphs: List[str] = []
    for p in article.find_all("p"):
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
        print(f"  [{slug}] only {len(deduped)} paragraphs, skipping")
        return 0

    (raw_dir / f"{slug}.txt").write_text(
        "\n\n".join(deduped), encoding="utf-8"
    )

    n = 0
    for i, chunk in enumerate(chunk_paragraphs(deduped)):
        record: Dict = {
            "id": f"thiel-{slug}-{i:03d}",
            "expert_id": "thiel",
            "kind": "speech",
            "source_url": url,
            "source_title": title,
            "text": chunk,
        }
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        n += 1

    print(f"  [{slug}] {len(deduped):4d} paragraphs (monologue) -> {n} chunks")
    return n


# ==================
# Wikipedia biography
# ==================


def _ingest_wikipedia(
    *,
    client: httpx.Client,
    url: str,
    slug: str,
    title: str,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  [{slug}] FAIL: {e}", file=sys.stderr)
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
        print(f"  [{slug}] only {len(deduped)} paragraphs, skipping")
        return 0

    (raw_dir / f"{slug}.txt").write_text(
        "\n\n".join(deduped), encoding="utf-8"
    )

    n = 0
    for i, chunk in enumerate(chunk_paragraphs(deduped)):
        record: Dict = {
            "id": f"thiel-{slug}-{i:03d}",
            "expert_id": "thiel",
            "kind": "biography",
            "source_url": url,
            "source_title": title,
            "text": chunk,
        }
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        n += 1

    print(f"  [{slug}] {len(deduped):4d} paragraphs -> {n} chunks")
    return n


# ==================
# Helpers
# ==================


def _clean_paragraphs(raw_paragraphs: Iterable[str]) -> Iterator[str]:
    for raw in raw_paragraphs:
        para = _normalize(raw)
        if not para:
            continue
        if len(para) < MIN_PARAGRAPH_CHARS:
            continue
        if _looks_like_boilerplate(para):
            continue
        if _looks_like_table(para):
            continue
        yield para


def _normalize(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _looks_like_boilerplate(para: str) -> bool:
    return any(p.search(para) for p in BOILERPLATE_PATTERNS)


def _looks_like_table(para: str) -> bool:
    non_space = [c for c in para if not c.isspace()]
    if not non_space:
        return True
    letters = sum(1 for c in non_space if c.isalpha())
    return letters / len(non_space) < 0.55


def _parse_year(heading: str) -> Optional[int]:
    m = re.match(r"^(\d{4})\b", heading.strip())
    if m:
        y = int(m.group(1))
        if 1990 <= y <= 2100:
            return y
    return None


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s or "section"


if __name__ == "__main__":
    raise SystemExit(main())
