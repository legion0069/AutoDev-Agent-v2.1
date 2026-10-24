"""FastAPI application entry point for AutoDev Version 5.2."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.services.project_service import ProjectService
from backend.websocket.logs import router as websocket_router


def create_app(project_service: ProjectService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.project_service.resume_interrupted()
        yield

    app = FastAPI(
        title="AutoDev API",
        description="REST and WebSocket API for the AutoDev Version 5.2 dashboard.",
        version="5.2.0",
        lifespan=lifespan,
    )
    app.state.project_service = project_service or ProjectService()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)
    app.include_router(websocket_router)
    return app


app = create_app()
