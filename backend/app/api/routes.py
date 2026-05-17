"""API routes for discourse endpoints.

Async-vs-sync routing convention (READ BEFORE EDITING):

`llm.generate` calls the *synchronous* `openai.OpenAI` client. A
synchronous SDK call inside an `async def` route blocks the asyncio
event loop for the entire LLM round-trip (5-15 seconds), which means
*every* other request to this worker — even a static GET /personas —
queues behind it. On a single-worker uvicorn deployment (see
fly.toml + Dockerfile, both deliberately single-worker because
sessions live in process memory), this manifests as "two devices
can't use the app at once": device B can't load any page while
device A is mid-turn.

FastAPI runs `def` (sync) route handlers in a starlette threadpool
(default 40 threads) *off* the event loop. That means the blocking
LLM call no longer monopolises the worker; other requests keep
flowing while the LLM is thinking. With the default threadpool size,
~40 concurrent LLM calls can be in flight before further requests
queue — well above any demo-scale audience.

The rule:
- Routes that call `llm.generate` (directly or transitively via
  `discourse.next_turn` / `aporia.Aporia.analyze`) are `def`, not
  `async def`.
- Trivial routes that just dict-lookup or return static data stay
  `async def`. They're cheap and either path is fine.

Do NOT "fix" these to `async def` without first converting
`llm.generate` to use `openai.AsyncOpenAI` and awaiting it. If you
do, the event-loop-blocking bug returns silently.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid

from app.core.personas import PERSONAS, all_personas

router = APIRouter()

# In-memory storage for discourse sessions. Lives for the lifetime of
# this worker process; wiped on every restart/deploy (accepted trade-off
# for the capstone demo, see fly.toml comments). Plain dict is safe
# enough for concurrent access because sessions are keyed by UUID so
# different requests touch different keys; within a single session,
# the frontend's "thinking…" state prevents the user from double-tapping
# Continue, so we don't bother locking the per-session history.
discourse_sessions: Dict[str, dict] = {}


# ==================
# Request Models
# ==================

class StartDiscourseRequest(BaseModel):
    topic: str
    persona_ids: List[str]
    user_name: Optional[str] = None
    max_turns: int = 6
    socratic_mode: bool = True


class AddResponseRequest(BaseModel):
    content: str


# ==================
# Response Models
# ==================

class PersonaResponse(BaseModel):
    id: str
    name: str
    title: str
    icon: str
    color: str
    bio: str
    rag_tier: str


# ==================
# Personas
# ==================

def _persona_to_response(p) -> PersonaResponse:
    return PersonaResponse(
        id=p.id,
        name=p.name,
        title=p.title,
        icon=p.icon,
        color=p.color,
        bio=p.bio,
        rag_tier=p.rag_tier,
    )


def _public_turn(turn: Dict) -> Dict:
    """Return only fields the frontend should see for a discourse turn."""
    allowed = {"role", "type", "speaker", "persona_id", "content", "done"}
    return {k: v for k, v in turn.items() if k in allowed}


def _public_session(session: Dict) -> Dict:
    """Return a discourse session without private retrieval diagnostics."""
    return {
        "topic": session.get("topic"),
        "persona_ids": session.get("persona_ids", []),
        "user_name": session.get("user_name"),
        "max_turns": session.get("max_turns"),
        "history": [_public_turn(t) for t in session.get("history", [])],
        "status": session.get("status", "active"),
    }


def _normalize_user_name(name: Optional[str]) -> str:
    """Keep the participant name short and single-line for prompts/UI."""
    compact = " ".join((name or "").split())
    if not compact:
        return "the user"
    return compact[:60]


def _normalize_user_input(content: str) -> str:
    """Trim empty/overlong interventions before appending to history."""
    compact = content.strip()
    if not compact:
        raise HTTPException(status_code=400, detail="Input cannot be empty.")
    if len(compact) > 1200:
        raise HTTPException(
            status_code=400,
            detail="Input is too long. Keep it under 1200 characters.",
        )
    return compact


@router.get("/personas")
async def list_personas():
    """Return the catalog of expert personas available for debates."""
    return {"personas": [_persona_to_response(p) for p in all_personas()]}


@router.get("/personas/{persona_id}")
async def get_persona_detail(persona_id: str):
    """Return one persona's full public-facing details."""
    if persona_id not in PERSONAS:
        raise HTTPException(status_code=404, detail=f"Unknown persona: {persona_id}")
    return _persona_to_response(PERSONAS[persona_id])


# ==================
# Discourse
# ==================


