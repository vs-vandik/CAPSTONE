"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes

# Create FastAPI app
app = FastAPI(
    title="AI Investment Discourse API",
    description="Socratic discourse between AI agents for asset managers",
    version="0.1.0"
)

# Configure CORS for Vue.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(routes.router, prefix="/api/v1", tags=["discourse"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "AI Investment Discourse API",
        "version": "0.1.0"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}