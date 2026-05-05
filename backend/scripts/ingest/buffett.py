"""Scrape Berkshire Hathaway shareholder letters for Warren Buffett's corpus.

Source: https://www.berkshirehathaway.com/letters/letters.html

Letters from 1977 through 2003 are bare HTML with the entire body wrapped
in a single <pre> block. From 2004 onward they are PDFs, which we skip
for now — adding PDFs is a separate problem (and a separate dep).

Run from `backend/`:

    python -m scripts.ingest.buffett

Output:

    backend/data/buffett/
        chunks.jsonl       # one chunk per line, ready for embedding
        raw/<year>.txt     # cleaned plain text per letter, for debugging

Polite: 1.5s delay between letter fetches. Run takes ~1 minute.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Iterator, List

import httpx
from bs4 import BeautifulSoup

from scripts.ingest._chunking import chunk_paragraphs


BASE_URL = "https://www.berkshirehathaway.com/letters"
# 1977-1989, 1991-1996 are bare-HTML <pre>-block letters at <year>.html.
# 1990 and 1997 are also at <year>.html but use <p> tags (with a small
# data-table <pre> as an aside).
# 1998-1999 are at <year>htm.html and use <p> tags.
# 2000-2001 are at /<year>ar/<year>letter.html.
# 2002-2003 and 2004+ are PDF-only; we skip them. PDFs would require pypdf
# and double the demo's "is the corpus current" promise — unnecessary for
# the demo since pre-2002 already gives ~25 years of voice.
YEAR_URLS = {
    **{y: f"{BASE_URL}/{y}.html" for y in range(1977, 1998)},
    **{y: f"{BASE_URL}/{y}htm.html" for y in (1998, 1999)},
    2000: "https://www.berkshirehathaway.com/2000ar/2000letter.html",
    2001: "https://www.berkshirehathaway.com/2001ar/2001letter.html",
}
REQUEST_DELAY = 1.5
USER_AGENT = (
    # Sucuri (the CDN in front of berkshirehathaway.com) bounces obvious
    # bot UAs to a JS challenge page. A realistic browser UA gets the real
    # HTML through the cache. Brotli is also required — see requirements.txt.
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Paragraphs shorter than this are almost always section headers, dates,
# or fragments. Drop them.
MIN_PARAGRAPH_CHARS = 80

# Heuristic: drop paragraphs where < 60% of non-whitespace chars are
# letters. Catches space-aligned ASCII tables of financial figures.
MIN_LETTER_RATIO = 0.6

# Salutation and signature patterns to strip.
SIGNATURE_PATTERNS = [
    re.compile(r"^Warren E\.? Buffett", re.IGNORECASE),
    re.compile(r"^Chairman of the Board", re.IGNORECASE),
    re.compile(r"^To the Shareholders of Berkshire Hathaway", re.IGNORECASE),
]

# Cleanup of common cp1252-decoded artifacts that survive in older letters.
# These are the chars that show up where Buffett used hyphens, em-dashes,
# or other typography that round-trips poorly.
ARTIFACT_REPLACEMENTS = {
    "\u00be": "--",   # ¾ used as em-dash in some letters
    "\u0040": "@",    # @ stays @ but we strip the cluster below
    "\u0085": "...",  # NEL — Word's ellipsis substitute
    "\u00a0": " ",    # NBSP
}
# In some letters the at-sign cluster "@compensation" appears where
# "-compensation" or " compensation" was intended. Replace bare @ between
# letters with a space.
AT_BETWEEN_LETTERS = re.compile(r"(?<=[a-z])@(?=[a-z])", re.IGNORECASE)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    out_dir = repo_root / "backend" / "data" / "buffett"
    raw_dir = out_dir / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = out_dir / "chunks.jsonl"
    chunks_written = 0
    letters_ok = 0
    letters_failed: List[int] = []

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    ) as client, chunks_path.open("w", encoding="utf-8") as f_out:
        for year, url in YEAR_URLS.items():
            try:
                paragraphs = _fetch_and_parse(client, url)
            except Exception as e:
                print(f"  [{year}] FAIL: {e}", file=sys.stderr)
                letters_failed.append(year)
                time.sleep(REQUEST_DELAY)
                continue

            if not paragraphs:
                print(f"  [{year}] empty after cleaning, skipping", file=sys.stderr)
                letters_failed.append(year)
                time.sleep(REQUEST_DELAY)
                continue

            # Save cleaned plain text for debugging / repro.
            (raw_dir / f"{year}.txt").write_text(
                "\n\n".join(paragraphs), encoding="utf-8"
            )

            for i, chunk in enumerate(chunk_paragraphs(paragraphs)):
                record = {
                    "id": f"buffett-{year}-{i:03d}",
                    "expert_id": "buffett",
                    "year": year,
                    "source_url": url,
                    "source_title": f"Berkshire Hathaway {year} Shareholder Letter",
                    "text": chunk,
                }
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                chunks_written += 1

            print(f"  [{year}] {len(paragraphs):4d} paragraphs")
            letters_ok += 1
            time.sleep(REQUEST_DELAY)

    print()
    print(f"OK: {letters_ok} letters, {chunks_written} chunks -> {chunks_path}")
    if letters_failed:
        print(f"FAILED: {letters_failed}", file=sys.stderr)
        return 1
    return 0


# ==================
# HTML parsing
# ==================


def _fetch_and_parse(client: httpx.Client, url: str) -> List[str]:
    resp = client.get(url)
    resp.raise_for_status()
    # Letter pages have no charset declaration and use cp1252 punctuation
    # (curly quotes, em-dashes). Decode explicitly.
    html = resp.content.decode("cp1252", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    # Two layouts in use across years:
    #   A) 1977-1989, 1991-1996: a single <pre> block holds the whole letter,
    #      hard-wrapped, paragraphs separated by blank lines.
    #   B) 1990, 1997, 1998-2003: prose is in <p> tags. Sometimes a small
    #      <pre> exists too but only contains a column-aligned data table.
    # Try both, keep whichever produces more paragraphs.
    pre_paras = list(_clean_paragraphs(_text_from_pre(soup)))
    p_paras = list(_clean_paragraphs(_text_from_p_tags(soup)))

    return p_paras if len(p_paras) > len(pre_paras) else pre_paras


def _text_from_pre(soup: BeautifulSoup) -> str:
    pre = soup.find("pre")
    return pre.get_text() if pre else ""


def _text_from_p_tags(soup: BeautifulSoup) -> str:
    """Concatenate all <p> tag text with double-newlines so the paragraph
    splitter treats each <p> as one block.

    Some letters (e.g. 1999) put most of the body inside a single giant <p>
    with internal paragraph breaks marked by runs of whitespace/newlines.
    Use separator='\\n' on get_text so those breaks survive, then let
    _clean_paragraphs split on blank lines.
    """
    body = soup.find("body")
    if body is None:
        return ""
    paras = []
    for p in body.find_all("p"):
        # separator='\n' preserves internal line breaks so a multi-paragraph
        # <p> still gets split downstream. _normalize will collapse runs of
        # single newlines within the same paragraph back to spaces.
        text = p.get_text(separator="\n").strip()
        if text:
            paras.append(text)
    return "\n\n".join(paras)


def _clean_paragraphs(raw: str) -> Iterator[str]:
    """Yield prose paragraphs from a letter body.

    Letters are hard-wrapped (~65 cols) inside the <pre>. Paragraphs are
    separated by blank lines. Each paragraph may have leading/trailing
    whitespace and internal newlines we want to collapse.
    """
    for block in re.split(r"\n\s*\n", raw):
        para = _normalize(block)
        if not para:
            continue
        if len(para) < MIN_PARAGRAPH_CHARS:
            continue
        if _looks_like_signature(para):
            continue
        if _looks_like_table(para):
            continue
        yield para


def _normalize(block: str) -> str:
    # Apply artifact replacements first.
    for src, dst in ARTIFACT_REPLACEMENTS.items():
        block = block.replace(src, dst)
    block = AT_BETWEEN_LETTERS.sub("-", block)
    # Collapse internal newlines and runs of whitespace.
    text = re.sub(r"\s+", " ", block).strip()
    return text


def _looks_like_signature(para: str) -> bool:
    return any(p.search(para) for p in SIGNATURE_PATTERNS)


def _looks_like_table(para: str) -> bool:
    """Drop paragraphs dominated by digits, dashes, and column whitespace."""
    if not para:
        return True
    non_space = [c for c in para if not c.isspace()]
    if not non_space:
        return True
    letters = sum(1 for c in non_space if c.isalpha())
    return letters / len(non_space) < MIN_LETTER_RATIO


if __name__ == "__main__":
    raise SystemExit(main())
