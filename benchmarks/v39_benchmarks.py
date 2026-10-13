"""Repeatable local latency benchmarks for AutoDev v3.9 organization workflows."""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.delivery_manager import DeliveryManager
from core.engineering_analytics import EngineeringAnalytics
from core.executive_dashboard import ExecutiveDashboard
from core.multi_agent.agent_registry import AgentDescriptor, AgentRole
from core.multi_agent_runtime import MultiAgentRuntime
from core.organization_manager import OrganizationManager
from core.project_manager import ProjectManager
from core.resource_manager import ResourceManager
from core.risk_manager import RiskManager
from core.team_builder import TeamBuilder


def _measure(operation: Callable[[], object], iterations: int) -> dict[str, float | int]:
    durations = []
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        durations.append(time.perf_counter() - started)
    return {
        "iterations": iterations,
        "min_seconds": round(min(durations), 8),
        "mean_seconds": round(statistics.fmean(durations), 8),
        "max_seconds": round(max(durations), 8),
    }


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            temporary = Path(stream.name)
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError):
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def run_benchmarks(
    output_dir: str | Path = "memory/benchmarks",
    iterations: int = 25,
) -> dict[str, object]:
    if iterations <= 0:
        raise ValueError("iterations must be greater than zero.")
    output = Path(output_dir)
    runtime = MultiAgentRuntime()
    runtime.register_agent(AgentDescriptor(
        agent_id="benchmark-backend",
        name="Benchmark Backend",
        role=AgentRole.BACKEND_ENGINEER,
        capabilities=["backend", "implementation", "python"],
    ))
    organization = OrganizationManager(runtime)
    project_manager = ProjectManager()
    project_manager.create_project("Benchmark project", project_id="BENCHMARK")
    resources = ResourceManager({"workers": float(iterations + 1)})
    risks = RiskManager()
    scratch = tempfile.TemporaryDirectory(prefix="autodev-v39-benchmark-")
    analytics = EngineeringAnalytics(scratch.name)
    analytics.record(completed=True, lead_time_hours=1, cycle_time_hours=0.5)
    dashboard = ExecutiveDashboard()
    team_builder = TeamBuilder(organization, runtime)
    delivery = DeliveryManager()
    dashboard_input = dashboard.build(
        organization=organization.organization_summary(),
        projects=project_manager.project_dashboard(),
        risks=risks.analyze().to_dict(),
        performance=analytics.metrics(),
        releases=[delivery.assess_release("BENCHMARK-RELEASE")],
    )

    try:
        metrics = {
            "organization_creation_latency": _measure(
                lambda: OrganizationManager(), iterations
            ),
            "team_formation_latency": _measure(
                lambda: team_builder.build_team(
                    "Benchmark", required_roles=["Backend"]
                ),
                iterations,
            ),
            "sprint_planning_latency": _measure(
                lambda: project_manager.create_sprint("BENCHMARK", "Benchmark sprint"),
                iterations,
            ),
            "resource_allocation_latency": _measure(
                lambda: resources.release(
                    resources.allocate("workers", 1, "benchmark").allocation_id
                ),
                iterations,
            ),
            "risk_analysis_latency": _measure(
                lambda: risks.analyze({
                    "overdue_milestones": 1,
                    "technical_debt_items": 2,
                    "quality_score": 78,
                }),
                iterations,
            ),
            "analytics_generation_latency": _measure(analytics.metrics, iterations),
            "dashboard_generation_latency": _measure(
                lambda: dashboard.build(
                    organization=dashboard_input["organization"],
                    projects=dashboard_input["projects"],
                    risks=dashboard_input["risks"],
                    performance=analytics.metrics(),
                ),
                iterations,
            ),
        }
    finally:
        runtime.close()
        scratch.cleanup()

    results: dict[str, object] = {
        "version": "3.9",
        "iterations": iterations,
        "metrics": metrics,
        "notes": "Local microbenchmarks; timings are machine- and load-dependent.",
    }
    history_path = output / "v39_benchmark_history.json"
    try:
        history = json.loads(history_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        history = []
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"Cannot load benchmark history {history_path}: {exc}") from exc
    if not isinstance(history, list):
        raise ValueError(f"Benchmark history {history_path} must contain a JSON list.")
    history.append(results)
    _write_json(history_path, history)
    _write_json(output / "v39_benchmark_results.json", results)
    _write_json(output / "v39_performance_report.json", {
        "version": "3.9",
        "benchmarks": metrics,
        "measurement_note": results["notes"],
    })
    return results


if __name__ == "__main__":
    print(json.dumps(run_benchmarks(), indent=2, sort_keys=True))
