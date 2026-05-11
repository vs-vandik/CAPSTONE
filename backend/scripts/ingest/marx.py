"""Scrape Marx's core economic and political writings for the Marx persona.

Sources (all from marxists.org, the canonical online archive):

1. The Communist Manifesto (1848). Preface + 4 chapters.
   Translator: Samuel Moore in cooperation with Engels, 1888 English edition,
   proofed against original by Andy Blunden 2004.
2. Capital, Volume I (1867). 33 chapters + appendix.
   Translator: Samuel Moore and Edward Aveling, edited by Engels.
3. Wage Labour and Capital (1847, pub. 1849, repub. 1891).
   Engels-edited, 9 chapters.
4. Value, Price and Profit (1865, pub. 1898). Speech to the First
   International. 14 sections across 3 pages.
5. Critique of the Gotha Programme (1875). 4 parts + appendix.
6. Theses on Feuerbach (1845). All 11 theses on one page (Cyril Smith
   2002 translation).
7. Economic and Philosophic Manuscripts of 1844. Multiple manuscript
   pages.
8. Wikipedia biography. Career arc, intellectual context, reception.

Why these and not the rest of MECW: this is the economic-and-political
core that a finance debate is most likely to touch (commodity, labor,
value, surplus value, accumulation, alienation, communism's two phases).
Volumes II and III of Capital, the Grundrisse, and the early journalism
are excluded by design to keep the corpus focused and the index small.

Run from `backend/`:

    python -m scripts.ingest.marx

Output:

    backend/data/marx/
        chunks.jsonl               # one chunk per line, ready for embedding
        raw/<slug>.txt             # cleaned plain text per source

Polite: 1.5s delay between fetches.

Notes:
- marxists.org pages are static HTML with prose in <p> tags inside a
  <div class="border"> wrapper. Plain BeautifulSoup parsing is enough;
  no JS rendering needed.
- Pages are served as iso-8859-1 with cp1252-style smart quotes. We
  decode explicitly so curly quotes / em-dashes / German umlauts come
  out clean.
- TOC entries, citation blocks, footers, and endnote markers are
  filtered by CSS class (`information`, `footer`, `title`, `toc`,
  `index`, `pagenote`). Endnote superscripts are decomposed before
  text extraction so "(1)"-style references don't leak in.
- Each source is independent. If one URL 404s the others still
  produce a usable corpus. Hard failure only if the whole run yields
  zero chunks.
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List

import httpx
from bs4 import BeautifulSoup

from scripts.ingest._chunking import chunk_paragraphs


BASE = "https://www.marxists.org/archive/marx/works"


# ==================
# Source catalog
# ==================


@dataclass(frozen=True)
class Source:
    slug: str            # filename-safe id, used for raw/<slug>.txt and chunk ids
    title: str           # human-readable source title for citations
    kind: str            # bucket label kept on each chunk record
    year: int | None     # publication year (or None for biography)
    url: str             # canonical fetch URL
    parser: str          # "marxists" or "wikipedia"


# Manifesto: index page is metadata only; prose lives in ch01-ch04 and
# preface.htm. Chapter 1 also includes the 4-paragraph preamble.
MANIFESTO_PAGES = [
    ("preface", "Preface"),
    ("ch01", "Chapter 1: Bourgeois and Proletarians"),
    ("ch02", "Chapter 2: Proletarians and Communists"),
    ("ch03", "Chapter 3: Socialist and Communist Literature"),
    ("ch04", "Chapter 4: Position of the Communists"),
]


# Capital Vol. I: 33 numbered chapters + part0 (prefaces) + appendix
# (Value-Form). part0 contains Marx's various prefaces; useful voice
# context but heavy on Engels editorial matter, so we keep it but the
# parser drops Engels-bracketed sections via the boilerplate filter.
CAPITAL_PAGES = (
    [("part0", "Prefaces and Afterwords")]
    + [(f"ch{n:02d}", f"Chapter {n}") for n in range(1, 34)]
    + [("appendix", "Appendix: The Value-Form")]
)


# Wage Labour and Capital: 1847 directory with intro + 9 chapters.
WAGE_LABOUR_PAGES = [
    ("intro", "Introduction (Engels 1891)"),
    ("ch01", "Preliminary"),
    ("ch02", "What are wages?"),
    ("ch03", "By what is the price of a commodity determined?"),
    ("ch04", "By what are wages determined?"),
    ("ch05", "The nature and growth of capital"),
    ("ch06", "Relation of wage-labor to capital"),
    ("ch07", "The general law of wages and profit"),
    ("ch08", "The interests of capital and wage-labor are opposed"),
    ("ch09", "Effect of capitalist competition"),
]


# Value, Price and Profit: 14 sections packed into 3 chapter pages.
VPP_PAGES = [
    ("preface", "Preface (Edward Aveling)"),
    ("ch01", "Sections 1-5: Production, Wages, Currency, Demand"),
    ("ch02", "Sections 6-11: Value, Labour, Surplus Value"),
    ("ch03", "Sections 12-14: Profits, Wages, Capital and Labour"),
]


# Critique of the Gotha Programme: foreword + 4 parts + appendix.
GOTHA_PAGES = [
    ("foreword", "Foreword (Engels 1891)"),
    ("ch01", "Part I"),
    ("ch02", "Part II"),
    ("ch03", "Part III"),
    ("ch04", "Part IV"),
    ("append", "Appendix"),
]


# 1844 Manuscripts: split across many short pages. We pull the ones with
# substantive prose; the index/contents page itself is skipped.
EPM_1844_PAGES = [
    ("preface", "Preface"),
    ("wages", "Wages of Labour"),
    ("capital", "Profit of Capital"),
    ("rent", "Rent of Land"),
    ("labour", "Estranged Labour"),
    ("second", "Antithesis of Capital and Labour"),
    ("third", "Private Property and Labour"),
    ("comm", "Private Property and Communism"),
    ("needs", "Human Needs and Division of Labour"),
    ("power", "The Power of Money"),
    ("hegel", "Critique of the Hegelian Dialectic"),
]


def _build_sources() -> List[Source]:
    out: List[Source] = []

    # Manifesto
    for slug, title in MANIFESTO_PAGES:
        out.append(Source(
            slug=f"manifesto-{slug}",
            title=f"The Communist Manifesto (1848): {title}",
            kind="manifesto",
            year=1848,
            url=f"{BASE}/1848/communist-manifesto/{slug}.htm",
            parser="marxists",
        ))

    # Capital Vol. I
    for slug, title in CAPITAL_PAGES:
        out.append(Source(
            slug=f"capital-v1-{slug}",
            title=f"Capital, Volume I (1867): {title}",
            kind="capital_v1",
            year=1867,
            url=f"{BASE}/1867-c1/{slug}.htm",
            parser="marxists",
        ))

    # Wage Labour and Capital
    for slug, title in WAGE_LABOUR_PAGES:
        out.append(Source(
            slug=f"wage-labour-{slug}",
            title=f"Wage Labour and Capital (1847): {title}",
            kind="wage_labour",
            year=1847,
            url=f"{BASE}/1847/wage-labour/{slug}.htm",
            parser="marxists",
        ))

    # Value, Price and Profit
    for slug, title in VPP_PAGES:
        out.append(Source(
            slug=f"vpp-{slug}",
            title=f"Value, Price and Profit (1865): {title}",
            kind="value_price_profit",
            year=1865,
            url=f"{BASE}/1865/value-price-profit/{slug}.htm",
            parser="marxists",
        ))

    # Critique of the Gotha Programme
    for slug, title in GOTHA_PAGES:
        out.append(Source(
            slug=f"gotha-{slug}",
            title=f"Critique of the Gotha Programme (1875): {title}",
            kind="gotha",
            year=1875,
            url=f"{BASE}/1875/gotha/{slug}.htm",
            parser="marxists",
        ))

    # Theses on Feuerbach (single-page work)
    out.append(Source(
        slug="theses-feuerbach",
        title="Theses on Feuerbach (1845)",
        kind="theses_feuerbach",
        year=1845,
        url=f"{BASE}/1845/theses/theses.htm",
        parser="marxists",
    ))

    # 1844 Manuscripts
    for slug, title in EPM_1844_PAGES:
        out.append(Source(
            slug=f"epm-1844-{slug}",
            title=f"Economic and Philosophic Manuscripts of 1844: {title}",
            kind="epm_1844",
            year=1844,
            url=f"{BASE}/1844/manuscripts/{slug}.htm",
            parser="marxists",
        ))

    # Wikipedia biography
    out.append(Source(
        slug="wikipedia",
        title="Wikipedia: Karl Marx",
        kind="biography",
        year=None,
        url="https://en.wikipedia.org/wiki/Karl_Marx",
        parser="wikipedia",
    ))

    return out


# ==================
# HTTP / parsing config
# ==================

REQUEST_DELAY = 1.5
USER_AGENT = (
    # marxists.org and Wikipedia both serve plain HTML to a browser-shaped
    # UA without challenge pages.
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Paragraphs shorter than this are usually section headers ("Chapter 1"),
# date stamps, or fragmentary editorial notes.
MIN_PARAGRAPH_CHARS = 100

# Below this many qualifying paragraphs after cleaning, we treat the
# fetch as a dud (custom 404 pages, near-empty preface stubs, etc.).
# Lower than the Fink threshold because some Marx pages are genuinely
# short (single theses, brief prefaces).
MIN_PARAGRAPHS_PER_SOURCE = 3

# CSS classes on <p> tags that mark non-prose elements on marxists.org.
# We skip these wholesale rather than rely on text-level heuristics.
SKIP_P_CLASSES = {
    "information",   # citation block, transcription credits
    "footer",        # nav links at the bottom
    "title",         # breadcrumb at top
    "toc",           # table-of-contents header
    "index",         # table-of-contents entries
    "indentb",       # indented TOC entries (also some genuine prose -- see _looks_like_toc)
    "indentc",       # deeply-indented TOC entries
    "pagenote",      # admin/volunteer footer
    "skip",          # whitespace spacers
    "fst",           # "first" class -- usually genuine prose, kept
}
# `fst` and `indentb` overlap with real prose in some files. We keep them
# in via the explicit allow-list below and rely on _looks_like_toc to
# reject the obvious table-of-contents cases.
ALLOW_P_CLASSES = {"fst", "indentb"}
SKIP_P_CLASSES -= ALLOW_P_CLASSES

# Boilerplate substrings that survive paragraph-length filtering.
BOILERPLATE_PATTERNS = [
    re.compile(r"^Source:", re.IGNORECASE),
    re.compile(r"^Translated:", re.IGNORECASE),
    re.compile(r"^Transcribed:", re.IGNORECASE),
    re.compile(r"^Transcription", re.IGNORECASE),
    re.compile(r"^Proofed:", re.IGNORECASE),
    re.compile(r"^HTML Mark", re.IGNORECASE),
    re.compile(r"^First Published", re.IGNORECASE),
    re.compile(r"^Online Version", re.IGNORECASE),
    re.compile(r"^Copyleft:", re.IGNORECASE),
    re.compile(r"^Permission is granted to copy", re.IGNORECASE),
    re.compile(r"^Marx/Engels Internet Archive", re.IGNORECASE),
    re.compile(r"^Table of Contents", re.IGNORECASE),
    re.compile(r"^Contents$", re.IGNORECASE),
    re.compile(r"^Background$", re.IGNORECASE),
    re.compile(r"^From Wikipedia"),
    re.compile(r"^This article"),
    re.compile(r"^\[edit\]"),
]


# ==================
# Entry point
# ==================


def main() -> int:
    repo_backend = Path(__file__).resolve().parents[2]
    out_dir = repo_backend / "data" / "marx"
    raw_dir = out_dir / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = out_dir / "chunks.jsonl"
    chunks_written = 0
    sources_ok = 0
    sources_failed: List[str] = []

    # Cross-source dedupe. The same Engels-authored prefatory note appears
    # across multiple Marx editions; the canonical "All hitherto existing
    # society..." sentence opens both Manifesto ch01 and is requoted in
    # other works. Drop exact-match paragraphs after the first occurrence.
    seen_paragraphs: set[str] = set()

    sources = _build_sources()

    parsers: Dict[str, Callable[[str], List[str]]] = {
        "marxists": _parse_marxists,
        "wikipedia": _parse_wikipedia,
    }

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    ) as client, chunks_path.open("w", encoding="utf-8") as f_out:

        for src in sources:
            parser = parsers[src.parser]
            n = _ingest_html(
                client=client,
                src=src,
                f_out=f_out,
                raw_dir=raw_dir,
                seen=seen_paragraphs,
                parser=parser,
            )
            if n > 0:
                chunks_written += n
                sources_ok += 1
            else:
                sources_failed.append(src.slug)
            time.sleep(REQUEST_DELAY)

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
    src: Source,
    f_out,
    raw_dir: Path,
    seen: set[str],
    parser: Callable[[str], List[str]],
) -> int:
    try:
        resp = client.get(src.url)
    except httpx.HTTPError as e:
        print(f"  [{src.slug}] FAIL: {e}", file=sys.stderr)
        return 0

    if resp.status_code != 200:
        print(f"  [{src.slug}] HTTP {resp.status_code}, skipping")
        return 0

    # marxists.org pages declare iso-8859-1 but the actual byte content
    # uses cp1252 punctuation (curly quotes, em-dashes, ellipses). cp1252
    # is a superset; decoding as cp1252 round-trips both.
    try:
        html = resp.content.decode("cp1252", errors="replace")
    except Exception:
        html = resp.text  # fallback to httpx's own decode

    try:
        paragraphs = parser(html)
    except Exception as e:
        print(f"  [{src.slug}] parse FAIL: {e}", file=sys.stderr)
        return 0

    # Cross-source dedupe.
    deduped: List[str] = []
    for p in paragraphs:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)

    if len(deduped) < MIN_PARAGRAPHS_PER_SOURCE:
        print(
            f"  [{src.slug}] only {len(deduped)} paragraphs after cleaning, skipping"
        )
        return 0

    (raw_dir / f"{src.slug}.txt").write_text(
        "\n\n".join(deduped), encoding="utf-8"
    )

    n = 0
    for i, chunk in enumerate(chunk_paragraphs(deduped)):
        record: Dict = {
            "id": f"marx-{src.slug}-{i:03d}",
            "expert_id": "marx",
            "kind": src.kind,
            "source_url": src.url,
            "source_title": src.title,
            "text": chunk,
        }
        if src.year is not None:
            record["year"] = src.year
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        n += 1

    print(f"  [{src.slug}] {len(deduped):4d} paragraphs -> {n} chunks")
    return n


# ==================
# Site-specific parsers
# ==================


def _parse_marxists(html: str) -> List[str]:
    """Extract prose paragraphs from a marxists.org work page.

    Pages share a layout: the work body lives inside `<div class="border">`
    (or, on a few older pages, inside `<body>` directly). Within that,
    prose is in `<p>` tags. Non-prose `<p>` elements are tagged with
    CSS classes (`information`, `footer`, `title`, `toc`, etc.) which
    we filter on.

    Endnote markers (`<sup class="enote">`) and German-language asides
    (`<span class="context">`) are decomposed before text extraction so
    they don't pollute the prose.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Strip nav/script/style globally.
    for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    # Strip endnote superscripts and the "context" spans (German originals,
    # editorial brackets) that pad otherwise clean prose.
    for tag in soup.find_all("sup", class_="enote"):
        tag.decompose()
    for tag in soup.find_all("span", class_="context"):
        tag.decompose()
    for tag in soup.find_all("span", class_="inote"):
        tag.decompose()

    # Drop horizontal rules and standalone anchors that get caught up in
    # paragraph traversal.
    for tag in soup.find_all(["hr", "br"]):
        tag.decompose()

    # Prefer the `<div class="border">` content block; fall back to body.
    container = soup.find("div", class_="border") or soup.find("body") or soup

    raw_paragraphs: List[str] = []
    for p in container.find_all("p"):
        classes = set(p.get("class") or [])
        if classes & SKIP_P_CLASSES:
            continue
        text = p.get_text(separator=" ").strip()
        if not text:
            continue
        # Numbered-thesis pages (Theses on Feuerbach) have <h3>1</h3>
        # before each <p>. We don't capture the heading; the prose alone
        # is enough.
        raw_paragraphs.append(text)

    return list(_clean_paragraphs(raw_paragraphs))


