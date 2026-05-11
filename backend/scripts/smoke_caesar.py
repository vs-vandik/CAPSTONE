"""Smoke test: drive a short discourse with Caesar as one of the experts and
print every turn plus the quotes that the retriever surfaced.

Run from `backend/`:
    python -m scripts.smoke_caesar
"""

from app.agents import discourse
from app.knowledge import store


def main() -> int:
    store.clear_cache()

    session = {
        "topic": (
            "When does it make sense to commit decisively to an "
            "expensive long-term project, knowing the political cost "
            "of failure?"
        ),
        "persona_ids": ["fink", "caesar"],
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
