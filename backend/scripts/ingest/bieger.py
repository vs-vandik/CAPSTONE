"""Assemble Thomas Bieger's public corpus for the HSG professor persona.

Sources:
0. User-provided profile summary used for frontend bio / general context.
1. German Wikipedia biography:
   https://de.wikipedia.org/wiki/Thomas_Bieger
2. ResearchGate generated author page:
   https://www.researchgate.net/scientific-contributions/Thomas-Bieger-68236403

ResearchGate access note:
- The public page is reachable in a browser-like fetch and exposes the
  generated publication list plus some metadata and abstracts.
- The site often blocks direct script HTTP with 403, and many publication
  pages say "Request full-text PDF" rather than exposing the paper body.
  This script therefore tries a live request, records the access result,
  and emits a small curated fallback of publication metadata / abstract
  summaries for reproducible local builds.

Run from `backend/`:

    python -m scripts.ingest.bieger

Output:

    backend/data/bieger/
        chunks.jsonl              # one chunk per line, ready for embedding
        raw/<slug>.txt            # cleaned plain text per source
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

import httpx
from bs4 import BeautifulSoup

from scripts.ingest._chunking import chunk_paragraphs


WIKIPEDIA_URL = "https://de.wikipedia.org/wiki/Thomas_Bieger"
RESEARCHGATE_AUTHOR_URL = (
    "https://www.researchgate.net/scientific-contributions/"
    "Thomas-Bieger-68236403"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

MIN_PARAGRAPH_CHARS = 80

BOILERPLATE_PATTERNS = [
    re.compile(r"^Aus Wikipedia", re.IGNORECASE),
    re.compile(r"^Diese Seite wurde", re.IGNORECASE),
    re.compile(r"^Der Text ist unter", re.IGNORECASE),
    re.compile(r"^Durch die Nutzung", re.IGNORECASE),
    re.compile(r"^Wikipedia", re.IGNORECASE),
    re.compile(r"^\[Bearbeiten\]"),
]


@dataclass(frozen=True)
class PublicationSummary:
    slug: str
    title: str
    source_url: str
    year: int
    kind: str
    summary: str


USER_PROFILE_SUMMARY = (
    "Thomas Bieger was dean of the Faculty of Management at the University "
    "of St. Gallen from 2003 to 2005, vice-president from 2005 to 2010, "
    "and rector/president from 2011 to 2020. He became full professor of "
    "business administration with a specialization in tourism in 1999 and "
    "directs the Institute for Systemic Management and Public Governance. "
    "His research and teaching priorities include management of personal "
    "services, general and location marketing, and net economics. His "
    "industry focus includes tourism development and planning, airline "
    "operations, railway operations, and sports. Since 1996 he has held "
    "directorships in service companies and institutions across transport, "
    "hotels, long-term care, international consulting, finance, retail, "
    "Swiss hotel credit, aviation, tourism science, CEMS, and EQUIS."
)


RESEARCHGATE_SUMMARIES: List[PublicationSummary] = [
    PublicationSummary(
        slug="digital-analytics-travel-2025",
        title="Digital Analytics bei Reisen - Chancen und Gefahren fuer Kunden und Anbieter",
        source_url=(
            "https://www.researchgate.net/publication/392236580_"
            "Digital_Analytics_bei_Reisen_-_Chancen_und_Gefahren_fur_"
            "Kunden_und_Anbieter"
        ),
        year=2025,
        kind="chapter",
        summary=(
            "ResearchGate lists this chapter by Pietro Beritelli and Thomas "
            "Bieger in a service-management volume on digital analytics. The "
            "publication frames travel analytics as a double-edged management "
            "issue: better data can improve coordination and personalization, "
            "but it also creates risks for customers and providers around "
            "trust, autonomy, and the handling of behavioral data."
        ),
    ),
    PublicationSummary(
        slug="end-of-tourism-2025",
        title="Das Ende des Tourismus?: Tourismuslehre neu gedacht",
        source_url=(
            "https://www.researchgate.net/publication/391850447_"
            "Das_Ende_des_Tourismus_Tourismuslehre_neu_gedacht"
        ),
        year=2025,
        kind="book",
        summary=(
            "This book with Christian Laesser and Pietro Beritelli argues that "
            "overtourism, changing travel behavior, mobility, sustainability, "
            "new consumption patterns, and new technologies challenge the "
            "traditional concepts of tourism. The ResearchGate abstract "
            "presents the answer as a modern, systemic rethinking of tourism "
            "rather than a narrow marketing playbook."
        ),
    ),
    PublicationSummary(
        slug="destination-marketing-management-change-2023",
        title="Wandel im Destinationsmarketing und -management - Ein Ausblick fuer Tourismusorganisationen",
        source_url=(
            "https://www.researchgate.net/publication/372769441_"
            "Wandel_im_Destinationsmarketing_und_-management_-"
            "Ein_Ausblick_fur_Tourismusorganisationen"
        ),
        year=2023,
        kind="chapter",
        summary=(
            "ResearchGate metadata identifies this Springer chapter with "
            "Pietro Beritelli as a forward-looking contribution on destination "
            "marketing and management. The associated literature on the page "
            "emphasizes that destination organizations should move beyond "
            "campaign logic toward coordination, moderation, and support for "
            "tourism development in open destination systems."
        ),
    ),
    PublicationSummary(
        slug="smart-services-tourism-2022",
        title="Smart Services im Tourismus - Herausforderungen der digitalen Koordination von offenen Dienstleistungsnetzwerken",
        source_url=(
            "https://www.researchgate.net/publication/361659989_"
            "Smart_Services_im_Tourismus_-_Herausforderungen_der_digitalen_"
            "Koordination_von_offenen_Dienstleistungsnetzwerken"
        ),
        year=2022,
        kind="chapter",
        summary=(
            "This chapter with Pietro Beritelli is listed as part of a volume "
            "on smart services. Its title points directly to Bieger's systems "
            "lens: tourism services are open networks that require digital "
            "coordination across providers, customers, destinations, and "
            "infrastructure rather than optimization inside one firm alone."
        ),
    ),
    PublicationSummary(
        slug="travel-motivations-sars-cov-2-2021",
        title="Considerations on the Impact of SARS-CoV-2 on Travel Motivations",
        source_url=(
            "https://www.researchgate.net/publication/356531380_"
            "Considerations_on_the_Impact_of_SARS-CoV-2_on_Travel_Motivations"
        ),
        year=2021,
        kind="article",
        summary=(
            "The ResearchGate abstract reports that travel motives changed "
            "less during the SARS-CoV-2 pandemic than expected. It offers two "
            "interpretations for further research: travel motivations may be "
            "more stable than assumed, or people may adjust motivations "
            "rapidly to available options when mobility is constrained."
        ),
    ),
    PublicationSummary(
        slug="covid-second-home-prices-2021",
        title="COVID-19 and Second Home Prices in Switzerland: An Empirical Insight",
        source_url=(
            "https://www.researchgate.net/publication/356529881_"
            "COVID-19_and_Second_Home_Prices_in_Switzerland_An_Empirical_"
            "Insight"
        ),
        year=2021,
        kind="article",
        summary=(
            "This paper with Robert Weinert and Aristid Klumbies studies "
            "Swiss second-home transaction prices during COVID-19. The "
            "ResearchGate abstract says prices rose significantly, especially "
            "relative to apartments, and proposes that buyers valued less "
            "crowded places while intensive tourism infrastructure became less "
            "useful during the pandemic."
        ),
    ),
    PublicationSummary(
        slug="aviation-value-chain-system-2021",
        title="From the Aviation Value Chain to the Aviation System",
        source_url=(
            "https://www.researchgate.net/publication/355204445_"
            "From_the_Aviation_Value_Chain_to_the_Aviation_System"
        ),
        year=2021,
        kind="chapter",
        summary=(
            "This chapter with Andreas Wittmer argues for mapping aviation as "
            "an interdependent system rather than a simple chain. The "
            "ResearchGate abstract distinguishes manufacturers, technical "
            "support, airlines, airports, and leasing firms, and links their "
            "different profit pools to entry barriers and market power."
        ),
    ),
    PublicationSummary(
        slug="tourismuslehre-grundriss-2010",
        title="Tourismuslehre - Ein Grundriss",
        source_url=RESEARCHGATE_AUTHOR_URL,
        year=2010,
        kind="book",
        summary=(
            "ResearchGate presents this textbook as an interdisciplinary "
            "treatment of tourism as an economic sector, a social phenomenon, "
            "and an ecological question. Its system-theory structure separates "
            "demand, destination, travel intermediation, and transport while "
            "using definitions, cases, and decision approaches for practice."
        ),
    ),
]


def main() -> int:
    repo_backend = Path(__file__).resolve().parents[2]
    out_dir = repo_backend / "data" / "bieger"
    raw_dir = out_dir / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = out_dir / "chunks.jsonl"
    chunks_written = 0
    sources_ok = 0
    sources_failed: List[str] = []
    seen: set[str] = set()

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    ) as client, chunks_path.open("w", encoding="utf-8") as f_out:
        n = _ingest_user_profile(f_out, raw_dir, seen)
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            sources_failed.append("user-profile")

        n = _ingest_wikipedia(client, f_out, raw_dir, seen)
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            sources_failed.append("wikipedia")

        n = _ingest_researchgate(client, f_out, raw_dir, seen)
        if n > 0:
            chunks_written += n
            sources_ok += 1
        else:
            sources_failed.append("researchgate")

    print()
    print(f"OK: {sources_ok} sources, {chunks_written} chunks -> {chunks_path}")
    if sources_failed:
        print(f"SKIPPED/FAILED: {sources_failed}", file=sys.stderr)
    if chunks_written == 0:
        print("ERR: zero chunks written; not viable as a corpus.", file=sys.stderr)
        return 1
    return 0


def _ingest_user_profile(f_out, raw_dir: Path, seen: set[str]) -> int:
    text = _normalize(USER_PROFILE_SUMMARY)
    if not text or text in seen:
        return 0
    seen.add(text)

    (raw_dir / "user-profile.txt").write_text(text + "\n", encoding="utf-8")

    n = 0
    for i, chunk in enumerate(
        chunk_paragraphs([text], target_tokens=350, min_chunk_chars=120)
    ):
        record: Dict = {
            "id": f"bieger-user-profile-{i:03d}",
            "expert_id": "bieger",
            "kind": "profile",
            "source_url": "user-provided",
            "source_title": "User-provided Thomas Bieger profile",
            "text": chunk,
        }
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        n += 1

    print(f"  [user-profile]    1 summary -> {n} chunks")
    return n


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
        print(f"  [wikipedia] FAIL: {e}", file=sys.stderr)
        return 0

    # German Wikipedia serves UTF-8, but httpx can occasionally infer a
    # fallback encoding from headers and produce mojibake for umlauts.
    html = resp.content.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find("div", {"id": "mw-content-text"})
    if content is None:
        return 0

    for tag in content.find_all(["sup", "table", "style", "script"]):
        tag.decompose()

    raw_paragraphs = [
        p.get_text(" ", strip=True)
        for p in content.find_all("p")
        if p.get_text(" ", strip=True)
    ]
    cleaned = list(_clean_paragraphs(raw_paragraphs))
    deduped: List[str] = []
    for p in cleaned:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)

    if len(deduped) < 3:
        print(f"  [wikipedia] only {len(deduped)} paragraphs, skipping")
        return 0

    (raw_dir / "wikipedia.txt").write_text(
        "\n\n".join(deduped), encoding="utf-8"
    )

    n = 0
    for i, chunk in enumerate(chunk_paragraphs(deduped)):
        record: Dict = {
            "id": f"bieger-wikipedia-{i:03d}",
            "expert_id": "bieger",
            "kind": "biography",
            "source_url": WIKIPEDIA_URL,
            "source_title": "Wikipedia: Thomas Bieger",
            "text": chunk,
        }
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        n += 1

    print(f"  [wikipedia] {len(deduped):4d} paragraphs -> {n} chunks")
    return n


def _ingest_researchgate(
    client: httpx.Client,
    f_out,
    raw_dir: Path,
    seen: set[str],
) -> int:
    access_note = _researchgate_access_note(client)

    raw_lines = [access_note, ""]
    n = 0
    for pub in RESEARCHGATE_SUMMARIES:
        text = (
            f"{pub.title} ({pub.year}, {pub.kind}). {pub.summary} "
            f"Source: ResearchGate publication metadata and abstract page."
        )
        text = _normalize(text)
        if text in seen:
            continue
        seen.add(text)
        raw_lines.append(text)
        raw_lines.append("")

        chunks = chunk_paragraphs([text], target_tokens=350, min_chunk_chars=120)
        for i, chunk in enumerate(chunks):
            record: Dict = {
                "id": f"bieger-researchgate-{pub.slug}-{i:03d}",
                "expert_id": "bieger",
                "kind": pub.kind,
                "source_url": pub.source_url,
                "source_title": f"ResearchGate: {pub.title}",
                "text": chunk,
                "year": pub.year,
                "access_note": access_note,
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1

    (raw_dir / "researchgate-summaries.txt").write_text(
        "\n".join(raw_lines), encoding="utf-8"
    )
    print(f"  [researchgate] {len(RESEARCHGATE_SUMMARIES):4d} summaries -> {n} chunks")
    print(f"  [researchgate] {access_note}")
    return n


def _researchgate_access_note(client: httpx.Client) -> str:
    try:
        resp = client.get(RESEARCHGATE_AUTHOR_URL)
    except httpx.HTTPError as e:
        return f"Live ResearchGate fetch failed: {e}. Used curated metadata fallback."

    if resp.status_code != 200:
        return (
            f"Live ResearchGate fetch returned HTTP {resp.status_code}. "
            "Used curated metadata fallback from public ResearchGate pages."
        )
    if "Publications" not in resp.text or "Thomas Bieger" not in resp.text:
        return (
            "Live ResearchGate fetch returned HTML without the expected "
            "publication markers. Used curated metadata fallback."
        )
    return (
        "Live ResearchGate author page was reachable, but the script uses "
        "the curated metadata fallback because full-text PDFs are not exposed "
        "for these publication pages."
    )


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


if __name__ == "__main__":
    raise SystemExit(main())
