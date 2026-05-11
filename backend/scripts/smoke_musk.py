"""Smoke test: drive a short discourse with Musk as one of the experts and
print every turn plus the quotes that the retriever surfaced.

Run from `backend/`:
    python -m scripts.smoke_musk
"""

from app.agents import discourse
from app.knowledge import store


def main() -> int:
    store.clear_cache()

    session = {
        "topic": (
            "Will artificial intelligence make most knowledge work "
            "obsolete within a decade, and what should investors do "
            "about it?"
        ),
        "persona_ids": ["fink", "musk"],
        "max_turns": 2,
        "history": [],
        "status": "active",
    }

    # Drive turns until status==done.
    while True:
        t = discourse.next_turn(session)
        sep = "=" * 70
        print(sep)
        print(f"[{t['speaker']:14s}] type={t['type']}")
        print(sep)
        print(t["content"])
        print()
        if t.get("done"):
            break

    print("=" * 70)
    print("QUOTES retrieved per persona for this topic:")
    print("=" * 70)
    for pid, quotes in session.get("quotes_by_persona", {}).items():
        print(f"\n--- {pid} ---")
        for q in quotes:
            print(f"  - {q[:200]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
