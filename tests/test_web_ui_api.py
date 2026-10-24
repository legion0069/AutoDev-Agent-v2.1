"""Focused contract tests for the Version 5.1 web API."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.services.project_service import ProjectService


def _request() -> dict[str, object]:
    return {
        "project_name": "Student Productivity App",
        "description": "Build a productivity platform",
        "tech_stack": ["React", "FastAPI", "MongoDB"],
        "days": 3,
        "working_hours": 3,
        "daily_commit_target": 4,
        "repository": "https://github.com/user/project",
        "mode": "autonomous",
    }


def test_health_and_project_creation_return_existing_planner_roadmap(tmp_path):
    app = create_app(ProjectService(tmp_path))
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/health").json()["status"] == "ok"

        response = client.post("/project/create", json=_request())

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["roadmap"]) == 3
    assert payload["daily_plan"]["day"] == 1
    assert payload["progress"]["status"] == "planned"
    assert payload["execution_metadata"] == {
        "project_id": payload["project"]["project_id"],
        "mode": "autonomous",
        "working_hours": 3,
        "daily_commit_target": 4,
    }
    assert payload["project"]["plan"]["daily_commit_plan"][0]["expected_commits"] == "4"
    assert payload["project"]["plan"]["phases"] == payload["roadmap"]


def test_project_controls_roadmap_history_and_dashboard(tmp_path):
    def run_day(_):
        time.sleep(0.1)
        return {
            "success": True,
            "next_day": 2,
            "commits_created": ["abc123"],
            "average_test_pass_rate": 1.0,
        }

    service = ProjectService(tmp_path, execution_runner=run_day)
    app = create_app(service)
    with TestClient(app) as client:
        created = client.post("/project/create", json=_request()).json()
        project_id = created["project"]["project_id"]

        started = client.post("/project/start", json={"project_id": project_id})
        assert started.status_code == 200
        deadline = time.monotonic() + 5
        while service.get_status(project_id)["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.01)

        status = client.get("/project/status", params={"project_id": project_id}).json()
        assert status["status"] == "waiting"
        assert status["completed_days"] == 1
        assert status["current_day"] == 2
        assert status["commits_today"] == 1
        assert status["elapsed_seconds"] > 0

        roadmap = client.get("/project/roadmap", params={"project_id": project_id}).json()
        assert roadmap["days"][0]["status"] == "completed"
        assert roadmap["days"][0]["tests"] == ["Validation pass rate: 100.0%"]
        assert client.get("/project/day/2", params={"project_id": project_id}).json()["day"] == 2
        assert client.get("/project/history").json()[0]["project_id"] == project_id
        assert client.get("/dashboard").json()["current_project"]["project_id"] == project_id
        assert client.get("/metrics").json()["project_count"] == 1
        assert client.get("/settings").status_code == 200
        assert client.get("/benchmarks").status_code == 200
        assert client.get("/github/status").status_code == 200
        assert client.get("/project/logs").json()


def test_project_request_validation_and_unknown_day(tmp_path):
    app = create_app(ProjectService(tmp_path))
    with TestClient(app) as client:
        invalid = _request()
        invalid["repository"] = "https://example.com/not-github"
        assert client.post("/project/create", json=invalid).status_code == 422

        created = client.post("/project/create", json=_request()).json()
        project_id = created["project"]["project_id"]
        assert client.get("/project/day/4", params={"project_id": project_id}).status_code == 404


def test_pause_resume_and_stop_controls_are_applied_between_daily_runs(tmp_path):
    def run_day(project):
        time.sleep(0.05)
        return {"success": True, "next_day": project["current_day"] + 1}

    service = ProjectService(tmp_path, execution_runner=run_day)
    app = create_app(service)
    with TestClient(app) as client:
        request = _request()
        request["days"] = 3
        created = client.post("/project/create", json=request).json()
        project_id = created["project"]["project_id"]
        assert client.post("/project/start", json={"project_id": project_id}).status_code == 200
        assert client.post("/project/pause", json={"project_id": project_id}).status_code == 200

        deadline = time.monotonic() + 5
        while service.get_status(project_id)["status"] != "paused" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service.get_status(project_id)["status"] == "paused"

        assert client.post("/project/resume", json={"project_id": project_id}).status_code == 200
        deadline = time.monotonic() + 5
        while service.get_status(project_id)["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service.get_status(project_id)["current_day"] == 3
        assert client.post("/project/stop", json={"project_id": project_id}).json()["project"]["status"] == "stopped"


def test_websocket_reconnect_streams_persisted_and_new_logs(tmp_path):
    service = ProjectService(tmp_path)
    app = create_app(service)
    with TestClient(app) as client:
        client.post("/project/create", json=_request())
        with client.websocket_connect("/ws/logs?after=0") as websocket:
            first = websocket.receive_json()
            assert first["event"] == "planning.completed"
            service.publish_log("Building code...", event="execution.progress", day=1)
            second = websocket.receive_json()
            assert second["message"] == "Building code..."
            assert second["event_id"] > first["event_id"]
