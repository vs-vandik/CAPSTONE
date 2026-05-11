"""Scrape Elon Musk's public corpus.

Musk has no clean single archive like Berkshire's letters or BlackRock's
Chairman's letters. His public output is fragmented across tweets,
podcast interviews, biography articles, and corporate communications,
with the obvious giant primary source — twitter.com/elonmusk — locked
behind paid X API access. We work around that by assembling many
secondary sources that quote him verbatim.

Sources, in rough order of voice fidelity:

1. Kaggle dataset "Elon Musk Tweets 2010 to 2025 (March)" by dadalyndell:
   https://www.kaggle.com/datasets/dadalyndell/elon-musk-tweets-2010-to-2025-march
   The full @elonmusk archive that the X API would have given us, only
   in CSV form. Manual download required (Kaggle requires login). Place
   the CSV at `backend/data/musk/raw/elon_musk_tweets.csv` before running
   this script. We filter to original tweets and quote-tweets (drop
   replies and pure retweets), then bucket by year and pack the year's
   tweets into chunks. This source is optional: if the CSV is missing
   the script logs a warning and falls back to the other sources.
2. Wikiquote (en.wikiquote.org/wiki/Elon_Musk). ~300 sourced verbatim
   quotes organized chronologically by year (2005-present). Higher
   editorial signal than the raw tweet stream — Wikiquote curators have
   already picked the durable quotes — and includes non-tweet quotes
   from interviews and earnings calls.
3. Lex Fridman podcast transcripts (#1-#4). Speaker-attributed
   transcripts; we filter to only Musk's segments. Hours of recent
   first-person speech on AI, autonomy, Mars, social media, and politics.
4. Singjupost interview transcripts (Joe Rogan #1470).
5. Wikipedia: Elon Musk. Biography paragraphs for context.
6. Wikipedia: Views of Elon Musk. ~100 paragraphs of his political,
   economic, and AI-policy positions, quoting him heavily.

xcancel.com (a Nitter mirror of @elonmusk's recent timeline) was
previously used as a best-effort recent-tweets source. The Kaggle
dataset supersedes it: it covers 2010 through March 2025 in full,
without rate limits or mirror flakiness. The xcancel parser is
deleted along with the live HTTP path.

Run from `backend/`:

    python -m scripts.ingest.musk

Output:

    backend/data/musk/
        chunks.jsonl          # one chunk per line, ready for embedding
        raw/<slug>.txt        # cleaned plain text per source

Polite: 1.5s delay between fetches.

Notes:
- Each source is independent. The run continues if one fails; we only
  fail hard if zero chunks total are produced.
- Wikiquote individual quotes are short (often 1-3 sentences). We pack
  many quotes per chunk via the existing chunk_paragraphs packer so the
  retriever has prose-sized context to embed.
- Tweets from the Kaggle CSV are bucketed by year and packed by the
  same chunker so each chunk holds a thematically-coherent batch.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

import httpx
from bs4 import BeautifulSoup

from scripts.ingest._chunking import chunk_paragraphs


# ==================
# Source catalog
# ==================

WIKIQUOTE_URL = "https://en.wikiquote.org/wiki/Elon_Musk"
WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Elon_Musk"
WIKIPEDIA_VIEWS_URL = "https://en.wikipedia.org/wiki/Views_of_Elon_Musk"

# Wikiquote sections to *exclude*. Everything after these headings is
# quotes by other people about Musk, not his own words.
WIKIQUOTE_SKIP_SECTIONS = {
    "Quotes about Musk",
    "External links",
    "See also",
    "References",
    "Notes",
}

# Lex Fridman transcript URLs. Each conversation is multi-hour and
# yields hundreds of Musk-attributed segments. Only the ones that
# returned 200 with a real transcript at probe time are listed; the
# earlier Musk episodes (#1-#3) have episode pages but no hosted
# transcripts.
LEX_TRANSCRIPT_URLS = [
    # #400 (2023): Musk solo on war, AI, aliens, politics, physics.
    "https://lexfridman.com/elon-musk-4-transcript",
    # Musk + Neuralink team (2024): heavy on neurotech, AI, autonomy.
    "https://lexfridman.com/elon-musk-and-neuralink-team-transcript",
]

# Singjupost transcripts are full-text "Speaker: line" interview
# transcripts of widely-circulated podcast appearances. We extract
# only Musk's lines.
SINGJUPOST_URLS = [
    # Joe Rogan Experience #1470 (May 2020), the famous COVID-era
    # conversation. ~3 hours, lots of Musk speech on first principles,
    # autonomy, Mars, AI, social media.
    (
        "https://singjupost.com/elon-musk-on-the-joe-rogan-experience-podcast-transcript/",
        "Joe Rogan Experience #1470 with Elon Musk",
        "rogan-1470",
    ),
]

# Kaggle dataset: full @elonmusk tweet archive 2010 through March 2025.
# Manual download required (Kaggle login). Drop the CSV at this path
# before running. The script tolerates the file's absence — if it's
# missing the run continues with the other sources and just logs a
# warning. Filename is matched case-insensitively against any *.csv in
# raw/ to be forgiving about Kaggle's auto-naming.
#
# Source: https://www.kaggle.com/datasets/dadalyndell/elon-musk-tweets-2010-to-2025-march
KAGGLE_TWEETS_FILENAME = "elon_musk_tweets.csv"
KAGGLE_DATASET_URL = (
    "https://www.kaggle.com/datasets/"
    "dadalyndell/elon-musk-tweets-2010-to-2025-march"
)

# Tweets shorter than this are usually one-word reactions ("yes", "lol",
# single emojis) that retrieve poorly and pad the index. The same
# threshold the deleted xcancel scraper used.
KAGGLE_MIN_TWEET_CHARS = 40

# Twitter URL hostnames stripped from tweet text before embedding —
# t.co shorteners are noise that hurt retrieval quality.
TWEET_URL_RE = re.compile(r"https?://\S+")


# ==================
# HTTP / parsing config
# ==================

REQUEST_DELAY = 1.5
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Wikiquote individual <li> length filter. Many entries are 1-2 sentences;
# we go lower than other sources because each quote is intentionally
# short. The chunker will pack them.
MIN_QUOTE_CHARS = 40
MAX_QUOTE_CHARS = 1200

# For long-form sources (Wikipedia, Lex transcripts, news prose).
MIN_PARAGRAPH_CHARS = 80

# Boilerplate / non-prose patterns to drop.
BOILERPLATE_PATTERNS = [
    re.compile(r"^From Wikipedia", re.IGNORECASE),
    re.compile(r"^This article", re.IGNORECASE),
    re.compile(r"^Jump to navigation", re.IGNORECASE),
    re.compile(r"^\[edit\]"),
    re.compile(r"^Retrieved from"),
    # Lex transcript intro / sponsor-read paragraphs that aren't
    # actually Musk speaking (we filter by speaker too, but these can
    # leak through if speaker tags are missing).
    re.compile(r"^The following is a conversation", re.IGNORECASE),
    re.compile(r"^This episode is brought to you by", re.IGNORECASE),
    re.compile(r"^Please support this podcast", re.IGNORECASE),
]


# ==================
# Entry point
# ==================


def main() -> int:
    repo_backend = Path(__file__).resolve().parents[2]
    out_dir = repo_backend / "data" / "musk"
    raw_dir = out_dir / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = out_dir / "chunks.jsonl"
    chunks_written = 0
    sources_ok = 0
    sources_failed: List[str] = []

    # Cross-source dedupe. Wikiquote and the Kaggle tweet archive can
    # overlap on tweets — Wikiquote curators copy famous tweets verbatim.
    # Whichever source emits the text first wins; the other skips it.
    seen_paragraphs: set[str] = set()

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    ) as client, chunks_path.open("w", encoding="utf-8") as f_out:

        # ----- 1. Wikiquote (highest-signal source) -----
        n = _ingest_wikiquote(client, f_out, raw_dir, seen_paragraphs)
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            sources_failed.append("wikiquote")
        time.sleep(REQUEST_DELAY)

        # ----- 2. Lex Fridman transcripts (Musk segments only) -----
        for url in LEX_TRANSCRIPT_URLS:
            n = _ingest_lex_transcript(
                client=client,
                url=url,
                f_out=f_out,
                raw_dir=raw_dir,
                seen=seen_paragraphs,
            )
            if n > 0:
                chunks_written += n
                sources_ok += 1
            else:
                sources_failed.append(url)
            time.sleep(REQUEST_DELAY)

        # ----- 3. Singjupost interview transcripts (Musk lines only) -----
        for url, title, slug in SINGJUPOST_URLS:
            n = _ingest_singjupost(
                client=client,
                url=url,
                title=title,
                slug=slug,
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

        # ----- 4. Kaggle tweet archive (offline, no HTTP) -----
        n = _ingest_kaggle_tweets(
            f_out=f_out,
            raw_dir=raw_dir,
            seen=seen_paragraphs,
        )
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            # Optional source: don't fail the run if the user hasn't
            # downloaded the CSV. Already logged inside the helper.
            pass

        # ----- 5. Wikipedia biography -----
        n = _ingest_wikipedia(
            client=client,
            url=WIKIPEDIA_URL,
            slug="wikipedia-bio",
            title="Wikipedia: Elon Musk",
            kind="biography",
            f_out=f_out,
            raw_dir=raw_dir,
            seen=seen_paragraphs,
        )
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            sources_failed.append("wikipedia-bio")
        time.sleep(REQUEST_DELAY)

        # ----- 6. Wikipedia views (positions on tech / politics / AI) -----
        n = _ingest_wikipedia(
            client=client,
            url=WIKIPEDIA_VIEWS_URL,
            slug="wikipedia-views",
            title="Wikipedia: Views of Elon Musk",
            kind="views",
            f_out=f_out,
            raw_dir=raw_dir,
            seen=seen_paragraphs,
        )
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            sources_failed.append("wikipedia-views")

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
    """Walk the Musk Wikiquote page section-by-section, harvesting his
    quotes and dropping the 'Quotes about Musk' meta-section.

    Each quote is emitted as a discrete paragraph (one quote per line in
    raw/, multiple quotes packed per chunk by chunk_paragraphs).
    Provenance: the section heading (typically a year) is preserved as
    the chunk's `year` field when parseable.
    """
    try:
        resp = client.get(WIKIQUOTE_URL)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  [wikiquote] FAIL: {e}", file=sys.stderr)
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.find("div", {"id": "mw-content-text"})
    if content is None:
        print("  [wikiquote] no #mw-content-text; layout changed?", file=sys.stderr)
        return 0

    # Strip cruft.
    for tag in content.find_all(["sup", "table", "style", "script"]):
        tag.decompose()

    # Walk in document order. h2/h3 demarcate sections. <ul> at the same
    # level holds the quotes for that section. We track the current
    # section heading and flip a "skip" flag when entering excluded
    # sections.
    current_section = "Top"
    skip = False
    quotes_by_year: Dict[str, List[str]] = {}

    for tag in content.find_all(["h2", "h3", "ul"]):
        if tag.name in ("h2", "h3"):
            heading = tag.get_text(" ", strip=True)
            heading = re.sub(r"\[edit\]", "", heading).strip()
            current_section = heading
            skip = any(skip_name in heading for skip_name in WIKIQUOTE_SKIP_SECTIONS)
            continue

        if skip:
            continue

        # Top-level <li>s only — nested <li>s are typically context /
        # commentary that gets glued onto the parent quote anyway via
        # get_text.
        for li in tag.find_all("li", recursive=False):
            quote = _normalize(li.get_text(" ", strip=True))
            if not (MIN_QUOTE_CHARS <= len(quote) <= MAX_QUOTE_CHARS):
                continue
            if _looks_like_boilerplate(quote):
                continue
            if quote in seen:
                continue
            seen.add(quote)
            quotes_by_year.setdefault(current_section, []).append(quote)

    if not quotes_by_year:
        print("  [wikiquote] zero quotes harvested", file=sys.stderr)
        return 0

    total_quotes = sum(len(qs) for qs in quotes_by_year.values())

    # Persist raw text for debugging.
    raw_lines: List[str] = []
    for section, quotes in quotes_by_year.items():
        raw_lines.append(f"=== {section} ===\n")
        for q in quotes:
            raw_lines.append(q)
            raw_lines.append("")
    (raw_dir / "wikiquote.txt").write_text("\n".join(raw_lines), encoding="utf-8")

    # Emit chunks: pack within each section so a chunk doesn't span
    # disjoint years (keeps the year metadata coherent).
    n = 0
    for section, quotes in quotes_by_year.items():
        year = _parse_year(section)
        for i, chunk in enumerate(chunk_paragraphs(quotes, target_tokens=400)):
            record: Dict = {
                "id": f"musk-wikiquote-{_slugify(section)}-{i:03d}",
                "expert_id": "musk",
                "kind": "wikiquote",
                "section": section,
                "source_url": WIKIQUOTE_URL,
                "source_title": f"Wikiquote: Elon Musk ({section})",
                "text": chunk,
            }
            if year is not None:
                record["year"] = year
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1

    print(f"  [wikiquote] {total_quotes:4d} quotes across {len(quotes_by_year)} sections -> {n} chunks")
    return n


# ==================
# Lex Fridman transcripts
# ==================


def _ingest_lex_transcript(
    *,
    client: httpx.Client,
    url: str,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    """Pull the 'Elon Musk' segments out of a Lex Fridman transcript page.

    Each segment is a <div class="ts-segment"> containing a speaker
    <span class="ts-name">, a timestamp, and the text in
    <span class="ts-text">. We keep only segments where the speaker is
    Musk, and pack consecutive segments into chunks.
    """
    try:
        resp = client.get(url)
    except httpx.HTTPError as e:
        print(f"  [lex {url}] FAIL: {e}", file=sys.stderr)
        return 0

    if resp.status_code != 200:
        print(f"  [lex {url}] HTTP {resp.status_code}, skipping")
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    segments_check = soup.find_all("div", class_="ts-segment")
    # Lex's CDN occasionally serves a thin shell HTML that is missing
    # the rendered transcript content. One retry with a short backoff
    # consistently recovers without needing a more elaborate strategy.
    if not segments_check:
        time.sleep(3.0)
        try:
            resp = client.get(url)
        except httpx.HTTPError:
            pass
        else:
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "Lex Fridman Podcast"
    # Strip "- Lex Fridman" suffix from title for nicer source labels.
    title = re.sub(r"\s*[-|]\s*Lex Fridman.*$", "", title)
    # Slug from the URL path, e.g.
    #   .../elon-musk-4-transcript        -> lex-elon-musk-4
    #   .../elon-musk-and-neuralink-team-transcript
    #                                     -> lex-elon-musk-and-neuralink-team
    path_slug = re.sub(r"^/|/$", "", _url_path(url))
    path_slug = re.sub(r"-transcript$", "", path_slug)
    slug = f"lex-{path_slug}"

    segments = soup.find_all("div", class_="ts-segment")
    if not segments:
        print(f"  [lex {url}] no ts-segment elements found")
        return 0

    musk_paragraphs: List[str] = []
    for seg in segments:
        speaker_tag = seg.find(class_="ts-name")
        text_tag = seg.find(class_="ts-text")
        if not speaker_tag or not text_tag:
            continue
        speaker = speaker_tag.get_text(strip=True)
        # Match anything that looks like Musk; the transcripts use
        # "Elon Musk" but be defensive.
        if "musk" not in speaker.lower():
            continue
        text = _normalize(text_tag.get_text(" ", strip=True))
        if len(text) < MIN_PARAGRAPH_CHARS:
            continue
        if _looks_like_boilerplate(text):
            continue
        if text in seen:
            continue
        seen.add(text)
        musk_paragraphs.append(text)

    if len(musk_paragraphs) < 5:
        print(f"  [lex {url}] only {len(musk_paragraphs)} Musk segments, skipping")
        return 0

    (raw_dir / f"{slug}.txt").write_text(
        "\n\n".join(musk_paragraphs), encoding="utf-8"
    )

    n = 0
    for i, chunk in enumerate(chunk_paragraphs(musk_paragraphs)):
        record: Dict = {
            "id": f"musk-{slug}-{i:03d}",
            "expert_id": "musk",
            "kind": "podcast_transcript",
            "source_url": url,
            "source_title": title,
            "text": chunk,
        }
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        n += 1

    print(f"  [{slug}] {len(musk_paragraphs):4d} Musk segments -> {n} chunks")
    return n


# ==================
# Singjupost interview transcripts
# ==================


# Speaker-line prefix patterns for Singjupost-style transcripts.
# These are full-text transcripts where each turn starts with the
# speaker's name followed by a colon. Different transcripts on the
# site use slightly different conventions (e.g. "Elon Musk:" vs
# "Elon:" vs the bolded variant).
_MUSK_SPEAKER_PATTERN = re.compile(
    r"^\s*(?:Elon Musk|Elon|Mr\.?\s*Musk|Musk)\s*[:\-]\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
# Anyone else's "Speaker:" prefix line. We use this to detect when a
# Musk-spoken paragraph ends and someone else's begins, so a stray
# unprefixed paragraph immediately after a Musk turn doesn't get
# silently swallowed as continued Musk speech. Two flavors are matched:
#   "Joe Rogan: ..."     — bare-name speaker prefix
#   "[GROK AI]: ..."     — bracketed speaker prefix (used by Singjupost
#                          to mark interjections from Grok in the
#                          Rogan #1470 transcript)
_OTHER_SPEAKER_PATTERN = re.compile(
    r"^\s*(?:\[[^\]]{1,40}\]|[A-Z][A-Za-z\.\s]{1,30})\s*[:\-]\s*",
)


def _ingest_singjupost(
    *,
    client: httpx.Client,
    url: str,
    title: str,
    slug: str,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    """Extract Musk's lines from a Singjupost speaker-prefixed transcript.

    These pages put every turn in its own <p>, prefixed by the speaker's
    name + colon. We match Musk's prefix, strip it, and keep the
    remaining text. Continuation paragraphs (no prefix) immediately
    following a Musk turn are kept too, until we hit another
    speaker-prefixed paragraph.
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

    # Strip nav / scripts / aside.
    for tag in article.find_all(["script", "style", "nav", "aside", "header", "footer"]):
        tag.decompose()

    paragraphs = article.find_all("p")

    musk_paragraphs: List[str] = []
    in_musk = False
    for p in paragraphs:
        raw = p.get_text(" ", strip=True)
        if not raw:
            continue
        m = _MUSK_SPEAKER_PATTERN.match(raw)
        if m:
            line = _normalize(m.group(1))
            in_musk = True
            if len(line) >= 40 and not _looks_like_boilerplate(line) and line not in seen:
                seen.add(line)
                musk_paragraphs.append(line)
            continue
        # Different speaker line — stop attributing to Musk.
        if _OTHER_SPEAKER_PATTERN.match(raw):
            in_musk = False
            continue
        # Continuation of the previous speaker's turn. Keep only if
        # we're inside a Musk turn.
        if in_musk:
            line = _normalize(raw)
            if len(line) >= 40 and not _looks_like_boilerplate(line) and line not in seen:
                seen.add(line)
                musk_paragraphs.append(line)

    if len(musk_paragraphs) < 5:
        print(f"  [{slug}] only {len(musk_paragraphs)} Musk lines, skipping")
        return 0

    (raw_dir / f"{slug}.txt").write_text(
        "\n\n".join(musk_paragraphs), encoding="utf-8"
    )

    n = 0
    for i, chunk in enumerate(chunk_paragraphs(musk_paragraphs)):
        record: Dict = {
            "id": f"musk-{slug}-{i:03d}",
            "expert_id": "musk",
            "kind": "podcast_transcript",
            "source_url": url,
            "source_title": title,
            "text": chunk,
        }
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        n += 1

    print(f"  [{slug}] {len(musk_paragraphs):4d} Musk lines -> {n} chunks")
    return n