def _parse_wikipedia(html: str) -> List[str]:
    """Extract prose paragraphs from the Karl Marx Wikipedia article."""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find("div", {"id": "mw-content-text"})
    if content is None:
        return []

    for tag in content.find_all(["sup", "table", "style", "script"]):
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
    for raw in raw_paragraphs:
        para = _normalize(raw)
        if not para:
            continue
        if len(para) < MIN_PARAGRAPH_CHARS:
            continue
        if _looks_like_boilerplate(para):
            continue
        if _looks_like_toc(para):
            continue
        if _looks_like_table(para):
            continue
        yield para


def _normalize(text: str) -> str:
    """Collapse whitespace, normalize NBSPs and Unicode artifacts."""
    text = text.replace("\u00a0", " ")
    # marxists.org occasionally has raw HTML entities surviving as text.
    text = text.replace("\u00ad", "")  # soft hyphen
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _looks_like_boilerplate(para: str) -> bool:
    return any(p.search(para) for p in BOILERPLATE_PATTERNS)


def _looks_like_toc(para: str) -> bool:
    """Catch indentb paragraphs that are actually TOC chapter listings.

    A TOC entry is mostly chapter labels separated by " | " or newlines,
    and has very few sentence terminators. Real prose has multiple
    periods/commas per 100 chars; TOCs have almost none.
    """
    if "Chapter" in para and para.count("Chapter") >= 3:
        return True
    if para.count(" | ") >= 2:
        return True
    # Prose has roughly 1 period per ~150 chars; a TOC has none.
    if len(para) > 200 and para.count(".") <= 1 and para.count(",") <= 1:
        return True
    return False


def _looks_like_table(para: str) -> bool:
    """Drop paragraphs dominated by digits and punctuation rather than prose."""
    non_space = [c for c in para if not c.isspace()]
    if not non_space:
        return True
    letters = sum(1 for c in non_space if c.isalpha())
    return letters / len(non_space) < 0.55


if __name__ == "__main__":
    raise SystemExit(main())
