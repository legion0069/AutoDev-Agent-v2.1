"""Focused tests for V5.2 milestone recovery and commit safety."""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from agents.git_agent import GitAgent, GitOperationResult
from backend.api.main import create_app
from backend.schemas.project import ProjectCreateRequest
from backend.services.project_service import ProjectService
from core.commit_scheduler import CommitScheduler
from core.day_execution_engine import DayExecutionEngine
from core.github_execution import GitHubExecution
from fastapi.testclient import TestClient


def test_day_execution_resumes_at_first_unfinished_milestone(tmp_path):
    engine = DayExecutionEngine(tmp_path / "execution" / "day_1.json")
    phase = {"phase_name": "Build", "tasks": ["Models", "API"]}
    completed: list[str] = []

    def execute(milestone):
        completed.append(milestone.title)
        return {"success": True}

    result = engine.run_day(
        1,
        phase,
        execute,
        commit_target=2,
        should_stop=lambda: len(completed) == 1,
    )
    assert result["status"] == "paused"
    assert completed == ["Models"]

    resumed = DayExecutionEngine(tmp_path / "execution" / "day_1.json")
    result = resumed.run_day(1, phase, execute, commit_target=2)
    assert result["status"] == "completed"
    assert completed == ["Models", "API"]
    assert result["completed_milestones"] == [
        "day-1-milestone-1",
        "day-1-milestone-2",
    ]


def test_day_execution_retries_failed_milestone_and_persists_recovery(tmp_path):
    state_path = tmp_path / "day.json"
    engine = DayExecutionEngine(state_path)
    phase = {"phase_name": "Build", "tasks": ["API"]}

    def fail_once(_):
        raise RuntimeError("temporary validation failure")

    try:
        engine.run_day(1, phase, fail_once, commit_target=1)
    except RuntimeError as exc:
        assert str(exc) == "temporary validation failure"
    else:
        raise AssertionError("The first milestone attempt should fail.")

    engine = DayExecutionEngine(state_path)
    assert engine.state.retry_queue == ["day-1-milestone-1"]
    result = engine.run_day(
        1,
        phase,
        lambda _: {"success": True},
        commit_target=1,
    )
    assert result["status"] == "completed"
    assert result["retry_queue"] == []
    assert engine.state.failed_tasks[0]["resolved"] is True


def test_commit_scheduler_skips_whitespace_only_and_commits_meaningful_changes(
    tmp_path,
):
    agent = GitAgent(project_root=tmp_path, auto_init=True)
    source = tmp_path / "app.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    initial = agent.commit(message="Initial source")
    assert initial.success

    source.write_text("VALUE = 1   \n", encoding="utf-8")
    scheduler = CommitScheduler(agent)
    assert scheduler.create_commit(1, "Whitespace update") is None

    source.write_text("VALUE = 2\n", encoding="utf-8")
    commit = scheduler.create_commit(1, "Meaningful update")
    assert commit is not None
    assert commit.commit_message == "Day 1 - Meaningful update"
    assert commit.files_committed == ["app.py"]


def test_github_execution_verifies_remote_head_after_push():
    class FakeGitAgent:
        def __init__(self):
            self.pushes = 0

        def get_current_branch(self):
            return "main"

        def push(self, **kwargs):
            self.pushes += 1
            return GitOperationResult(
                success=True, command="git push", message="Pushed successfully."
            )

        def _run_git_command(self, args, **kwargs):
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="abc123\trefs/heads/main\n",
                stderr="",
            )

    git_agent = FakeGitAgent()
    result = GitHubExecution(git_agent, retry_delay=0).push_and_verify("abc123")
    assert result["success"] is True
    assert result["verified"] is True
    assert git_agent.pushes == 1


def test_github_execution_rebases_conflict_and_returns_rewritten_commit_hash():
    class FakeGitAgent:
        def __init__(self):
            self.pushes = 0

        def get_current_branch(self):
            return "main"

        def get_latest_commit_hash(self):
            return "rebased123"

        def push(self, **kwargs):
            self.pushes += 1
            if self.pushes == 1:
                return GitOperationResult(
                    success=False,
                    command="git push",
                    message="Push rejected",
                    stderr="non-fast-forward",
                )
            return GitOperationResult(success=True, command="git push")

        def _run_git_command(self, args, **kwargs):
            output = "rebased123\trefs/heads/main\n" if args[0] == "ls-remote" else ""
            return subprocess.CompletedProcess(args, 0, output, "")

    git_agent = FakeGitAgent()
    result = GitHubExecution(git_agent, retry_delay=0).push_and_verify("old123")
    assert result["verified"] is True
    assert result["commit_hash"] == "rebased123"
    assert git_agent.pushes == 2


