"""Scrape Larry Fink's public corpus for the BlackRock CEO persona.

Fink doesn't have a single clean archive like Berkshire's letters, so we
assemble three complementary sources:

1. BlackRock Annual Letter to CEOs (2012, 2014-2022). His most-cited
   public writing. Same letter, same domain, year-prefixed URL slug.
2. BlackRock Annual Chairman's Letter to Investors (2023-present).
   In 2023 the CEO letter was renamed and split, with the investor-
   facing version published as the "Chairman's Letter." Same voice,
   different audience framing.
3. Wikipedia biography. Biographical context (career arc, BlackRock's
   scale, Aladdin, controversies) so the model can ground identity-
   level questions, not just policy positions.

Run from `backend/`:

    python -m scripts.ingest.fink

Output:

    backend/data/fink/
        chunks.jsonl              # one chunk per line, ready for embedding
        raw/<slug>.txt            # cleaned plain text per source

Polite: 1.5s delay between fetches.

Notes:
- BlackRock pages are React-rendered but the prose is also present in the
  initial HTML (server-rendered), so plain BS4 parsing works; no headless
  browser needed.
- Letters share recurring sidebars ("Mega forces are big, structural
  changes...") that we dedupe by exact-match across years before writing
  chunks.
- Each source is independent. If one fails, the others still produce a
  usable corpus. The only hard failure is producing zero chunks total.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple

import httpx
from bs4 import BeautifulSoup

from scripts.ingest._chunking import chunk_paragraphs


# ==================
# Source catalog
# ==================

# BlackRock CEO letters: the original "Letter to CEOs" series.
# 2013 was never published (404s on the canonical slug). 2023+ replaced
# this series with the Chairman's letter (handled separately below).
CEO_LETTER_YEARS = [2012, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022]
CEO_LETTER_URL = (
    "https://www.blackrock.com/corporate/investor-relations/"
    "{year}-larry-fink-ceo-letter"
)

# BlackRock Annual Chairman's Letter to Investors: the post-2022 series.
# 2025 may not yet be published when this script runs; non-200s are
# tolerated and skipped.
CHAIRMAN_LETTER_YEARS = [2023, 2024, 2025]
CHAIRMAN_LETTER_URL = (
    "https://www.blackrock.com/corporate/investor-relations/"
    "{year}-larry-fink-annual-chairmans-letter"
)

# Wikipedia biography. Pulled from the rendered article body, not the
# Wikipedia API, because we want clean prose paragraphs and the article
# HTML keeps them in <p> tags inside #mw-content-text.
WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Larry_Fink"


# ==================
# HTTP / parsing config
# ==================

REQUEST_DELAY = 1.5
USER_AGENT = (
    # Realistic UA. BlackRock and Wikipedia both serve plain HTML to a
    # browser-shaped UA without challenge pages.
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Paragraphs shorter than this are typically headings, captions, or UI
# strings ("Read the full letter," "Download PDF").
MIN_PARAGRAPH_CHARS = 100

# We need at least this many qualifying paragraphs to consider a fetch
# successful. Custom 404 pages and bare-shell React errors come back with
# 1-2 navigation paragraphs and trip this guard.
MIN_PARAGRAPHS_PER_LETTER = 5

# Boilerplate strings to drop. These are nav/UI/legal lines that survive
# paragraph filtering because they are long enough.
BOILERPLATE_PATTERNS = [
    re.compile(r"^©\s*\d{4}\s*BlackRock", re.IGNORECASE),
    re.compile(r"^Prepared by BlackRock", re.IGNORECASE),
    re.compile(r"^This material.*BlackRock", re.IGNORECASE),
    re.compile(r"^The opinions expressed", re.IGNORECASE),
    re.compile(r"^Past performance is not", re.IGNORECASE),
    re.compile(r"^Capital at risk", re.IGNORECASE),
    re.compile(r"^Investing involves risks", re.IGNORECASE),
    re.compile(r"^All financial investments", re.IGNORECASE),
    # Wikipedia-specific cruft.
    re.compile(r"^From Wikipedia", re.IGNORECASE),
    re.compile(r"^This article", re.IGNORECASE),
    re.compile(r"^\[edit\]"),
]

# Recurring sidebar across multiple years' chairman letters. We drop
# exact duplicates anyway, but flagging this one helps reduce noise.
KNOWN_SIDEBARS = {
    "Mega forces are big, structural changes that affect investing now - "
    "and far in the future. This creates major opportunities - and risks - "
    "for investors.",
}


# ==================
# Entry point
# ==================


def main() -> int:
    repo_backend = Path(__file__).resolve().parents[2]
    out_dir = repo_backend / "data" / "fink"
    raw_dir = out_dir / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = out_dir / "chunks.jsonl"
    chunks_written = 0
    sources_ok = 0
    sources_failed: List[str] = []

    # Track exact-match paragraphs across every source so the recurring
    # sidebars don't appear in the index three or four times. We hash on
    # the cleaned paragraph text after `_normalize`.
    seen_paragraphs: set[str] = set(KNOWN_SIDEBARS)

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    ) as client, chunks_path.open("w", encoding="utf-8") as f_out:

        # ----- BlackRock CEO letters -----
        for year in CEO_LETTER_YEARS:
            url = CEO_LETTER_URL.format(year=year)
            slug = f"ceo-letter-{year}"
            title = f"BlackRock {year} Annual Letter to CEOs"
            n = _ingest_html(
                client=client,
                url=url,
                slug=slug,
                title=title,
                year=year,
                kind="ceo_letter",
                f_out=f_out,
                raw_dir=raw_dir,
                seen=seen_paragraphs,
                parser=_parse_blackrock,
            )
            if n > 0:
                chunks_written += n
                sources_ok += 1
            else:
                sources_failed.append(slug)
            time.sleep(REQUEST_DELAY)

        # ----- BlackRock Chairman's letters -----
        for year in CHAIRMAN_LETTER_YEARS:
            url = CHAIRMAN_LETTER_URL.format(year=year)
            slug = f"chairmans-letter-{year}"
            title = f"BlackRock {year} Annual Chairman's Letter to Investors"
            n = _ingest_html(
                client=client,
                url=url,
                slug=slug,
                title=title,
                year=year,
                kind="chairmans_letter",
                f_out=f_out,
                raw_dir=raw_dir,
                seen=seen_paragraphs,
                parser=_parse_blackrock,
            )
            if n > 0:
                chunks_written += n
                sources_ok += 1
            else:
                sources_failed.append(slug)
            time.sleep(REQUEST_DELAY)

        # ----- Wikipedia biography -----
        n = _ingest_html(
            client=client,
            url=WIKIPEDIA_URL,
            slug="wikipedia",
            title="Wikipedia: Larry Fink",
            year=None,
            kind="biography",
            f_out=f_out,
            raw_dir=raw_dir,
            seen=seen_paragraphs,
            parser=_parse_wikipedia,
        )
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            sources_failed.append("wikipedia")

    print()
    print(f"OK: {sources_ok} sources, {chunks_written} chunks -> {chunks_path}")
    if sources_failed:
        print(f"SKIPPED/FAILED: {sources_failed}", file=sys.stderr)
    if chunks_written == 0:
        print("ERR: zero chunks written; not viable as a corpus.", file=sys.stderr)
        return 1
    return 0


# ==================
# Per-source ingestion
# ==================


def _ingest_html(
    *,
    client: httpx.Client,
    url: str,
    slug: str,
    title: str,
    year: int | None,
    kind: str,
    f_out,
    raw_dir: Path,
    seen: set[str],
    parser,
) -> int:
    """Fetch one HTML source, parse it, and write its chunks to f_out.

    Returns the number of chunks written for this source. Zero means the
    source failed or produced too little content; the caller decides how
    to react.
    """
    try:
        resp = client.get(url)
    except httpx.HTTPError as e:
        print(f"  [{slug}] FAIL: {e}", file=sys.stderr)
        return 0

    if resp.status_code != 200:
        print(f"  [{slug}] HTTP {resp.status_code}, skipping")
        return 0

    try:
        paragraphs = parser(resp.text)
    except Exception as e:  # parser robustness: never let one source kill the run
        print(f"  [{slug}] parse FAIL: {e}", file=sys.stderr)
        return 0

    # Apply cross-source dedupe.
    deduped: List[str] = []
    for p in paragraphs:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)

    if len(deduped) < MIN_PARAGRAPHS_PER_LETTER:
        print(
            f"  [{slug}] only {len(deduped)} paragraphs after cleaning, skipping"
        )
        return 0

    # Save cleaned plain text for debugging / repro.
    (raw_dir / f"{slug}.txt").write_text(
        "\n\n".join(deduped), encoding="utf-8"
    )

    n = 0
    for i, chunk in enumerate(chunk_paragraphs(deduped)):
        record: Dict = {
            "id": f"fink-{slug}-{i:03d}",
            "expert_id": "fink",
            "kind": kind,
            "source_url": url,
            "source_title": title,
            "text": chunk,
        }
        if year is not None:
            record["year"] = year
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        n += 1

    print(f"  [{slug}] {len(deduped):4d} paragraphs -> {n} chunks")
    return n


# ==================
# Site-specific parsers
# ==================


def _parse_blackrock(html: str) -> List[str]:
    """Extract prose paragraphs from a BlackRock investor-relations page.

    Letters live in the page body wrapped in <p> tags, mixed in with nav
    and footer paragraphs. We pull every <p> from inside <main> if it
    exists, otherwise the whole <body>, then filter via _clean_paragraphs.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Strip nav/aside/script/style outright so their text never enters the
    # paragraph list.
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    container = soup.find("main") or soup.find("body") or soup
    raw_paragraphs: List[str] = []
    for p in container.find_all("p"):
        text = p.get_text(separator=" ").strip()
        if text:
            raw_paragraphs.append(text)

    return list(_clean_paragraphs(raw_paragraphs))


