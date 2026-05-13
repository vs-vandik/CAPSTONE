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

# Configure CORS. Stable origins (localhost, production Vercel domain)
# come from settings.CORS_ORIGINS as a comma-separated list. Ephemeral
# Vercel preview deployment URLs (one new origin per push) are matched
# by settings.CORS_ORIGIN_REGEX so we don't rotate the Fly secret on
# every deploy. Both can be set independently; either alone is fine.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
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