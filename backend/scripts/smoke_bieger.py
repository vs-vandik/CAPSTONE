"""Smoke test: drive a short discourse with Thomas Bieger as one expert.

Run from `backend/`:
    python -m scripts.smoke_bieger
"""

from app.agents import discourse
from app.knowledge import store


def main() -> int:
    store.clear_cache()

    session = {
        "topic": (
            "How should alpine tourism adapt to digital analytics, mobility "
            "shifts, and sustainability pressure?"
        ),
        "persona_ids": ["fink", "bieger"],
        "max_turns": 2,
        "history": [],
        "status": "active",
    }

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
            print(f"  - {q[:240]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
