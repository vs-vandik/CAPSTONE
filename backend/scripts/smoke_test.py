"""A/B smoke test: real LLM calls, comparing seed-quotes-only vs full corpus.

Runs the same debate twice — once with `force_seed_quotes=True` (so even
Buffett, who has a built embeddings index, gets only his hand-picked
seed_quotes) and once with the full corpus retrieval. Same topic, same
personas, same number of turns. Print both transcripts.

The point is to read the output ourselves and decide if the corpus is
actually shaping voice. If A and B sound identical, retrieval is
mechanical-only and the prompts need work; if B is visibly better, ship.

Cost: ~$0.06 of chat tokens at Claude Haiku 4.5 prices, plus a few
embeddings (one query per persona per run, plus seed-quote embeddings
done once and cached).

Run from `backend/`:

    python -m scripts.smoke_test
"""

from __future__ import annotations

import sys
from typing import Dict, List

from app.agents import discourse
from app.agents.aporia import Aporia
from app.core import llm
from app.core.config import settings
from app.knowledge import store as knowledge_store


TOPIC = "Is passive index investing weakening market price discovery?"
PERSONA_IDS: List[str] = ["buffett", "musk"]
MAX_TURNS = 4


def main() -> int:
    if not settings.MODEL_ACCESS_KEY:
        print(
            "ERR: MODEL_ACCESS_KEY is not set. Add it to backend/.env "
            "(see .env.example).",
            file=sys.stderr,
        )
        return 2

    print(f"Provider: {settings.LLM_BASE_URL}")
    print(f"Chat model: {settings.LLM_MODEL}")
    print(f"Embedding model: {settings.EMBEDDING_MODEL}")
    print(f"Topic: {TOPIC}")
    print(f"Personas: {', '.join(PERSONA_IDS)}, max_turns={MAX_TURNS}")
    print()

    # Run A: seed quotes only
    knowledge_store.clear_cache()
    llm.reset_usage()
    print("=" * 72)
    print("RUN A — SEED QUOTES ONLY")
    print("=" * 72)
    a_session = _run_debate(force_seed_quotes=True)
    a_usage = dict(llm.usage_totals)

    print()

    # Run B: full corpus
    knowledge_store.clear_cache()
    llm.reset_usage()
    print("=" * 72)
    print("RUN B — FULL CORPUS RETRIEVAL")
    print("=" * 72)
    b_session = _run_debate(force_seed_quotes=False)
    b_usage = dict(llm.usage_totals)

    # Summary
    print()
    print("=" * 72)
    print("USAGE")
    print("=" * 72)
    _print_usage("A (seed)  ", a_usage)
    _print_usage("B (corpus)", b_usage)

    print()
    print("Read both transcripts above. The question is: does B sound more")
    print("like the real Buffett than A? If yes, retrieval is doing its job.")
    print("If A and B are indistinguishable, the prompt structure needs work.")
    return 0


def _run_debate(*, force_seed_quotes: bool) -> Dict:
    session = {
        "topic": TOPIC,
        "persona_ids": list(PERSONA_IDS),
        "max_turns": MAX_TURNS,
        "history": [],
        "force_seed_quotes": force_seed_quotes,
    }
    while True:
        turn = discourse.next_turn(session)
        _print_turn(turn)
        if turn.get("done"):
            break

    print()
    print("--- Aporia analysis ---")
    aporia = Aporia.analyze(session["history"], mode="simple")

    # Per-expert structured analyses. These are the richest output —
    # if the prompts are working, this is where you read for quality.
    experts = aporia.get("experts") or []
    if not experts:
        print("(no per-expert analyses)")
    for ex in experts:
        print()
        print(f"  ## {ex.get('expert', '?')}")
        claim = ex.get("core_claim") or ""
        if claim:
            print(f"    core claim: {claim}")
        for a in ex.get("assumptions") or []:
            print(f"    assumption: {a}")
        for lim in ex.get("limits") or []:
            print(f"    limit:      {lim}")
        for cl in ex.get("clashes") or []:
            other = cl.get("with_whom") or "?"
            point = cl.get("point") or ""
            print(f"    clash with {other}: {point}")

    # Cross-cutting findings.
    disagreements = aporia.get("disagreements") or []
    if disagreements:
        print()
        print("  ## Real disagreements")
        for d in disagreements:
            between = " vs ".join(d.get("between") or []) or "the speakers"
            print(f"    [{between}] {d.get('description', '')}")
            q = d.get("question") or ""
            if q:
                print(f"        Q: {q}")

    open_questions = aporia.get("open_questions") or []
    if open_questions:
        print()
        print("  ## Open questions")
        for q in open_questions:
            print(f"    {q.get('description', '')}")
            qq = q.get("question") or ""
            if qq:
                print(f"        Q: {qq}")

    # The flat `findings` list is what the frontend renders. Print a
    # one-liner per entry so we can see what the panel will show.
    findings = aporia.get("findings", [])
    print()
    print("  ## Frontend findings list")
    if not findings:
        print("    (no findings)")
    else:
        for f in findings:
            kind = f.get("kind") or f.get("type") or "?"
            expert = f.get("expert") or "—"
            title = f.get("title") or ""
            print(f"    [{kind}] {expert}: {title}")

    return session


def _print_turn(turn: Dict) -> None:
    speaker = turn.get("speaker", "?")
    role = turn.get("role", "?")
    ttype = turn.get("type", "?")
    label = f"[{role}/{ttype}] {speaker}"
    print()
    print(label)
    print("-" * len(label))
    # Strip emojis to keep Windows consoles happy.
    content = turn.get("content", "").encode("ascii", "replace").decode()
    print(content)


def _print_usage(label: str, usage: Dict[str, int]) -> None:
    pt = usage.get("prompt_tokens", 0)
    ct = usage.get("completion_tokens", 0)
    tt = usage.get("total_tokens", 0)
    calls = usage.get("calls", 0)
    print(f"  {label}: {calls} calls, {pt} prompt + {ct} completion = {tt} total tokens")


if __name__ == "__main__":
    raise SystemExit(main())
