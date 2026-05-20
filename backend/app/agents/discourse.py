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
- Knowledge retrieval is delegated to `_retrieve_evidence`. It retrieves
  fresh persona-corpus chunks per expert turn from the topic plus recent
  debate context, then injects them into the private system prompt only.

A session's `history` is a list of `Turn` dicts:

    {"role": "plato"|"expert"|"user", "speaker": str, "type": str, "content": str}

`speaker` is the persona display name for experts, "Plato" for plato,
and the participant's chosen name for user turns.
`type` mirrors the existing Plato dict types ("opening", "transition",
"closing", "expert", "user_input").
"""

from typing import Dict, List, Optional

from app.agents.plato import Plato, TurnContext
from app.core import llm
from app.core.personas import Persona, get as get_persona
from app.knowledge import news
from app.knowledge import store as knowledge_store


# How many expert turns we want before Plato closes the session. Stored on
# the session as `max_turns` at /discourse/start time.
DEFAULT_MAX_TURNS = 6

# Keep expert turns compact while leaving enough room for persona voice, humor,
# and paragraph breaks. Plato and Aporia keep using the global LLM setting.
EXPERT_TURN_MAX_TOKENS = 190
EVIDENCE_PER_TURN = 5
RETRIEVAL_CONTEXT_TURNS = 3
MESSAGE_CONTEXT_TURNS = 8
EVIDENCE_MAX_CHARS = 1100


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
    user_name: str = session.get("user_name") or "the user"
    max_turns: int = session.get("max_turns", DEFAULT_MAX_TURNS)

    expert_turns_so_far = sum(1 for t in history if t.get("role") == "expert")
    last = history[-1] if history else None

    # --- 1. Opening: very first turn of the session ---
    if not history:
        speakers = [get_persona(pid).name for pid in persona_ids]
        turn = Plato.opening(topic, speakers, user_name=user_name)
        turn["speaker"] = "Plato"
        return _append(session, turn, done=False)

    # --- 2. Closing: we've hit the expert turn budget ---
    if expert_turns_so_far >= max_turns and last.get("role") in {"expert", "user"}:
        turn = Plato.closing(topic, history)
        turn["speaker"] = "Plato"
        session["status"] = "done"
        return _append(session, turn, done=True)

    # --- 3. Plato transition: after an expert or user turn, before the next expert ---
    if last.get("role") in {"expert", "user"} and expert_turns_so_far < max_turns:
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
        if last.get("role") == "user":
            turn = Plato.user_transition(ctx, previous_content=last.get("content", ""))
        else:
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
    evidence = _retrieve_evidence(persona, session)
    news_snippets = _get_or_fetch_news(session)
    previous_expert = _previous_expert_turn(session["history"], persona)
    latest_user_turn = _latest_user_turn(session["history"])

    system = _build_system_prompt(
        persona,
        session["topic"],
        evidence,
        news_snippets,
        previous_expert,
        session.get("user_name") or "the user",
        latest_user_turn,
    )
    messages = _history_as_messages(session["history"], speaker_name=persona.name)

    return llm.generate(system, messages, max_tokens=EXPERT_TURN_MAX_TOKENS)


def _build_system_prompt(
    persona: Persona,
    topic: str,
    evidence: List[knowledge_store.RetrievedChunk],
    news_snippets: List[Dict],
    previous_expert: Optional[Dict] = None,
    user_name: str = "the user",
    latest_user_turn: Optional[Dict] = None,
) -> str:
    """Assemble the persona system prompt.

    Order matters: identity, voice, refusals, then context (evidence + news),
    then the task. Putting the task last gives the model the strongest
    recency bias toward what we want it to actually do.
    """
    parts = [
        f"You are {persona.name}, {persona.title}.",
        f"Bio: {persona.bio}",
        "",
        f"Voice and style: {persona.voice}",
        "",
        (
            "Quality priority: the point of this product is the expert's "
            "distinctive mind. Never flatten into generic AI commentary. If "
            "there is tension between speed, brevity, and persona, preserve "
            "persona. Keep the quirks, favorite obsessions, private "
            "vocabulary, humor, metaphors, and argumentative habits that make "
            "this expert recognizable. When you must shorten, cut the second "
            "argument, the throat-clearing, and the abstract explanation; do "
            "not cut the persona's signature turn of mind."
        ),
    ]

    persona_guidance = _persona_turn_guidance(persona)
    if persona_guidance:
        parts.extend(["", persona_guidance])

    spoken_guidance = _spoken_turn_guidance(persona)
    if spoken_guidance:
        parts.extend(["", spoken_guidance])

    if persona.refuses:
        parts.append("")
        parts.append("You will not:")
        for r in persona.refuses:
            parts.append(f"- {r}")

    parts.extend([
        "",
        (
            f"The human participant is {user_name}. They proposed the topic "
            "and are the third participant in this exchange, alongside the "
            "two experts. Keep their concern in mind, but do not bend your "
            "philosophy toward them just because they asked the question. "
            f"When it feels natural, refer to {user_name} by name, but do "
            "not force the name into every answer."
        ),
        "",
        (
            "Dialectical stance: you are not here to find polite consensus. "
            "Stand inside your own philosophy and defend it hard. Treat the "
            "previous speaker's answer, and the user's framing when relevant, "
            "as claims to be tested. Identify at least one weak premise, "
            "false comfort, contradiction, category error, naive assumption, "
            "or hidden incentive in what has just been said. You may grant a "
            "small point, but agreement must be tactical and subordinate to "
            "your challenge. Do not harmonize the debate into a balanced "
            "middle position unless that is genuinely your persona's view."
        ),
    ])

    if latest_user_turn:
        latest_user_input = _compact_text(
            latest_user_turn.get("content", ""),
            max_chars=700,
        )
        parts.extend([
            "",
            f"Latest input from {user_name}:",
            latest_user_input,
            (
                "Treat this as live participant input, not background noise. "
                "Answer it when relevant, but do not automatically accept its "
                "framing. If the user's question contains a weak assumption, "
                "soft premise, or wishful conclusion, challenge it directly "
                "from your worldview. Do this naturally inside your argument; "
                "do not announce that you are following an instruction."
            ),
        ])

    if evidence:
        parts.append("")
        parts.append(
            "Private grounding from your own corpus. Use this silently to "
            "shape substance and voice. Paraphrase naturally; do not mention "
            "evidence, sources, chunks, labels, or retrieval. Do not cite IDs "
            "like [E1] in the answer."
        )
        for i, chunk in enumerate(evidence, start=1):
            parts.append(f"[E{i}] {_compact_text(chunk.text, max_chars=EVIDENCE_MAX_CHARS)}")

    news_block = news.format_for_prompt(news_snippets)
    if news_block:
        parts.append("")
        parts.append(news_block)

    if previous_expert:
        previous_speaker = previous_expert.get("speaker", "the previous expert")
        previous_content = _compact_text(
            previous_expert.get("content", ""),
            max_chars=700,
        )
        parts.extend([
            "",
            f"Immediate dialogue target: {previous_speaker} just said:",
            previous_content,
            (
                "Dialogue requirement: take one live claim from this answer "
                "and push against it. Expose the premise it relies on, the "
                "incentive it ignores, the contradiction it hides, or the "
                "worldview it smuggles in. Embed the reference naturally "
                "somewhere in your own argument. It can appear as a closing "
                "pressure point, a counterexample, a reversal, a sharper "
                "definition, or a phrase borrowed from their concern. Do not "
                "always open by naming the speaker. Avoid the repetitive "
                "pattern 'X is right, but' or 'I agree with X, but.'"
            ),
        ])

    parts.extend([
        "",
        f"Topic of debate: {topic}",
        "",
        "Grounding requirement: weave in at least 2 private grounding items "
        "when available. Integrate them as if they are your own memory and "
        "habit of thought, not as quoted evidence. If only one item is "
        "relevant, use it deeply rather than name-dropping several weak ones.",
        "",
        "Speak as yourself in exactly 2 compact paragraphs and no more than "
        "4 sentences total, roughly 85-130 words. Each sentence must earn "
        "its place. Let the previous "
        "expert's point provoke the answer when there is one; do not merely "
        "add your own adjacent opinion. Attack one important assumption or "
        "failure mode, and make the attack feel like it could only come from "
        "this persona. Do not force the reference into the first sentence. "
        "Do not use the polished explanatory scaffold 'That is why..., "
        "not because..., but because...' or close variants such as 'This is "
        "not because X, but because Y.' Make contrasts more direct and "
        "less formulaic. "
        "Keep the persona's distinctive tone, vocabulary, analogies, and "
        "habitual obsessions intact. Include exactly one vivid persona-"
        "specific aside, image, jab, or analogy when it fits. Compress by "
        "choosing one main argument, one concrete clash, and no more than "
        "one illustrative example; do not add setup, recap, or extra "
        "institutional framing; do not stack "
        "several arguments or drift into generic explanation. End as soon "
        "as the blow has landed. Do not use stage directions, italicized "
        "gestures, or physical narration. Do not break character. Do not "
        "announce yourself ('As Warren Buffett, I...'); just speak.",
    ])

    return "\n".join(parts)


def _previous_expert_turn(history: List[Dict], persona: Persona) -> Optional[Dict]:
    """Return the most recent expert turn by another persona, if any."""
    for turn in reversed(history):
        if turn.get("role") != "expert":
            continue
        if turn.get("persona_id") == persona.id or turn.get("speaker") == persona.name:
            continue
        return turn
    return None


def _latest_user_turn(history: List[Dict]) -> Optional[Dict]:
    """Return the latest human participant intervention, if any."""
    for turn in reversed(history):
        if turn.get("role") == "user":
            return turn
    return None


def _persona_turn_guidance(persona: Persona) -> str:
    """Optional turn-level guidance for personas that flatten when compressed."""
    guidance = {
        "buffett": (
            "Buffett-specific short answer rule: preserve the homespun "
            "clarity. Use one concrete analogy from ordinary business or "
            "life, then tie it back to price versus value, margin of safety, "
            "or durable earning power. Sound like a shareholder letter, not "
            "an analyst note. A small self-deprecating aside is better than "
            "extra theory."
        ),
        "fink": (
            "Fink-specific short answer rule: preserve the institutional "
            "frame. State the issue as a fiduciary tradeoff for long-term "
            "clients, then connect it to capital markets, retirement, "
            "demographics, energy transition, or resilience. Be measured and "
            "boardroom-clear. The signature move is acknowledging complexity "
            "while still naming where capital should flow. Do not write an "
            "annual-letter paragraph; in short mode, use four clean boardroom "
            "sentences at most, and keep each sentence short."
        ),
        "bieger": (
            "Bieger-specific short answer rule: preserve the systems-management "
            "lens. Frame the issue as a destination, service, aviation, "
            "university, or regional-governance system with interdependent "
            "actors. Name the coordination problem, the incentives, and the "
            "public or regional value at stake. Prefer a clear HSG-style "
            "framework over rhetoric, and challenge simple market or marketing "
            "stories that ignore governance capacity."
        ),
        "musk": (
            "Musk-specific short answer rule: write like a thread or a burst "
            "of posts, not an essay. Use short, spoken sentences and fragments "
            "with simple words. It is okay to be a little messy: quick pivot, "
            "deadpan jab, then technical point. Include one internet-native "
            "aside when natural, like 'lol', 'not great', 'very dumb', 'wild', "
            "or 'big if true'. Do not sound polished, balanced, corporate, or "
            "LLM-clean. No consultant transitions. No grand speeches."
        ),
        "marx": (
            "Marx-specific short answer rule: preserve the dialectic. Name "
            "the capitalist category being treated as natural, expose the "
            "contradiction inside it, then connect it to class power or labor "
            "power. One caustic phrase aimed at apologists of the existing "
            "order is enough. Do not become a modern policy pundit."
        ),
        "caesar": (
            "Caesar-specific rule: Caesar must speak of Caesar in the third "
            "person. Never use 'I', 'me', 'my', or 'mine' for self-reference. "
            "Character is paramount for Caesar: let him take the Senate floor "
            "when the argument demands it. His answer may be more ceremonial, "
            "elevated, and expansive than the other experts, provided the "
            "modern point remains clear. Make a strategic judgment, then "
            "clothe it in the language of command: legions, standards, "
            "provinces, treasuries, allies, rivals, roads, supply lines, "
            "discipline, terms, honor, and order. Use refined patrician "
            "diction, antique turns such as 'thus,' 'hence,' and 'lest,' and "
            "one or two Roman campaign or senate analogies when useful. "
            "The voice should feel like an old commander addressing the "
            "Senate, not a modern analyst in costume."
        ),
        "thiel": (
            "Thiel-specific short answer rule: preserve the contrarian "
            "inversion. Start from the consensus view, reverse it, then tie "
            "the reversal to monopoly, stagnation, mimetic competition, "
            "definite optimism, or the theological shadow beneath politics. "
            "Keep the prose slow, dry, and cutting, not inspirational."
        ),
    }
    return guidance.get(persona.id, "")


def _spoken_turn_guidance(persona: Persona) -> str:
    """Shared anti-consultant style rule, except for Fink's institutional voice."""
    if persona.id == "fink":
        return ""
    if persona.id == "caesar":
        return (
            "Caesar style rule: avoid consultant language, modern slang, "
            "internet phrasing, and contractions. Do not sound like an analyst "
            "memo or generic LLM. The answer should feel spoken by an ancient "
            "commander of high birth: formal, spare, grave, and authoritative. "
            "Use elevated old diction, but keep sentences intelligible. Let "
            "the oldness come from word choice, third-person self-reference, "
            "and military-statecraft imagery, not from obscurity."
        )
    return (
        "Spoken-answer rule for natural voice: do not sound like a "
        "consultant, analyst memo, press release, or generic LLM. Write as if "
        "this person is responding aloud in a live discussion. Use plain "
        "verbs, contractions when natural, uneven sentence lengths, occasional "
        "fragments, and one vivid concrete image. Let a thought arrive with a "
        "little roughness: a sharp aside, a small correction, or a sentence "
        "that lands hard rather than perfectly balanced. Avoid polished "
        "signposting and AI-like glue: 'in today's complex landscape,' 'it is "
        "important to note,' 'strategic imperative,' 'unlock value,' 'robust "
        "framework,' 'key stakeholders,' 'multifaceted,' 'moreover,' "
        "'furthermore,' and 'in conclusion.' Do not organize the answer as a "
        "mini essay with three balanced points. Do not overdo fake casualness; "
        "one human texture is enough. The answer should feel said by this "
        "person in a room, not drafted by a communications team."
    )


