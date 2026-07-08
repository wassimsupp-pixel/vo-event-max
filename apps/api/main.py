"""
main.py — FastAPI application entry point for VO Event Max API.

Configures:
  - CORS middleware
  - All routers under /api prefix
  - Health check endpoint
  - Global exception handler (no stack traces in production)
"""

from __future__ import annotations

import logging
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from routers import events, files, participants, consolidation, exports, flights, hotels, transfers, activities, reports, global_participants

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title=config.APP_TITLE,
    description=config.APP_DESCRIPTION,
    version=config.APP_VERSION,
    # Disable the auto-generated docs in production to reduce attack surface
    docs_url="/docs" if os.getenv("ENVIRONMENT", "development") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENVIRONMENT", "development") != "production" else None,
)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unhandled exceptions.

    In production: returns a generic 500 with no stack trace.
    In development: includes the traceback for easier debugging.
    """
    is_production = os.getenv("ENVIRONMENT", "development") == "production"

    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )

    body: dict = {
        "detail": "An unexpected internal error occurred. Please try again or contact support.",
        "path": request.url.path,
    }

    if not is_production:
        body["debug_traceback"] = traceback.format_exc()

    return JSONResponse(status_code=500, content=body)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
API_PREFIX = "/api"

app.include_router(events.router,        prefix=API_PREFIX, tags=["Events"])
app.include_router(files.router,         prefix=API_PREFIX, tags=["Files"])
app.include_router(participants.router,  prefix=API_PREFIX, tags=["Participants"])
app.include_router(consolidation.router, prefix=API_PREFIX, tags=["Consolidation"])
app.include_router(exports.router,       prefix=API_PREFIX, tags=["Exports"])
app.include_router(flights.router,       prefix=API_PREFIX, tags=["Flights"])
app.include_router(hotels.router,        prefix=API_PREFIX, tags=["Hotels"])
app.include_router(transfers.router,     prefix=API_PREFIX, tags=["Transfers"])
app.include_router(activities.router,    prefix=API_PREFIX, tags=["Activities"])
app.include_router(reports.router,       prefix=API_PREFIX, tags=["Reports"])
app.include_router(global_participants.router, prefix=API_PREFIX, tags=["Global Participants"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """
    Liveness probe endpoint.

    Returns a simple status object used by Railway health checks and
    uptime monitors. No authentication required.
    """
    return {"status": "ok", "version": config.APP_VERSION}
