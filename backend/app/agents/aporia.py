"""Aporia: post-debate dialectical examination of each expert's argument.

Named after the Socratic aporia (ἀπορία) — the productive puzzlement
that arises when an argument is taken apart into the premises it
needs, the inferential moves it makes, and the things it says that
cannot all be true at once.

Shape of the analysis: for each expert who spoke, one LLM call that
sees *only* that expert's turns plus the topic, and returns three
categories of dialectical critique:

  1. Assumptions  — unstated premises the argument depends on.
  2. Fallacies    — named errors of reasoning in what they said.
  3. Contradictions — places where their own statements pull
     against each other, or against something they implicitly granted.

No preamble, no closing sermon, no cross-speaker synthesis. The
structure *is* the analysis. One LLM call per speaker; nothing more.

Cost: N LLM calls at the end of a debate, where N is the number of
speakers. With Claude Haiku 4.5 on DO Inference that's well under a
cent per click for a 2-speaker debate.

Output contract (consumed by `frontend/src/components/AporiaPanel.vue`,
`backend/scripts/smoke_test.py`):

    {
        "role": "plato",
        "type": "aporia",
        "content": "",                      # intentionally empty
        "guidance": "",                     # intentionally empty
        "speakers": [str, ...],
        "experts": [
            {
                "expert": str,              # display name
                "assumptions":    [{"point": str, "why": str}, ...],
                "fallacies":      [{"name": str, "point": str, "why": str}, ...],
                "contradictions": [{"point": str, "why": str}, ...],
            },
            ...
        ],
        "findings": [                       # flat back-compat view
            {
                "expert": str,
                "kind": "assumption" | "fallacy" | "contradiction",
                "type": str,                # alias of kind
                "title": str,               # short heading
                "description": str,         # the dialectical point + why
                "detail": str,              # alias of description
            },
            ...
        ],
    }

The flat `findings` list is preserved for back-compat with any caller
(smoke tests, older clients) that iterated it. The frontend renders
the structured `experts[]` view; `findings[]` is its fallback.

If the LLM is unavailable (no MODEL_ACCESS_KEY) or returns unparseable
output, we degrade gracefully: the route returns an empty-experts
response with a short content message rather than 500-ing.
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
            turns are skipped — they moderate, they don't make claims.
        mode: Retained for back-compat with `Aporia.analyze(..., mode=)`
            callers. Currently unused. Kept rather than removed so any
            existing caller doesn't crash on a stray kwarg.

    Returns:
        The dict described in the module docstring. Never raises on
        LLM failure; degrades to an empty-experts response.
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
    except RuntimeError as exc:
        # llm._get_client() raises RuntimeError when MODEL_ACCESS_KEY
        # is missing. Route handlers expect aporia to never blow up,
        # so we surface this as an empty response.
        logger.warning("Aporia: LLM unavailable, returning stub. %s", exc)
        return _empty_response(reason="no_llm")
    except Exception:
        # Network/parse failures: log loudly, return stub. The Aporia
        # button is non-critical — a failure here should never break
        # the debate UI.
        logger.exception("Aporia: analysis failed, returning stub.")
        return _empty_response(reason="error")

    speakers = [name for name, _persona, _turns in expert_turns]
    findings = _flatten_findings(per_expert)
    return {
        "role": "plato",
        "type": "aporia",
        "content": "",
        "guidance": "",
        "speakers": speakers,
        "experts": per_expert,
        "findings": findings,
    }


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
    """One LLM call: three dialectical categories for one speaker.

    Returns:
        Dict with keys `expert`, `assumptions` (List[Dict]),
        `fallacies` (List[Dict]), `contradictions` (List[Dict]).
        Each list item is `{point, why}` (or `{name, point, why}` for
        fallacies). Missing keys are coerced to empty.
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
        # Cold: we want rigor, not flourish.
        temperature=0.3,
        max_tokens=700,
    )

    parsed = _parse_json_payload(raw)
    return {
        "expert": name,
        "assumptions": _as_point_list(parsed.get("assumptions")),
        "fallacies": _as_fallacy_list(parsed.get("fallacies")),
        "contradictions": _as_point_list(parsed.get("contradictions")),
    }


# ==================
# Flatten for back-compat findings list
# ==================


def _flatten_findings(per_expert: List[Dict]) -> List[Dict]:
    """Render the structured per-expert output as a flat list.

    Kept so any consumer that iterated the old `findings[]` (smoke
    tests, older clients) still has something to iterate. The frontend
    prefers the structured `experts[]` view.

    Reading order, per expert in turn: assumptions, then fallacies,
    then contradictions.
    """
    findings: List[Dict] = []

    for ex in per_expert:
        name = ex["expert"]
        for a in ex["assumptions"]:
            findings.append(_finding(
                expert=name,
                kind="assumption",
                title=f"{name}: assumption",
                description=_combine(a.get("point"), a.get("why")),
            ))
        for f in ex["fallacies"]:
            heading = f.get("name") or "fallacy"
            findings.append(_finding(
                expert=name,
                kind="fallacy",
                title=f"{name}: {heading}",
                description=_combine(f.get("point"), f.get("why")),
            ))
        for c in ex["contradictions"]:
            findings.append(_finding(
                expert=name,
                kind="contradiction",
                title=f"{name}: contradiction",
                description=_combine(c.get("point"), c.get("why")),
            ))

    return findings


