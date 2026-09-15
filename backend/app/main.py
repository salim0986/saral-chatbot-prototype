"""
FastAPI application entrypoint.
Phase 0: Health endpoint only. All other routes are stubs registered here.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.routers import ingest, generate, refine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    await init_db()
    yield


app = FastAPI(
    title="SARAL Chatbot API",
    description="Audience-Adaptive Script & Bullet Generator for SARAL - AI PMU, IIIT Hyderabad",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(ingest.router, prefix="/api")
app.include_router(generate.router, prefix="/api")
app.include_router(refine.router, prefix="/api")


@app.get("/api/health", tags=["System"])
async def health_check():
    """Liveness probe. Returns service name and version."""
    return {
        "status": "ok",
        "service": "saral-chatbot",
        "version": settings.app_version,
    }