# ==================
# Kaggle tweet archive
# ==================


def _ingest_kaggle_tweets(
    *,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    """Read the Kaggle @elonmusk tweet CSV, filter, bucket by year, emit chunks.

    The CSV is downloaded manually (Kaggle requires a logged-in browser
    session, and we don't want to add the kaggle SDK + credentials as a
    hard dependency for a corpus rebuild). Drop the file at
    `backend/data/musk/raw/elon_musk_tweets.csv` (or any *.csv there)
    before running this script.

    Filtering rules:
    - Drop pure retweets (`text` starts with "RT @").
    - Drop replies (any tweet whose text starts with "@username "
      addressed at someone other than @elonmusk himself, OR with a
      non-empty `in_reply_to_*` column when present).
    - Drop tweets shorter than KAGGLE_MIN_TWEET_CHARS chars after URL
      stripping. Kills "lol", "true", lone-emoji reactions.
    - Strip t.co URLs from tweet bodies; they're noise for retrieval.

    Chunking:
    - Group by year (parsed from the timestamp column).
    - For each year, pack tweets into ~400-token chunks via
      chunk_paragraphs. Same approach as the Wikiquote per-year sections.

    The CSV column names vary across Kaggle Twitter datasets. We
    auto-detect from a small set of common synonyms rather than
    hardcoding column names. If detection fails the function logs a
    clear error and returns 0.
    """
    csv_path = _locate_kaggle_csv(raw_dir)
    if csv_path is None:
        print(
            f"  [kaggle] no CSV at {raw_dir / KAGGLE_TWEETS_FILENAME}; "
            f"skipping. Download from {KAGGLE_DATASET_URL} to enable."
        )
        return 0

    print(f"  [kaggle] reading {csv_path.name}")
    try:
        rows = list(_read_kaggle_rows(csv_path))
    except Exception as e:
        print(f"  [kaggle] FAIL reading {csv_path.name}: {e}", file=sys.stderr)
        return 0

    if not rows:
        print(f"  [kaggle] CSV parsed but produced 0 rows", file=sys.stderr)
        return 0

    # Group surviving tweets by year. Tweets without a parseable year are
    # bucketed under "undated" so we don't silently drop them.
    by_year: Dict[Optional[int], List[str]] = defaultdict(list)
    n_filtered_retweet = 0
    n_filtered_reply = 0
    n_filtered_short = 0
    n_filtered_dup = 0

    for row in rows:
        text_raw = row["text"]
        if _is_retweet(text_raw):
            n_filtered_retweet += 1
            continue
        if _is_reply(text_raw, row.get("in_reply_to")):
            n_filtered_reply += 1
            continue

        text = _clean_tweet(text_raw)
        if len(text) < KAGGLE_MIN_TWEET_CHARS:
            n_filtered_short += 1
            continue
        if text in seen:
            n_filtered_dup += 1
            continue
        seen.add(text)
        by_year[row["year"]].append(text)

    total_kept = sum(len(v) for v in by_year.values())
    print(
        f"  [kaggle] {len(rows)} rows -> {total_kept} kept "
        f"(rt={n_filtered_retweet}, reply={n_filtered_reply}, "
        f"short={n_filtered_short}, dup={n_filtered_dup})"
    )
    if total_kept == 0:
        return 0

    # Save cleaned plain text for debugging / repro. One section per year.
    raw_lines: List[str] = []
    for year in sorted(by_year, key=lambda y: (y is None, y)):
        raw_lines.append(f"--- {year if year is not None else 'undated'} ---")
        raw_lines.extend(by_year[year])
        raw_lines.append("")
    (raw_dir / "kaggle-tweets.txt").write_text(
        "\n\n".join(raw_lines), encoding="utf-8"
    )

    n = 0
    for year in sorted(by_year, key=lambda y: (y is None, y)):
        tweets = by_year[year]
        # ~400 tokens per chunk so each chunk holds ~5-15 packed tweets,
        # comparable to Wikiquote chunk density. min_chunk_chars=100 (vs
        # the default 200) so sparse early years (2010-2011 had little
        # @elonmusk activity) don't get silently dropped — a single
        # substantive tweet is still worth indexing.
        for i, chunk in enumerate(
            chunk_paragraphs(tweets, target_tokens=400, min_chunk_chars=100)
        ):
            year_label = str(year) if year is not None else "undated"
            record: Dict = {
                "id": f"musk-tweets-{year_label}-{i:03d}",
                "expert_id": "musk",
                "kind": "tweet",
                "section": year_label,
                "source_url": "https://twitter.com/elonmusk",
                "source_title": (
                    f"@elonmusk tweets ({year_label}, "
                    f"Kaggle dadalyndell/elon-musk-tweets-2010-to-2025-march)"
                ),
                "text": chunk,
            }
            if year is not None:
                record["year"] = year
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1

    print(f"  [kaggle] {total_kept} tweets across {len(by_year)} years -> {n} chunks")
    return n


def _locate_kaggle_csv(raw_dir: Path) -> Optional[Path]:
    """Find the Kaggle CSV. Prefer the canonical filename; fall back to
    any *.csv in raw/ so the user doesn't have to rename Kaggle's auto-
    generated archive.
    """
    canonical = raw_dir / KAGGLE_TWEETS_FILENAME
    if canonical.is_file():
        return canonical
    csvs = sorted(raw_dir.glob("*.csv"))
    return csvs[0] if csvs else None


# Column-name synonyms across the various @elonmusk Kaggle datasets that
# circulate. We pick the first column from each list that the CSV
# actually contains.
_TEXT_COLUMNS = ["text", "Text", "tweet", "Tweet", "content", "full_text"]
_DATE_COLUMNS = [
    "created_at", "Created_At", "date", "Date", "datetime", "timestamp",
    "Timestamp", "time", "Tweet_Posted_Time(UTC)",
]
_REPLY_COLUMNS = [
    "in_reply_to_status_id", "in_reply_to_user_id", "in_reply_to_screen_name",
    "in_reply_to", "reply_to",
]


def _read_kaggle_rows(path: Path) -> Iterator[Dict]:
    """Yield {text, year, in_reply_to} dicts from the Kaggle CSV.

    Auto-detects the text and date columns. Skips rows with no text.
    Tolerates malformed rows by letting the csv module's default error
    behavior (skip on quoting issues) pass through; the few rows it
    drops are not worth fighting over given the dataset has ~30k+ rows.
    """
    # newline="" + utf-8-sig handles a possible BOM and CRLFs from
    # Windows-exported Kaggle CSVs.
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise RuntimeError("CSV has no header row")

        text_col = _pick_column(reader.fieldnames, _TEXT_COLUMNS)
        date_col = _pick_column(reader.fieldnames, _DATE_COLUMNS)
        reply_col = _pick_column(reader.fieldnames, _REPLY_COLUMNS, required=False)

        if text_col is None:
            raise RuntimeError(
                f"could not find a tweet-text column in {reader.fieldnames!r}; "
                f"expected one of {_TEXT_COLUMNS}"
            )
        if date_col is None:
            # Date is recoverable: we can still emit tweets bucketed
            # under "undated". Log and continue.
            print(
                f"  [kaggle] WARN: no date column found in "
                f"{reader.fieldnames!r}; tweets will go under 'undated'."
            )

        for row in reader:
            text = (row.get(text_col) or "").strip()
            if not text:
                continue
            year = _parse_tweet_year(row.get(date_col)) if date_col else None
            in_reply_to = (row.get(reply_col) or "").strip() if reply_col else ""
            yield {"text": text, "year": year, "in_reply_to": in_reply_to}


def _pick_column(
    fieldnames: Iterable[str], candidates: Iterable[str], *, required: bool = True
) -> Optional[str]:
    field_set = {f for f in fieldnames if f}
    for c in candidates:
        if c in field_set:
            return c
    # Case-insensitive second pass.
    lower_map = {f.lower(): f for f in field_set}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


# Date format detection. Kaggle Twitter dumps come in many flavors;
# we try the most common ones in order. Bare year extraction (4
# consecutive digits between 2005-2030) is the last-ditch fallback.
_DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%d",
    "%a %b %d %H:%M:%S %z %Y",   # Twitter API legacy: "Mon Sep 28 19:21:18 +0000 2020"
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
]
_BARE_YEAR_RE = re.compile(r"\b(20[0-3]\d)\b")


