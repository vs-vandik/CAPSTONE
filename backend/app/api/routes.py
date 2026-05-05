"""API routes for discourse endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid

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
    style: str
    icon: str
    color: str


# ==================
# Placeholder Routes
# ==================

@router.get("/personas")
async def list_personas():
    """Get all available expert personas."""
    return {"personas": [], "message": "Personas not yet implemented"}


@router.get("/personas/{persona_id}")
async def get_persona_detail(persona_id: str):
    """Get details of a specific persona."""
    raise HTTPException(status_code=404, detail="Personas not yet implemented")


@router.post("/discourse/start")
async def start_discourse(request: StartDiscourseRequest):
    """Start a new discourse session."""
    session_id = str(uuid.uuid4())
    discourse_sessions[session_id] = {
        "topic": request.topic,
        "persona_ids": request.persona_ids,
        "max_turns": request.max_turns,
        "history": []
    }
    return {
        "session_id": session_id,
        "topic": request.topic,
        "persona_ids": request.persona_ids
    }


@router.post("/discourse/{session_id}/next")
async def next_turn(session_id: str, request: AddResponseRequest):
    """Get the next turn in the discourse."""
    if session_id not in discourse_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Discourse engine not yet implemented"}


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