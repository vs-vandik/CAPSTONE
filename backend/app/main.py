"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes
from app.core.config import settings

# Create FastAPI app
app = FastAPI(
    title="AI Investment Discourse API",
    description="Socratic discourse between AI agents for asset managers",
    version="0.1.0"
)

# Configure CORS. Origins come from settings.CORS_ORIGINS (comma-separated
# in .env), so deploys can change allowed origins without a code change.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
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