def _combine(point: Optional[str], why: Optional[str]) -> str:
    """Join the dialectical point and its 'why' into one paragraph."""
    p = (point or "").strip()
    w = (why or "").strip()
    if p and w:
        return f"{p} — {w}"
    return p or w


def _finding(*, expert: str, kind: str, title: str, description: str) -> Dict:
    """Build a flat-finding dict with both new and legacy field names.

    `kind` is the canonical category; `type` is its alias for any
    pre-existing consumer that grouped by `type`. `detail` aliases
    `description` so the panel's `f.detail ?? f.description` lookup
    finds something either way.
    """
    return {
        "expert": expert,
        "kind": kind,
        "type": kind,
        "title": title,
        "description": description,
        "detail": description,
    }


def _empty_response(*, reason: str) -> Dict:
    """Degraded response when analysis can't run.

    We still set `content` here (briefly) because the structured
    `experts[]` is empty — the frontend has nothing else to render,
    so a single line explains why.
    """
    if reason == "no_experts":
        content = "The dialogue has not yet produced an expert turn."
    elif reason == "no_llm":
        content = (
            "The model that performs this analysis is not configured "
            "on this instance."
        )
    else:
        content = "Examination could not complete."
    return {
        "role": "plato",
        "type": "aporia",
        "content": content,
        "guidance": "",
        "speakers": [],
        "experts": [],
        "findings": [],
    }


# ==================
# Button info (consumed by /aporia/button)
# ==================


def get_button_info() -> Dict:
    return {
        "label": "Aporia",
        "description": "Surface each speaker's assumptions, fallacies, and contradictions.",
        "tooltip": "Aporia: a dialectical breakdown of the arguments made.",
        "icon": "A",
    }


# ==================
# Prompts
# ==================


_SYSTEM_PER_EXPERT = """You are a philosophical analyst working in the Socratic-dialectical tradition. You examine one speaker's contribution to a debate and produce a rigorous, point-by-point critique under three fixed headings: assumptions, fallacies, and contradictions.

You are analyzing {name}{bio_line}.

Definitions — hold to these strictly:

- ASSUMPTION: an unstated premise the speaker's argument requires to be true. It is NOT something they said; it is something they did NOT say but had to be granted for what they said to follow. State it as a proposition that someone could agree or disagree with.

- FALLACY: a specific, named error of reasoning in what the speaker actually said. Use the established name (e.g. "appeal to authority", "hasty generalization", "equivocation", "false dichotomy", "post hoc", "begging the question", "ad hominem", "straw man", "no true Scotsman", "composition", "division", "non sequitur"). If you cannot name a specific fallacy, do not list one — better an empty list than vague hand-waving.

- CONTRADICTION: a place where two things the speaker said cannot both be true, OR where what they said pulls against something they implicitly granted earlier in the same turn or in another. Quote nothing verbatim; render the conflict in your own neutral prose.

Be parsimonious. Quality over quantity. Each list should contain 0 to 3 items. If a category has no genuine content for this speaker, return an empty array — do NOT invent items to fill space. A speaker who reasoned cleanly may legitimately have zero fallacies.

Each item must include a tight one-clause "point" and a one-sentence "why" that justifies the diagnosis with reference to what the speaker actually said.

Output STRICT JSON with this exact shape, and nothing else:

{{
  "assumptions": [
    {{"point": "<the unstated premise, as a proposition>", "why": "<one sentence: why the argument needs this to be true>"}}
  ],
  "fallacies": [
    {{"name": "<established name of the fallacy>", "point": "<what move in the argument commits it>", "why": "<one sentence: why that move is fallacious here>"}}
  ],
  "contradictions": [
    {{"point": "<the conflict, stated as two claims that can't both hold>", "why": "<one sentence: how the speaker is committed to both>"}}
  ]
}}

Return only the JSON object. No preamble, no closing remarks, no code fences."""


_USER_PER_EXPERT = """Topic of the debate: {topic}

Below are all of {name}'s contributions to the debate, in order. Read them carefully, then produce the three-category dialectical critique described in the system instructions.

--- {name}'s turns ---
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


# ==================
# JSON parsing
# ==================


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_payload(raw: str) -> Dict:
    """Best-effort JSON extraction from an LLM response.

    The system prompt demands a bare JSON object, but models routinely
    wrap output in ```json ... ``` fences, add a leading "Here is the
    analysis:", or trail explanatory prose. We strip fences, then fall
    back to a regex that grabs the first {...} span. If both fail, we
    log and return {} — the per-field coercers below treat missing
    keys as empty, so a bad parse degrades to "no findings for this
    speaker" rather than 500-ing the route.
    """
    if not raw:
        return {}
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        pass
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


def _as_point_list(v) -> List[Dict]:
    """Coerce a list of `{point, why}` items, dropping empties."""
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        if not isinstance(item, dict):
            continue
        point = _as_str(item.get("point"))
        why = _as_str(item.get("why"))
        if point or why:
            out.append({"point": point, "why": why})
    return out


def _as_fallacy_list(v) -> List[Dict]:
    """Coerce a list of `{name, point, why}` items, dropping empties."""
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        if not isinstance(item, dict):
            continue
        name = _as_str(item.get("name"))
        point = _as_str(item.get("point"))
        why = _as_str(item.get("why"))
        # A nameless fallacy isn't worth listing — the rigor comes
        # from naming the move.
        if name and (point or why):
            out.append({"name": name, "point": point, "why": why})
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
