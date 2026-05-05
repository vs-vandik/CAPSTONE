"""Tavily-based news retrieval for grounding debate turns in current events.

One call per debate session, results cached on the session dict by the
discourse loop. If TAVILY_API_KEY is unset, returns an empty list and the
debate proceeds without news context — degrading gracefully matters more
for a demo than a hard failure.

We hit the Tavily REST API directly via httpx instead of pulling in
tavily-python. The endpoint is stable, the payload is trivial, and we
already pin httpx in requirements.txt.
"""

from typing import List, Dict
import httpx

from app.core.config import settings


TAVILY_URL = "https://api.tavily.com/search"


def fetch_topic_context(topic: str, max_results: int | None = None) -> List[Dict]:
    """Return a list of news snippets relevant to `topic`.

    Args:
        topic: The debate topic, used verbatim as the search query.
        max_results: Override `settings.TAVILY_MAX_RESULTS`.

    Returns:
        List of `{"title": str, "url": str, "content": str}`. Empty list
        if Tavily is not configured or the call fails — never raises.
    """
    if not settings.TAVILY_API_KEY:
        return []

    payload = {
        "api_key": settings.TAVILY_API_KEY,
        "query": topic,
        "search_depth": "basic",
        "max_results": max_results or settings.TAVILY_MAX_RESULTS,
        "include_answer": False,
        "include_raw_content": False,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(TAVILY_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        # Log to stderr but don't break the debate. A demo without current
        # news is still a working demo.
        print(f"[news] Tavily call failed, proceeding without news: {e}")
        return []

    results = data.get("results", []) or []
    return [
        {
            "title": r.get("title", "").strip(),
            "url": r.get("url", "").strip(),
            "content": r.get("content", "").strip(),
        }
        for r in results
        if r.get("content")
    ]


def format_for_prompt(snippets: List[Dict]) -> str:
    """Render snippets as a compact block for inclusion in a system prompt."""
    if not snippets:
        return ""

    lines = ["Recent context on this topic (for grounding, cite sparingly):"]
    for i, s in enumerate(snippets, 1):
        title = s["title"] or "(untitled)"
        # Trim aggressively. The point is signal, not full articles.
        content = s["content"][:400].replace("\n", " ").strip()
        lines.append(f"{i}. {title} — {content}")
    return "\n".join(lines)
