"""API routes for discourse endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid

from app.core.personas import PERSONAS, all_personas

router = APIRouter()

# In-memory storage for discourse sessions
discourse_sessions: Dict[str, dict] = {}


# ==================
# Request Models
# ==================

class StartDiscourseRequest(BaseModel):
    topic: str
    persona_ids: List[str]
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
    discourse_sessions[session_id] = {
        "topic": request.topic,
        "persona_ids": request.persona_ids,
        "max_turns": request.max_turns,
        "history": [],
        "status": "active",
    }
    return {
        "session_id": session_id,
        "topic": request.topic,
        "persona_ids": request.persona_ids,
        "max_turns": request.max_turns,
        "status": "active",
    }


@router.post("/discourse/{session_id}/next")
async def next_turn(session_id: str):
    """Advance the discourse by one turn (Plato or expert).

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
        return {**last, "done": True}

    # Lazy import keeps the routes module importable even when openai is
    # not installed (e.g. in CI without the API key).
    from app.agents import discourse

    try:
        return discourse.next_turn(session)
    except RuntimeError as e:
        # Missing API key surfaces here.
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/discourse/{session_id}")
async def get_discourse(session_id: str):
    """Get the full discourse history."""
    if session_id not in discourse_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return discourse_sessions[session_id]


@router.delete("/discourse/{session_id}")
async def end_discourse(session_id: str):
    """End and clean up a discourse session."""
    if session_id not in discourse_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del discourse_sessions[session_id]
    return {"message": "Session ended successfully"}


@router.post("/discourse/{session_id}/aporia")
async def trigger_aporia(session_id: str):
    """
    Trigger Aporia analysis on the discourse.
    
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