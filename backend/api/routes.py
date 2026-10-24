"""REST endpoints for the AutoDev dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from backend.schemas.project import (
    ApiMessage,
    ProjectActionRequest,
    ProjectCreateRequest,
    ProjectScheduleRequest,
    ProjectSummary,
)

router = APIRouter()


def _service(request: Request):
    return request.app.state.project_service


@router.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "AutoDev Web API",
        "version": "6.0",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "6.0"}


@router.post("/project/create")
def create_project(payload: ProjectCreateRequest, request: Request) -> dict[str, Any]:
    project = _service(request).create_project(payload)
    status = _service(request).get_status(project["project_id"])
    return {
        "project": project,
        "roadmap": project["plan"]["phases"],
        "daily_plan": project["plan"]["phases"][0],
        "progress": status,
        "execution_metadata": {
            "project_id": project["project_id"],
            "mode": project["mode"],
            "working_hours": project["working_hours"],
            "daily_commit_target": project["daily_commit_target"],
        },
    }


def _action(
    request: Request,
    payload: ProjectActionRequest | None,
    method: str,
) -> ApiMessage:
    service = _service(request)
    try:
        status = getattr(service, method)(payload.project_id if payload else None)
        return ApiMessage(message=f"Project {method} request accepted.", project=ProjectSummary(**status))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/project/start", response_model=ApiMessage)
def start_project(request: Request, payload: ProjectActionRequest | None = None) -> ApiMessage:
    return _action(request, payload, "start")


@router.post("/project/pause", response_model=ApiMessage)
def pause_project(request: Request, payload: ProjectActionRequest | None = None) -> ApiMessage:
    return _action(request, payload, "pause")


@router.post("/project/resume", response_model=ApiMessage)
def resume_project(request: Request, payload: ProjectActionRequest | None = None) -> ApiMessage:
    return _action(request, payload, "resume")


@router.post("/project/stop", response_model=ApiMessage)
def stop_project(request: Request, payload: ProjectActionRequest | None = None) -> ApiMessage:
    return _action(request, payload, "stop")


@router.put("/project/schedule")
def update_project_schedule(
    request: Request,
    payload: ProjectScheduleRequest,
    project_id: str | None = None,
) -> dict[str, Any]:
    try:
        return _service(request).update_schedule(payload, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/project/run-day")
def run_project_day(request: Request, payload: ProjectActionRequest | None = None) -> dict[str, Any]:
    return _execution_action(request, payload, "run_day")


@router.post("/project/run-milestone")
def run_project_milestone(request: Request, payload: ProjectActionRequest | None = None) -> dict[str, Any]:
    return _execution_action(request, payload, "run_milestone")


@router.post("/project/create-commit")
def create_project_commit(request: Request, payload: ProjectActionRequest | None = None) -> dict[str, Any]:
    return _execution_action(request, payload, "create_commit")


@router.post("/project/push")
def push_project(request: Request, payload: ProjectActionRequest | None = None) -> dict[str, Any]:
    return _execution_action(request, payload, "push")


@router.post("/project/review")
def review_project(request: Request, payload: ProjectActionRequest | None = None) -> dict[str, Any]:
    return _execution_action(request, payload, "review")


def _execution_action(
    request: Request,
    payload: ProjectActionRequest | None,
    method: str,
) -> dict[str, Any]:
    try:
        return getattr(_service(request), method)(payload.project_id if payload else None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/project/status")
def project_status(
    request: Request,
    project_id: str | None = None,
) -> dict[str, Any]:
    try:
        return _service(request).get_status(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/project/current-day")
def current_day(request: Request, project_id: str | None = None) -> dict[str, Any]:
    try:
        state = _service(request).get_execution_state(project_id)
        state["roadmap_day"] = _service(request).get_day(state["current_day"], project_id)
        return state
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/project/current-milestone")
def current_milestone(request: Request, project_id: str | None = None) -> dict[str, Any]:
    try:
        state = _service(request).get_execution_state(project_id)
        current = next(
            (item for item in state.get("milestones", []) if item["milestone_id"] == state["current_milestone"]),
            None,
        )
        return {"day": state["current_day"], "milestone": current, "execution": state}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/project/commits")
def project_commits(request: Request, project_id: str | None = None) -> list[dict[str, Any]]:
    try:
        return _service(request).get_commits(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/project/report")
def project_report(
    request: Request,
    project_id: str | None = None,
    day: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    try:
        return _service(request).get_report(project_id, day)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/project/logs")
def project_logs(
    request: Request,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=2000),
) -> list[dict[str, Any]]:
    return _service(request).get_logs(after=after, limit=limit)


@router.get("/project/roadmap")
def project_roadmap(request: Request, project_id: str | None = None) -> dict[str, Any]:
    try:
        return _service(request).get_roadmap(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/project/day/{day}")
def project_day(day: int, request: Request, project_id: str | None = None) -> dict[str, Any]:
    try:
        return _service(request).get_day(day, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/project/history")
def project_history(request: Request) -> list[dict[str, Any]]:
    return _service(request).get_history()


@router.get("/github/status")
def github_status(request: Request) -> dict[str, Any]:
    return _service(request).github_status()


@router.get("/benchmarks")
def benchmarks(request: Request) -> dict[str, Any]:
    return _service(request).benchmarks()


@router.get("/dashboard")
def dashboard(request: Request) -> dict[str, Any]:
    return _service(request).dashboard()


@router.get("/metrics")
def metrics(request: Request) -> dict[str, Any]:
    return _service(request).metrics()


@router.get("/settings")
def settings(request: Request) -> dict[str, Any]:
    return _service(request).settings()
