"""Aporia: post-debate critical examination of each expert's argument.

Named after the Socratic concept of aporia (ἀπορία) — the productive
puzzlement that arises when examining a belief reveals its unstated
premises, its scope, and its real points of disagreement with rival
views.

What this module does:

1. For each expert who spoke in the debate, make one LLM call that sees
   *only* that expert's turns plus the topic, and asks the model to
   recover the argument's structure: the core claim, the unstated
   assumptions it rests on, the scope where it stops applying, and the
   real points of friction with the other speakers.
2. Then one synthesis call sees the per-expert summaries and the full
   transcript, and produces a list of cross-cutting points: where the
   debate actually disagrees (vs. talks past itself), and what questions
   remain genuinely open.

Why this shape: a single LLM pass over the whole transcript flattens
each expert into one bullet. Splitting per-expert gives each persona
real attention; the synthesis pass is for the things that only exist
between speakers.

Cost: N+1 LLM calls at the end of a debate, where N is the number of
speakers. With Claude Haiku 4.5 at current DO pricing, a typical
2-speaker, 6-turn debate adds ~3 calls of ~800 input + ~400 output
tokens each. Well under one cent per click.

Output contract (consumed by `frontend/src/components/AporiaPanel.vue`
and `backend/scripts/smoke_test.py`):

    {
        "role": "plato",
        "type": "aporia",
        "content": str,                    # human-readable preamble
        "findings": [                       # flat list, frontend renders each
            {
                "expert": str,              # display name, or "" for cross-cutting
                "kind": str,                # "core_claim" | "assumption" |
                                            #   "limit" | "clash" | "disagreement" |
                                            #   "open_question"
                "type": str,                # alias of `kind`, for back-compat
                "title": str,               # short heading, used by the panel
                "description": str,         # body text shown under the heading
                "detail": str,              # alias of `description`
                "question": str,            # Socratic prompt for the reader
            },
            ...
        ],
        "guidance": str,                    # human-readable footer
    }

The `findings` shape is intentionally redundant (kind/type and
description/detail and title) because the frontend renders the first
field it finds. Keep both aliases populated. `expert == ""` marks a
cross-cutting finding (disagreement or open question) rather than a
per-expert one.

If the LLM is unavailable (no MODEL_ACCESS_KEY) or returns unparseable
output, we degrade gracefully: the route returns a content-only message
explaining that analysis could not run, rather than 500-ing.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

from app.core import llm
from app.core.personas import PERSONAS, Persona


logger = logging.getLogger(__name__)


# Cap so a runaway debate doesn't balloon the LLM context. Real debates
# in this app top out at ~12 turns, so this is a safety net rather than
# a regular trim.
_MAX_TURNS_PER_EXPERT = 12
_MAX_TURN_CHARS = 1200


# ==================
# Public entry point
# ==================


def analyze(turns: List[Dict], mode: str = "simple") -> Dict:
    """Examine a finished (or in-progress) debate and return findings.

    Args:
        turns: The session history, as built by `app.agents.discourse`.
            Each dict has at least `role`, `speaker`, `content`. Plato
            turns are skipped for the per-expert analysis but kept for
            the synthesis pass's full-transcript view.
        mode: Retained for back-compat with `Aporia.analyze(..., mode=)`
            callers. Currently unused; both "simple" and "deep" run the
            same LLM-backed analysis. Kept rather than removed so any
            existing caller doesn't crash on a stray kwarg.

    Returns:
        The dict described in the module docstring. Never raises on
        LLM failure; degrades to a content-only message.
    """
    del mode  # see docstring

    expert_turns = _group_expert_turns(turns)
    topic = _infer_topic(turns)

    if not expert_turns:
        return _empty_response(reason="no_experts")

    try:
        per_expert = [
            _analyze_expert(name, persona, persona_turns, topic)
            for name, persona, persona_turns in expert_turns
        ]
        synthesis = _synthesize(per_expert, turns, topic)
    except RuntimeError as exc:
        # llm._get_client() raises RuntimeError when MODEL_ACCESS_KEY
        # is missing. Route handlers expect aporia to never blow up,
        # so we surface this as a content-only response.
        logger.warning("Aporia: LLM unavailable, returning stub. %s", exc)
        return _empty_response(reason="no_llm")
    except Exception:
        # Network/parse failures: log loudly, return stub. The Aporia
        # button is non-critical — a failure here should never break
        # the debate UI.
        logger.exception("Aporia: analysis failed, returning stub.")
        return _empty_response(reason="error")

    findings = _flatten_findings(per_expert, synthesis)
    speakers = [name for name, _persona, _turns in expert_turns]
    return _format_response(findings, speakers, per_expert, synthesis, topic)


# Back-compat: smoke_test.py imports the convenience function.
def analyze_debate(turns: List[Dict], mode: str = "simple") -> Dict:
    return analyze(turns, mode)


# ==================
# Per-expert pass
# ==================


def _analyze_expert(
    name: str,
    persona: Optional[Persona],
    persona_turns: List[Dict],
    topic: str,
) -> Dict:
    """One LLM call: recover the structure of a single expert's argument.

    Args:
        name: Display name as it appears in `turn["speaker"]`.
        persona: The `Persona` object if `name` matches a known persona,
            else None. Used only to anchor voice in the prompt; the
            analysis itself is text-grounded in the turns.
        persona_turns: Every turn by this expert, in order.
        topic: The debate topic, for context.

    Returns:
        Dict with keys `expert`, `core_claim` (str), `assumptions`
        (List[str]), `limits` (List[str]), `clashes` (List[Dict] each
        with `with_whom`, `point`). Missing keys are coerced to empty.
    """
    transcript = _format_persona_transcript(persona_turns)

    bio_line = f" ({persona.title})" if persona else ""
    system = _SYSTEM_PER_EXPERT.format(name=name, bio_line=bio_line)
    user = _USER_PER_EXPERT.format(
        name=name,
        topic=topic,
        transcript=transcript,
    )

    raw = llm.generate(
        system,
        [{"role": "user", "content": user}],
        # A little colder than the debate itself — we want analysis,
        # not flourish. Still leaves enough wiggle for the model to pick
        # genuinely different assumptions across reruns.
        temperature=0.4,
        max_tokens=700,
    )

    parsed = _parse_json_payload(raw)
    return {
        "expert": name,
        "core_claim": _as_str(parsed.get("core_claim")),
        "assumptions": _as_str_list(parsed.get("assumptions")),
        "limits": _as_str_list(parsed.get("limits")),
        "clashes": _as_clash_list(parsed.get("clashes")),
    }


# ==================
# Synthesis pass
# ==================


def _synthesize(
    per_expert: List[Dict],
    full_history: List[Dict],
    topic: str,
) -> Dict:
    """One LLM call: cross-cutting findings the per-expert pass can't see.

    Sees the per-expert summaries (so it doesn't have to re-derive them)
    plus the full transcript (so it can name *actual* disagreements
    rather than restated ones).

    Returns:
        Dict with keys `disagreements` (List[Dict] each with `between`,
        `description`, `question`) and `open_questions` (List[Dict]
        each with `description`, `question`). Missing keys coerced.
    """
    transcript = _format_full_transcript(full_history)
    summaries = json.dumps(per_expert, ensure_ascii=False, indent=2)

    system = _SYSTEM_SYNTHESIS
    user = _USER_SYNTHESIS.format(
        topic=topic,
        summaries=summaries,
        transcript=transcript,
    )

    raw = llm.generate(
        system,
        [{"role": "user", "content": user}],
        temperature=0.4,
        max_tokens=600,
    )

    parsed = _parse_json_payload(raw)
    return {
        "disagreements": _as_disagreement_list(parsed.get("disagreements")),
        "open_questions": _as_question_list(parsed.get("open_questions")),
    }


# ==================
# Flatten + format
# ==================


def _flatten_findings(per_expert: List[Dict], synthesis: Dict) -> List[Dict]:
    """Turn structured per-expert + synthesis output into flat findings.

    The frontend's `AporiaPanel` iterates one list. We map each piece
    of structure (claim, assumption, limit, clash, disagreement,
    open question) to one finding entry, in a stable reading order:

    1. Each expert's core claim, then their assumptions, then their
       limits, then their named clashes — one expert at a time.
    2. Then cross-cutting disagreements.
    3. Then open questions.

    This is also the rendering order in the human-readable `content`.
    """
    findings: List[Dict] = []

    for ex in per_expert:
        name = ex["expert"]
        if ex["core_claim"]:
            findings.append(_finding(
                expert=name,
                kind="core_claim",
                title=f"{name}: core claim",
                description=ex["core_claim"],
                question=f"Is this really {name}'s claim, or a rhetorical wrapping?",
            ))
        for a in ex["assumptions"]:
            findings.append(_finding(
                expert=name,
                kind="assumption",
                title=f"{name}: assumption",
                description=a,
                question="Would the argument survive if this assumption failed?",
            ))
        for lim in ex["limits"]:
            findings.append(_finding(
                expert=name,
                kind="limit",
                title=f"{name}: scope limit",
                description=lim,
                question="Outside this scope, what argument would have to take over?",
            ))
        for cl in ex["clashes"]:
            other = cl.get("with_whom") or "another speaker"
            point = cl.get("point") or ""
            findings.append(_finding(
                expert=name,
                kind="clash",
                title=f"{name} vs. {other}",
                description=point,
                question=f"On this point, what evidence would change {name}'s mind? What about {other}'s?",
            ))

    for d in synthesis["disagreements"]:
        between = d.get("between") or []
        between_str = " and ".join(between) if between else "the speakers"
        findings.append(_finding(
            expert="",
            kind="disagreement",
            title=f"Real disagreement: {between_str}",
            description=d.get("description", ""),
            question=d.get("question") or "What would settle this?",
        ))

    for q in synthesis["open_questions"]:
        findings.append(_finding(
            expert="",
            kind="open_question",
            title="Open question",
            description=q.get("description", ""),
            question=q.get("question") or "",
        ))

    return findings


def _finding(*, expert: str, kind: str, title: str, description: str, question: str) -> Dict:
    """Build a finding dict with both new and legacy field names populated.

    `kind` is the canonical category; `type` is its alias so any
    pre-existing consumer that grouped by `type` still works.
    Likewise `detail` aliases `description` so the frontend's
    `f.detail ?? f.description` lookup finds something either way.
    """
    return {
        "expert": expert,
        "kind": kind,
        "type": kind,
        "title": title,
        "description": description,
        "detail": description,
        "question": question,
    }


def _format_response(
    findings: List[Dict],
    speakers: List[str],
    per_expert: List[Dict],
    synthesis: Dict,
    topic: str,
) -> Dict:
    """Build the final response dict.

    The `content` field is Plato's prose preamble — a brief
    orientation, not the full analysis (the panel renders the
    structured findings beneath it). The closing sermon goes in
    `guidance`. Both are intentionally short.
    """
    if speakers:
        if len(speakers) == 1:
            who = speakers[0]
        elif len(speakers) == 2:
            who = f"{speakers[0]} and {speakers[1]}"
        else:
            who = ", ".join(speakers[:-1]) + f", and {speakers[-1]}"
    else:
        who = "the speakers"

    content = (
        "Aporia.\n\n"
        f"I have re-read the dialogue between {who} on the question of {topic}. "
        "What follows is not a verdict. It is a map of the ground each "
        "argument actually stands on — the claims made, the assumptions "
        "those claims rest on, the limits beyond which they no longer "
        "apply, and the points where the speakers genuinely diverge "
        "rather than merely talk past one another."
    )

    guidance = (
        "Aporia is not a weakness. It is the beginning of wisdom. "
        "Each assumption above is a place where the argument could fail "
        "and where your own judgment must enter. Press on the assumptions "
        "you find least credible; let the limits tell you which expert's "
        "frame fits the part of the problem you actually care about."
    )

    return {
        "role": "plato",
        "type": "aporia",
        "content": content,
        "findings": findings,
        "guidance": guidance,
        # Optional structured fields, for callers (or future frontend
        # work) that want to render expert cards rather than a flat
        # list. Not depended on by the current UI.
        "experts": per_expert,
        "disagreements": synthesis["disagreements"],
        "open_questions": synthesis["open_questions"],
        "speakers": speakers,
    }


def _empty_response(*, reason: str) -> Dict:
    """Degraded response when analysis can't run. Never the steady state."""
    if reason == "no_experts":
        content = (
            "Aporia.\n\n"
            "The dialogue has not yet produced an expert turn. Let the "
            "speakers state their positions, then return."
        )
    elif reason == "no_llm":
        content = (
            "Aporia.\n\n"
            "The model that performs this analysis is not configured "
            "on this instance. Set MODEL_ACCESS_KEY in backend/.env "
            "and try again."
        )
    else:
        content = (
            "Aporia.\n\n"
            "I could not complete the examination. The dialogue stands "
            "as it is; read it again with your own ear."
        )
    return {
        "role": "plato",
        "type": "aporia",
        "content": content,
        "findings": [],
        "guidance": "",
        "experts": [],
        "disagreements": [],
        "open_questions": [],
        "speakers": [],
    }


# ==================
# Button info (consumed by /aporia/button)
# ==================


def get_button_info() -> Dict:
    return {
        "label": "Aporia",
        "description": "Examine each expert's claims, assumptions, and limits.",
        "tooltip": "Aporia: surface the premises and points of real disagreement.",
        "icon": "A",
    }


# ==================
# Prompts
# ==================


_SYSTEM_PER_EXPERT = """You are a philosophical analyst working in the Socratic tradition. Your job is to examine one speaker's contribution to a debate and recover the structure of their argument: the claim, the premises it rests on, the scope where it applies, and the points where it engages — or fails to engage — with rival views.

You are analyzing {name}{bio_line}.

Be rigorous, not generous. Do not paraphrase what the speaker said and call it an assumption — an assumption is something they did NOT say but their argument requires to be true. Do not list rhetorical hedges as limits — a limit is a real scope condition outside which their argument stops applying. Quote no one verbatim; render claims in your own neutral prose.

Output STRICT JSON with this exact shape, and nothing else:

{{
  "core_claim": "<one or two sentences: the main argument this speaker advanced. Not a summary of what they said, but the proposition they want the audience to walk away believing.>",
  "assumptions": [
    "<an unstated premise their argument depends on. Stated as a proposition someone could agree or disagree with.>",
    "<another assumption, if any. 1-3 total. Quality over quantity. If only one is genuinely present, return only one.>"
  ],
  "limits": [
    "<a real scope condition: where, when, or under what circumstance the argument stops applying. 1-3 total.>"
  ],
  "clashes": [
    {{"with_whom": "<other speaker's name as it appears in the transcript>", "point": "<one sentence stating the substantive point on which they actually diverge, not a stylistic difference>"}}
  ]
}}

If a field has no genuine content for this speaker, return an empty array (or an empty string for core_claim). Do not invent. Do not pad. Return only the JSON object."""


_USER_PER_EXPERT = """Topic of the debate: {topic}

Below are all of {name}'s contributions to the debate, in order. Read them carefully, then produce the analysis described in the system instructions.

--- {name}'s turns ---
{transcript}
--- end ---

Return only the JSON object."""


_SYSTEM_SYNTHESIS = """You are a philosophical analyst working in the Socratic tradition. You have already received structured summaries of each speaker in a debate. Your job now is to do what no single per-speaker analysis can do: identify the cross-cutting tensions in the debate as a whole.

Two distinct things to surface:

1. REAL disagreements — points where two or more speakers actually contradict each other on a substantive question, not where they merely emphasize different things or use different vocabulary for the same underlying claim. If the speakers are talking past each other, name that explicitly as the disagreement.

2. OPEN questions — questions raised by the debate (explicitly or implicitly by what nobody addressed) that none of the speakers answered. These should be questions whose answer would meaningfully change which speaker is right.

Be parsimonious. A debate with no real disagreement should yield an empty disagreements array. A debate that closes every question it raises should yield an empty open_questions array. Quality over quantity: 1-3 of each is usually right.

Output STRICT JSON with this exact shape, and nothing else:

{
  "disagreements": [
    {
      "between": ["<speaker A>", "<speaker B>"],
      "description": "<one or two sentences naming the substantive proposition they disagree on>",
      "question": "<a Socratic question that, if answered, would resolve the disagreement>"
    }
  ],
  "open_questions": [
    {
      "description": "<one or two sentences naming the question the debate left unanswered>",
      "question": "<the question itself, phrased as a question the reader could carry forward>"
    }
  ]
}

Return only the JSON object."""


_USER_SYNTHESIS = """Topic of the debate: {topic}

Per-speaker analyses already produced:
{summaries}

Full transcript (for grounding — do not re-summarize per-speaker, just use it to verify what each speaker actually said):
--- transcript ---
{transcript}
--- end ---

Return only the JSON object."""


# ==================
# Helpers
# ==================


def _group_expert_turns(turns: List[Dict]) -> List[tuple]:
    """Group expert turns by speaker, preserving first-appearance order.

    Returns a list of (display_name, Persona | None, [turn, ...]). Plato
    turns are skipped. We look up the persona by `persona_id` if set
    (cheap, set on every expert turn by `discourse.py`), else by name.
    The persona is optional in the prompt — used only to add the bio
    line — so a miss is fine.
    """
    order: List[str] = []
    by_name: Dict[str, List[Dict]] = {}
    persona_by_name: Dict[str, Optional[Persona]] = {}

    for t in turns:
        if t.get("role") != "expert":
            continue
        name = t.get("speaker") or "Unknown"
        if name not in by_name:
            order.append(name)
            by_name[name] = []
            pid = t.get("persona_id")
            persona_by_name[name] = PERSONAS.get(pid) if pid else _persona_by_name(name)
        by_name[name].append(t)

    return [
        (name, persona_by_name[name], by_name[name][:_MAX_TURNS_PER_EXPERT])
        for name in order
    ]


def _persona_by_name(name: str) -> Optional[Persona]:
    for p in PERSONAS.values():
        if p.name == name:
            return p
    return None


def _infer_topic(turns: List[Dict]) -> str:
    """Recover the topic from Plato's opening turn, with a fallback.

    `discourse.py` builds the opening with `Plato.opening(topic, ...)`
    in `app/agents/plato.py`, which renders the topic inside `**...**`
    markdown bold on the "The question before us is:" line. We pull it
    back out by matching that line. If the template ever changes, fall
    back to a neutral placeholder so the prompts still run.
    """
    for t in turns:
        if t.get("role") == "plato" and t.get("type") == "opening":
            content = t.get("content", "")
            # Primary: the literal template "The question before us is: **<topic>**"
            m = re.search(r"The question before us is:\s*\*\*(.+?)\*\*", content)
            if m:
                return m.group(1).strip()
            # Loosened fallback if the bold markers ever disappear.
            m = re.search(r"The question before us is:\s*(.+?)[\n\r]", content)
            if m:
                return m.group(1).strip().strip("*").strip()
    return "the topic at hand"


def _format_persona_transcript(persona_turns: List[Dict]) -> str:
    """Render one expert's turns as a numbered block, truncated per turn."""
    lines = []
    for i, t in enumerate(persona_turns, start=1):
        content = (t.get("content") or "").strip()
        if len(content) > _MAX_TURN_CHARS:
            content = content[:_MAX_TURN_CHARS].rstrip() + "..."
        lines.append(f"[turn {i}] {content}")
    return "\n\n".join(lines) if lines else "(no turns)"


def _format_full_transcript(turns: List[Dict]) -> str:
    """Render the full debate, lightly truncated per turn, including Plato."""
    lines = []
    for t in turns:
        speaker = t.get("speaker") or t.get("role") or "?"
        content = (t.get("content") or "").strip()
        if len(content) > _MAX_TURN_CHARS:
            content = content[:_MAX_TURN_CHARS].rstrip() + "..."
        lines.append(f"{speaker}: {content}")
    return "\n\n".join(lines) if lines else "(no turns)"


# ==================
# JSON parsing
# ==================


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_payload(raw: str) -> Dict:
    """Best-effort JSON extraction from an LLM response.

    The system prompts demand a bare JSON object, but models routinely
    wrap output in ```json ... ``` fences, add a leading "Here is the
    analysis:", or trail explanatory prose. We strip fences, then fall
    back to a regex that grabs the first {...} span. If both fail, we
    log and return {} — the per-field coercers below treat missing
    keys as empty, so a bad parse degrades to "no findings for this
    speaker" rather than 500-ing the route.
    """
    if not raw:
        return {}
    # Strip code fences.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    # Try direct parse.
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        pass
    # Try to grab the first {...} span.
    m = _JSON_OBJECT_RE.search(cleaned)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            pass
    logger.warning("Aporia: could not parse LLM JSON output. Raw: %s", raw[:300])
    return {}


def _as_str(v) -> str:
    if isinstance(v, str):
        return v.strip()
    return ""


def _as_str_list(v) -> List[str]:
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _as_clash_list(v) -> List[Dict]:
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        if not isinstance(item, dict):
            continue
        with_whom = _as_str(item.get("with_whom"))
        point = _as_str(item.get("point"))
        if point:  # with_whom is allowed to be empty; point isn't
            out.append({"with_whom": with_whom, "point": point})
    return out


def _as_disagreement_list(v) -> List[Dict]:
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        if not isinstance(item, dict):
            continue
        between = item.get("between")
        between_list = [_as_str(x) for x in between if _as_str(x)] if isinstance(between, list) else []
        description = _as_str(item.get("description"))
        question = _as_str(item.get("question"))
        if description:
            out.append({
                "between": between_list,
                "description": description,
                "question": question,
            })
    return out


def _as_question_list(v) -> List[Dict]:
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        if not isinstance(item, dict):
            continue
        description = _as_str(item.get("description"))
        question = _as_str(item.get("question"))
        if description or question:
            out.append({"description": description, "question": question})
    return out


# ==================
# Back-compat class facade
# ==================
#
# routes.py and smoke_test.py both call `Aporia.analyze(...)` and
# `Aporia.get_button_info()` as classmethods on a class. Keep a thin
# class shim so we don't have to touch them.


class Aporia:
    """Facade preserved for back-compat. Real logic is module-level."""

    @staticmethod
    def analyze(turns: List[Dict], mode: str = "simple") -> Dict:
        return analyze(turns, mode)

    @staticmethod
    def get_button_info() -> Dict:
        return get_button_info()