@router.post("/discourse/start")
async def start_discourse(request: StartDiscourseRequest):
    """Start a new discourse session.

    Validates persona_ids up-front so typos surface immediately rather
    than on the first /next call.
    """
    unknown = [pid for pid in request.persona_ids if pid not in PERSONAS]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown persona_ids: {unknown}. "
                   f"Available: {sorted(PERSONAS.keys())}",
        )
    if len(request.persona_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="Need at least 2 personas for a debate.",
        )

    session_id = str(uuid.uuid4())
    user_name = _normalize_user_name(request.user_name)
    discourse_sessions[session_id] = {
        "topic": request.topic,
        "persona_ids": request.persona_ids,
        "user_name": user_name,
        "max_turns": request.max_turns,
        "history": [],
        "status": "active",
    }
    return {
        "session_id": session_id,
        "topic": request.topic,
        "persona_ids": request.persona_ids,
        "user_name": user_name,
        "max_turns": request.max_turns,
        "status": "active",
    }


@router.post("/discourse/{session_id}/input")
async def add_user_input(session_id: str, request: AddResponseRequest):
    """Append the human participant's intervention to the discourse."""
    if session_id not in discourse_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = discourse_sessions[session_id]
    if session.get("status") == "done":
        raise HTTPException(status_code=400, detail="Dialogue is already concluded.")
    history = session.setdefault("history", [])
    last = history[-1] if history else None
    if not last or last.get("role") != "expert":
        raise HTTPException(
            status_code=400,
            detail="Input is available after an expert turn.",
        )
    expert_turns_so_far = sum(1 for t in history if t.get("role") == "expert")
    if expert_turns_so_far >= session.get("max_turns", 6):
        raise HTTPException(
            status_code=400,
            detail="The dialogue is ready to conclude.",
        )

    turn = {
        "role": "user",
        "type": "user_input",
        "speaker": session.get("user_name") or "the user",
        "content": _normalize_user_input(request.content),
    }
    history.append(turn)
    session["status"] = "active"
    return _public_turn({**turn, "done": False})


@router.post("/discourse/{session_id}/next")
def next_turn(session_id: str):
    """Advance the discourse by one turn (Plato or expert).

    Sync handler on purpose — see the async-vs-sync note at the top of
    this file. FastAPI runs this in starlette's threadpool, so the
    blocking `llm.generate` call inside `discourse.next_turn` no longer
    holds the event loop hostage.

    Idempotent only in the sense that calling /next on a `done` session
    returns the existing closing turn rather than generating a new one.
    """
    if session_id not in discourse_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = discourse_sessions[session_id]

    if session.get("status") == "done":
        # Return the last turn so the frontend can detect end-of-debate
        # gracefully on a stray extra call.
        history = session.get("history", [])
        last = history[-1] if history else {"content": "", "role": "plato"}
        return _public_turn({**last, "done": True})

    # Lazy import keeps the routes module importable even when openai is
    # not installed (e.g. in CI without the API key).
    from app.agents import discourse

    try:
        return _public_turn(discourse.next_turn(session))
    except RuntimeError as e:
        # Missing API key surfaces here.
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/discourse/{session_id}")
async def get_discourse(session_id: str):
    """Get the full discourse history."""
    if session_id not in discourse_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return _public_session(discourse_sessions[session_id])


@router.delete("/discourse/{session_id}")
async def end_discourse(session_id: str):
    """End and clean up a discourse session."""
    if session_id not in discourse_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del discourse_sessions[session_id]
    return {"message": "Session ended successfully"}


@router.post("/discourse/{session_id}/aporia")
def trigger_aporia(session_id: str):
    """
    Trigger Aporia analysis on the discourse.

    Sync handler on purpose — see the async-vs-sync note at the top of
    this file. Aporia makes N+1 blocking LLM calls per click (one per
    expert plus a synthesis pass), and any one of them would block the
    event loop if this were `async def`.

    When user clicks the Aporia button, this analyzes the debate
    to expose assumptions, contradictions, and blind spots.
    """
    if session_id not in discourse_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = discourse_sessions[session_id]
    turns = session.get("history", [])
    
    if not turns:
        return {
            "role": "plato",
            "type": "aporia",
            "content": "Aporia Analysis\n\nThe dialogue has not yet begun. Start a discourse first.",
            "findings": [],
            "guidance": "Begin the dialogue to gather material for analysis."
        }
    
    # Import and call Aporia system
    from app.agents.aporia import Aporia
    result = Aporia.analyze(turns, mode="simple")
    
    return result


@router.get("/aporia/button")
async def get_aporia_button():
    """Get the Aporia button configuration for the UI."""
    from app.agents.aporia import Aporia
    return Aporia.get_button_info()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "sessions": len(discourse_sessions)
    }