def _parse_wikipedia(html: str) -> List[str]:
    """Extract prose paragraphs from the Larry Fink Wikipedia article.

    Wikipedia keeps article body inside #mw-content-text. We avoid the
    infobox and reference list by only walking <p> tags directly.
    """
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find("div", {"id": "mw-content-text"})
    if content is None:
        return []

    # Drop reference numbers, edit links, infobox tables.
    for tag in content.find_all(["sup", "table", "style"]):
        tag.decompose()

    raw_paragraphs: List[str] = []
    for p in content.find_all("p"):
        text = p.get_text(separator=" ").strip()
        if text:
            raw_paragraphs.append(text)

    return list(_clean_paragraphs(raw_paragraphs))


# ==================
# Paragraph cleaning
# ==================


def _clean_paragraphs(raw_paragraphs: Iterable[str]) -> Iterator[str]:
    """Yield prose paragraphs after normalization and quality filters."""
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
    """Collapse whitespace, normalize NBSPs, trim."""
    text = text.replace("\u00a0", " ")  # NBSP -> space
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _looks_like_boilerplate(para: str) -> bool:
    return any(p.search(para) for p in BOILERPLATE_PATTERNS)


def _looks_like_table(para: str) -> bool:
    """Drop paragraphs dominated by digits and punctuation rather than prose."""
    non_space = [c for c in para if not c.isspace()]
    if not non_space:
        return True
    letters = sum(1 for c in non_space if c.isalpha())
    return letters / len(non_space) < 0.55


if __name__ == "__main__":
    raise SystemExit(main())
