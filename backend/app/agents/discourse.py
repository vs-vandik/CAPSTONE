"""Debate loop: drives one Socratic discourse session forward by one turn.

Design:

- Each call to `next_turn(session)` advances the dialogue by exactly one
  turn (Plato or expert) and mutates `session["history"]` in place.
- The frontend drives the loop. It calls /discourse/{id}/next repeatedly
  until the session is `done`.
- Plato segments the dialogue: opening (turn 0), then a transition between
  every pair of expert turns, then a closing once `max_turns` expert
  turns have been spoken.
- Experts speak round-robin in the order they appear in `persona_ids`.
- News context is fetched once on first expert turn, cached on the
  session, and injected into every expert's system prompt thereafter.
- Knowledge retrieval is delegated to `_retrieve_quotes` which is a
  placeholder until `app.knowledge.store` exists; for now it returns the
  persona's `seed_quotes`. The signature won't change when we wire
  Chroma in.

A session's `history` is a list of `Turn` dicts:

    {"role": "plato"|"expert", "speaker": str, "type": str, "content": str}

`speaker` is the persona display name for experts, "Plato" for plato.
`type` mirrors the existing Plato dict types ("opening", "transition",
"closing", "expert").
"""

from typing import Dict, List, Optional

from app.agents.plato import Plato, TurnContext
from app.core import llm
from app.core.personas import Persona, get as get_persona
from app.knowledge import news


# How many expert turns we want before Plato closes the session. Stored on
# the session as `max_turns` at /discourse/start time.
DEFAULT_MAX_TURNS = 6


# ==================
# Public entry point
# ==================


def next_turn(session: Dict) -> Dict:
    """Advance the session by one turn and return the new turn.

    Mutates `session["history"]` in place. Also sets `session["status"]`
    to "active" or "done" so callers know whether to keep polling.

    Args:
        session: The mutable session dict from `discourse_sessions`.

    Returns:
        The new turn dict that was appended to history. Includes a
        `done: bool` field to make the frontend's life easier.
    """
    history: List[Dict] = session.setdefault("history", [])
    persona_ids: List[str] = session["persona_ids"]
    topic: str = session["topic"]
    max_turns: int = session.get("max_turns", DEFAULT_MAX_TURNS)

    expert_turns_so_far = sum(1 for t in history if t.get("role") == "expert")

    # --- 1. Opening: very first turn of the session ---
    if not history:
        speakers = [get_persona(pid).name for pid in persona_ids]
        turn = Plato.opening(topic, speakers)
        turn["speaker"] = "Plato"
        return _append(session, turn, done=False)

    # --- 2. Closing: we've hit the expert turn budget ---
    if expert_turns_so_far >= max_turns and history[-1].get("role") == "expert":
        turn = Plato.closing(topic, history)
        turn["speaker"] = "Plato"
        session["status"] = "done"
        return _append(session, turn, done=True)

    # --- 3. Plato transition: between expert turns, after at least one expert has spoken ---
    last = history[-1]
    if last.get("role") == "expert" and expert_turns_so_far < max_turns:
        next_persona = _next_expert(persona_ids, history)
        # Build the context ourselves rather than calling plato.create_context,
        # which indexes into the speakers list using turn_number and breaks
        # for round-robin debates with more turns than speakers.
        ctx = TurnContext(
            turn_number=expert_turns_so_far + 1,
            topic=topic,
            speakers=[get_persona(pid).name for pid in persona_ids],
            current_speaker=next_persona.name,
            previous_speaker=last.get("speaker"),
        )
        turn = Plato.transition(ctx, previous_content=last.get("content", ""))
        turn["speaker"] = "Plato"
        return _append(session, turn, done=False)

    # --- 4. Expert turn ---
    persona = _next_expert(persona_ids, history)
    content = _generate_expert_turn(persona, session)
    turn = {
        "role": "expert",
        "type": "expert",
        "speaker": persona.name,
        "persona_id": persona.id,
        "content": content,
    }
    return _append(session, turn, done=False)


