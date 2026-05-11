"""Smoke test: drive a short discourse with Marx as one of the experts and
print every turn plus the quotes that the retriever surfaced.

Pairs Marx with Buffett so the contrast in retrieved material is obvious:
Marx should pull from Capital / the 1844 Manuscripts on the labor topic
below, while Buffett pulls from Berkshire shareholder letters.

Run from `backend/`:
    python -m scripts.smoke_marx
"""

from app.agents import discourse
from app.knowledge import store


def main() -> int:
    store.clear_cache()

    session = {
        "topic": (
            "Does the long-run accumulation of capital benefit workers, "
            "or does it concentrate wealth at the expense of labor?"
        ),
        "persona_ids": ["buffett", "marx"],
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
            print(f"  - {q[:200]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
