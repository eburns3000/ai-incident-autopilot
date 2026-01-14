"""Main FastAPI application for Incident Autopilot."""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.routers import webhook_router, health_router, metrics_router
from app.db import get_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    settings = get_settings()
    logger.info(f"Starting Incident Autopilot v{__version__}")
    logger.info(f"DRY_RUN mode: {settings.dry_run}")
    logger.info(f"LLM Provider: {settings.llm_provider}")

    # Initialize database
    get_database()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down Incident Autopilot")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Incident Autopilot",
        description="IT Ops automation for Jira incident triage",
        version=__version__,
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(webhook_router)

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "Incident Autopilot",
            "version": __version__,
            "status": "running",
            "dry_run": settings.dry_run,
        }

    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