def test_v52_execution_routes_preserve_async_day_lifecycle(tmp_path):
    def run_day(project):
        return {"success": True, "next_day": project["current_day"] + 1}

    service = ProjectService(tmp_path, execution_runner=run_day)
    with TestClient(create_app(service)) as client:
        request = {
            "project_name": "Execution API",
            "description": "Test the V5.2 endpoints",
            "tech_stack": ["Python"],
            "days": 2,
        }
        project_id = client.post("/project/create", json=request).json()["project"][
            "project_id"
        ]

        assert (
            client.get(
                "/project/current-day", params={"project_id": project_id}
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/project/current-milestone", params={"project_id": project_id}
            ).status_code
            == 200
        )
        assert (
            client.get("/project/commits", params={"project_id": project_id}).json()
            == []
        )
        assert (
            client.get("/project/report", params={"project_id": project_id}).status_code
            == 200
        )
        assert (
            client.post("/project/review", json={"project_id": project_id}).status_code
            == 200
        )
        assert (
            client.post("/project/push", json={"project_id": project_id}).status_code
            == 409
        )

        assert (
            client.post("/project/run-day", json={"project_id": project_id}).status_code
            == 200
        )
        deadline = time.monotonic() + 5
        while (
            service.get_status(project_id)["status"] == "running"
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert service.get_status(project_id)["current_day"] == 2

        assert (
            client.post(
                "/project/run-milestone", json={"project_id": project_id}
            ).status_code
            == 200
        )
        deadline = time.monotonic() + 5
        while (
            service.get_status(project_id)["status"] == "running"
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert service.get_status(project_id)["status"] == "completed"

        workspace = service.workspaces_dir / project_id
        workspace.mkdir(parents=True, exist_ok=True)
        agent = GitAgent(project_root=workspace, auto_init=True)
        (workspace / "app.py").write_text("print('ok')\n", encoding="utf-8")
        assert client.post(
            "/project/create-commit", json={"project_id": project_id}
        ).json()["success"]
        assert (
            len(
                client.get("/project/commits", params={"project_id": project_id}).json()
            )
            == 1
        )


def test_project_service_runs_one_orchestrator_task_per_milestone(
    tmp_path, monkeypatch
):
    from backend.schemas.project import ProjectCreateRequest
    from core import orchestrator as orchestrator_module

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            self.project_root = kwargs["project_root"]
            self.task_planner = kwargs["task_planner"]

        def execute(self):
            tasks = self.task_planner.execute({})
            assert len(tasks) == 1
            (self.project_root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            return {
                "success": True,
                "next_day": None,
                "commits_created": [],
                "average_test_pass_rate": 1.0,
            }

    monkeypatch.setattr(orchestrator_module, "Orchestrator", FakeOrchestrator)
    service = ProjectService(tmp_path)
    project = service.create_project(
        ProjectCreateRequest(
            project_name="Milestone Integration",
            description="Build one feature",
            tech_stack=["Python"],
            days=1,
        )
    )

    result = service._execute_orchestrator(project)
    assert result["overall_success"] is True
    assert len(result["commits_created"]) == 1
    workspace = service.workspaces_dir / project["project_id"]
    commit_message = (
        GitAgent(project_root=workspace)
        ._run_git_command(["log", "-1", "--pretty=%s"])
        .stdout.strip()
    )
    assert commit_message.startswith("Day 1 - ")
    assert (
        service.projects_dir / project["project_id"] / "memory" / "reports" / "day_1.md"
    ).is_file()
    events = [event["event"] for event in service.get_logs()]
    assert "milestone_started" in events
    assert "review_completed" in events
    assert "commit_created" in events
    assert "milestone_completed" in events


def test_app_startup_resumes_projects_persisted_as_running(tmp_path):
    from backend.schemas.project import ProjectCreateRequest

    def run_day(project):
        return {"success": True, "next_day": project["current_day"] + 1}

    previous = ProjectService(tmp_path, execution_runner=run_day)
    project = previous.create_project(
        ProjectCreateRequest(
            project_name="Recovery",
            description="Resume after process interruption",
            tech_stack=["Python"],
            days=2,
        )
    )
    with previous._lock:
        previous._projects[project["project_id"]]["status"] = "running"
        previous._persist()

    restarted = ProjectService(tmp_path, execution_runner=run_day)
    with TestClient(create_app(restarted)):
        deadline = time.monotonic() + 5
        while (
            restarted.get_status(project["project_id"])["status"] == "running"
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert restarted.get_status(project["project_id"])["status"] == "waiting"
        assert restarted.get_status(project["project_id"])["current_day"] == 2


def test_project_schedule_runs_once_per_local_day_and_advances_one_day(tmp_path):
    calls = []

    def run_day(project):
        calls.append(project["current_day"])
        return {"success": True, "next_day": project["current_day"] + 1}

    service = ProjectService(tmp_path, execution_runner=run_day)
    project = service.create_project(
        ProjectCreateRequest(
            project_name="Scheduled project",
            description="Run each project day on schedule",
            tech_stack=["Python"],
            days=3,
            schedule_enabled=True,
            schedule_time="00:00",
            timezone="America/Los_Angeles",
        )
    )
    local_now = datetime.now(ZoneInfo("America/Los_Angeles"))

    assert service.run_due_schedules(local_now.astimezone(timezone.utc)) == [
        project["project_id"]
    ]
    deadline = time.monotonic() + 5
    while service.get_status(project["project_id"])["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)

    assert calls == [1]
    assert service.get_status(project["project_id"])["current_day"] == 2
    assert service.run_due_schedules(local_now.astimezone(timezone.utc)) == []

    next_day = (local_now + timedelta(days=1)).replace(hour=1)
    assert service.run_due_schedules(next_day.astimezone(timezone.utc)) == [
        project["project_id"]
    ]
    deadline = time.monotonic() + 5
    while service.get_status(project["project_id"])["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert calls == [1, 2]
    assert service.get_status(project["project_id"])["current_day"] == 3


def test_schedule_api_can_pause_and_resume_project_schedule(tmp_path):
    service = ProjectService(tmp_path)
    with TestClient(create_app(service)) as client:
        created = client.post(
            "/project/create",
            json={
                "project_name": "Schedule API",
                "description": "Manage the daily schedule",
                "tech_stack": ["Python"],
                "days": 2,
                "schedule_time": "08:30",
                "timezone": "Europe/London",
            },
        )
        project_id = created.json()["project"]["project_id"]
        assert created.json()["progress"]["schedule_enabled"] is True
        assert created.json()["progress"]["schedule_time"] == "08:30"
        assert created.json()["progress"]["timezone"] == "Europe/London"

        paused = client.put(
            "/project/schedule",
            params={"project_id": project_id},
            json={
                "enabled": False,
                "schedule_time": "10:15",
                "timezone": "Europe/London",
            },
        )
        assert paused.status_code == 200
        assert paused.json()["schedule_enabled"] is False
        assert paused.json()["next_run_at"] is None

        resumed = client.put(
            "/project/schedule",
            params={"project_id": project_id},
            json={
                "enabled": True,
                "schedule_time": "10:15",
                "timezone": "Europe/London",
            },
        )
        assert resumed.status_code == 200
        assert resumed.json()["schedule_enabled"] is True
        assert resumed.json()["next_run_at"]

        invalid = client.put(
            "/project/schedule",
            params={"project_id": project_id},
            json={"enabled": True, "schedule_time": "25:00", "timezone": "UTC"},
        )
        assert invalid.status_code == 422


def test_each_manual_execution_invocation_runs_only_one_day(tmp_path):
    calls = []

    def run_day(project):
        calls.append(project["current_day"])
        return {"success": True, "next_day": project["current_day"] + 1}

    service = ProjectService(tmp_path, execution_runner=run_day)
    project = service.create_project(
        ProjectCreateRequest(
            project_name="One day at a time",
            description="Do not consume the full roadmap in one run",
            tech_stack=["Python"],
            days=3,
            schedule_enabled=False,
        )
    )
    service.start(project["project_id"])
    deadline = time.monotonic() + 5
    while service.get_status(project["project_id"])["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)

    assert calls == [1]
    assert service.get_status(project["project_id"])["status"] == "waiting"
    assert service.get_status(project["project_id"])["current_day"] == 2


def test_startup_recovery_does_not_repeat_a_fully_persisted_day(tmp_path):
    service = ProjectService(tmp_path)
    project = service.create_project(
        ProjectCreateRequest(
            project_name="Completed-day recovery",
            description="Do not replay milestones after a state-write interruption",
            tech_stack=["Python"],
            days=1,
            schedule_enabled=False,
        )
    )
    phase = project["plan"]["phases"][0]
    engine = DayExecutionEngine(
        service._execution_state_path(project["project_id"], 1)
    )
    engine.run_day(
        1,
        phase,
        lambda _: {"success": True},
        commit_target=project["daily_commit_target"],
    )
    service._execute_orchestrator = lambda _: (_ for _ in ()).throw(
        AssertionError("Completed day should not be executed again.")
    )

    service.start(project["project_id"])
    deadline = time.monotonic() + 5
    while service.get_status(project["project_id"])["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)

    status = service.get_status(project["project_id"])
    assert status["status"] == "completed"
    assert status["completed_days"] == 1
    assert any(
        event["event"] == "execution.recovered"
        for event in service.get_logs()
    )