# ==================
# Internals
# ==================


def _append(session: Dict, turn: Dict, *, done: bool) -> Dict:
    """Append a turn to history and return it with `done` flag."""
    session.setdefault("history", []).append(turn)
    if done:
        session["status"] = "done"
    else:
        session.setdefault("status", "active")
    out = dict(turn)
    out["done"] = done
    return out


def _next_expert(persona_ids: List[str], history: List[Dict]) -> Persona:
    """Round-robin pick of the next expert based on how many turns each has had."""
    expert_history = [t for t in history if t.get("role") == "expert"]
    idx = len(expert_history) % len(persona_ids)
    return get_persona(persona_ids[idx])


def _generate_expert_turn(persona: Persona, session: Dict) -> str:
    """Build the system prompt + chat history and call the LLM."""
    quotes = _retrieve_quotes(persona, session["topic"])
    news_snippets = _get_or_fetch_news(session)

    system = _build_system_prompt(persona, session["topic"], quotes, news_snippets)
    messages = _history_as_messages(session["history"], speaker_name=persona.name)

    return llm.generate(system, messages)


def _build_system_prompt(
    persona: Persona,
    topic: str,
    quotes: List[str],
    news_snippets: List[Dict],
) -> str:
    """Assemble the persona system prompt.

    Order matters: identity, voice, refusals, then context (quotes + news),
    then the task. Putting the task last gives the model the strongest
    recency bias toward what we want it to actually do.
    """
    parts = [
        f"You are {persona.name}, {persona.title}.",
        f"Bio: {persona.bio}",
        "",
        f"Voice and style: {persona.voice}",
    ]

    if persona.refuses:
        parts.append("")
        parts.append("You will not:")
        for r in persona.refuses:
            parts.append(f"- {r}")

    if quotes:
        parts.append("")
        parts.append(
            "Things you have actually said or written (use to ground your "
            "voice — paraphrase, do not quote verbatim unless natural):"
        )
        for q in quotes:
            parts.append(f"- {q}")

    news_block = news.format_for_prompt(news_snippets)
    if news_block:
        parts.append("")
        parts.append(news_block)

    parts.extend([
        "",
        f"Topic of debate: {topic}",
        "",
        "Speak as yourself. 2-4 short paragraphs. Engage with what the "
        "previous speaker said when there is one. Do not break character. "
        "Do not announce yourself ('As Warren Buffett, I...'); just speak.",
    ])

    return "\n".join(parts)


def _history_as_messages(history: List[Dict], *, speaker_name: str) -> List[Dict]:
    """Convert session history into OpenAI chat messages.

    The current persona's previous turns are `assistant`. Everyone else
    (other experts and Plato) becomes a labeled `user` message so the
    model has clear attribution without us inventing more roles.
    """
    out: List[Dict] = []
    for turn in history:
        content = turn.get("content", "")
        speaker = turn.get("speaker", "Unknown")
        if speaker == speaker_name:
            out.append({"role": "assistant", "content": content})
        else:
            out.append({"role": "user", "content": f"[{speaker}]: {content}"})

    # Make sure the model has *something* to respond to. If the last
    # message is from this same persona (shouldn't normally happen), nudge
    # it forward.
    if not out or out[-1]["role"] == "assistant":
        out.append({"role": "user", "content": "It is your turn. Speak."})

    return out


# ==================
# News + knowledge retrieval
# ==================


def _get_or_fetch_news(session: Dict) -> List[Dict]:
    """Fetch news for the topic once per session, cache on the session dict."""
    if "news" in session:
        return session["news"]
    snippets = news.fetch_topic_context(session["topic"])
    session["news"] = snippets
    return snippets


def _retrieve_quotes(persona: Persona, topic: str) -> List[str]:
    """Retrieve persona-relevant quotes for this topic.

    Placeholder: returns the persona's seed_quotes verbatim. Step 6
    replaces this with Chroma retrieval (full tier) and in-memory cosine
    over seed_quotes (curated tier). The signature stays the same.
    """
    return list(persona.seed_quotes)