def _parse_tweet_year(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    from datetime import datetime
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).year
        except ValueError:
            continue
    m = _BARE_YEAR_RE.search(s)
    if m:
        return int(m.group(1))
    return None


def _is_retweet(text: str) -> bool:
    """Pure retweets start with 'RT @username:'. Quote-tweets do not —
    they have arbitrary leading text and the quoted tweet is appended
    by Twitter, not present in the text column.
    """
    return text.lstrip().startswith("RT @")


def _is_reply(text: str, in_reply_to: str) -> bool:
    """A reply is either:
    - flagged by an `in_reply_to_*` column (when present), or
    - starts with `@username ` addressed at someone other than @elonmusk.

    Self-mentions ("@elonmusk replied to himself") are kept; threads of
    his own are voice-relevant. Tweets that *contain* a mention but
    don't start with one are kept (the mention is rhetorical, not a
    reply).
    """
    if in_reply_to:
        return True
    stripped = text.lstrip()
    if not stripped.startswith("@"):
        return False
    # Mention is the first token. If it's @elonmusk it's a self-reply;
    # keep it. Otherwise it's a reply to someone else; drop it.
    first_token = stripped.split(maxsplit=1)[0].rstrip(":,.!?").lower()
    return first_token != "@elonmusk"


def _clean_tweet(text: str) -> str:
    """Strip t.co URLs and collapse whitespace.

    We keep mentions, hashtags, and emoji intact — they're part of the
    voice signature. URLs go because they're tokens like
    'https://t.co/abc' that carry zero semantic meaning for retrieval.
    """
    text = TWEET_URL_RE.sub("", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ==================
# Wikipedia (long-form prose)
# ==================


def _ingest_wikipedia(
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
            "id": f"musk-{slug}-{i:03d}",
            "expert_id": "musk",
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
# Cleaning helpers
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
    """Extract a 4-digit year if the heading looks like a year section."""
    m = re.match(r"^(\d{4})\b", heading.strip())
    if m:
        y = int(m.group(1))
        if 1990 <= y <= 2100:
            return y
    return None


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s or "section"


def _url_path(url: str) -> str:
    """Return the path portion of a URL without scheme/host/query."""
    from urllib.parse import urlparse

    return urlparse(url).path


if __name__ == "__main__":
    raise SystemExit(main())