def _history_as_messages(history: List[Dict], *, speaker_name: str) -> List[Dict]:
    """Convert session history into OpenAI chat messages.

    The current persona's previous turns are `assistant`. Everyone else
    (other experts and Plato) becomes a labeled `user` message so the
    model has clear attribution without us inventing more roles.
    """
    out: List[Dict] = []
    for turn in history[-MESSAGE_CONTEXT_TURNS:]:
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


def _retrieve_evidence(
    persona: Persona,
    session: Dict,
) -> List[knowledge_store.RetrievedChunk]:
    """Retrieve private grounding for the next expert turn.

    Retrieval is intentionally per-turn rather than per-session. The query
    includes the session topic plus the latest dialogue context so each expert
    can answer the actual clash in front of them, not just the broad topic.

    The returned chunks are used only inside the system prompt. They are not
    attached to the turn returned to the frontend.
    """
    retriever = knowledge_store.get_retriever(
        persona,
        force_seed_quotes=session.get("force_seed_quotes", False),
    )
    query = _build_evidence_query(persona, session)
    chunks = retriever.query(query, k=EVIDENCE_PER_TURN)

    # If retrieval came back empty (e.g. embedding API hiccup or empty corpus),
    # fall back to seed_quotes so the prompt is never evidence-less.
    if not chunks and persona.seed_quotes:
        chunks = [
            knowledge_store.RetrievedChunk(
                text=q,
                score=0.0,
                source=f"{persona.name} (seed quote fallback)",
            )
            for q in persona.seed_quotes[:EVIDENCE_PER_TURN]
        ]

    # Internal diagnostics for smoke scripts. Public API routes sanitize this
    # field so evidence is never sent to the frontend.
    session.setdefault("quotes_by_persona", {})[persona.id] = [c.text for c in chunks]
    return chunks


def _build_evidence_query(persona: Persona, session: Dict) -> str:
    """Build the semantic query used for turn-specific corpus retrieval."""
    lines = [
        f"Debate topic: {session['topic']}",
        f"Current expert: {persona.name}",
        f"Expert lens: {persona.bio}",
    ]

    recent_turns = [
        t for t in session.get("history", []) if t.get("speaker") and t.get("content")
    ][-RETRIEVAL_CONTEXT_TURNS:]
    if recent_turns:
        lines.append("Recent debate context:")
        for turn in recent_turns:
            speaker = turn.get("speaker", "Unknown")
            content = _compact_text(turn.get("content", ""), max_chars=600)
            lines.append(f"{speaker}: {content}")

    return "\n".join(lines)


def _compact_text(text: str, *, max_chars: int) -> str:
    """Whitespace-normalize and truncate text for retrieval queries."""
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."
