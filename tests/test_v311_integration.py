import inspect
import json

from core.orchestrator import Orchestrator
from core.symbol_graph import SymbolGraph
from tests.benchmark_v311 import run_benchmarks


class _EnvironmentControllerSpy:
    def __init__(self):
        self.calls = []

    def analyze(self, **kwargs):
        self.calls.append(kwargs)
        return {"version": "3.11", "execution_performed": False}


class _ContextBuilderStub:
    def __init__(self):
        self.change_detector = None

    def build(self, *, project_root):
        return {
            "current_phase": {"phase_name": "test", "description": "test"},
            "project_files": [],
            "symbol_graph": SymbolGraph(),
        }


class _TaskPlannerStub:
    def __init__(self):
        self.context = None

    def execute(self, context):
        self.context = context
        return []


class _IncrementalIndexerStub:
    def __init__(self):
        self.graph = SymbolGraph()

    def index_project(self, *, changes):
        return self.graph


def test_environment_mode_is_optional_and_appended_after_existing_parameters():
    parameters = inspect.signature(Orchestrator.__init__).parameters

    assert parameters["memory_mode"].default is False
    assert parameters["environment_mode"].default is False
    assert list(parameters)[-2:] == ["environment_mode", "environment_controller"]


def test_environment_mode_is_opt_in_and_report_is_attached_to_dashboard(tmp_path):
    root = tmp_path / "enabled"
    (root / "memory").mkdir(parents=True)
    plan_path = root / "memory" / "project_plan.json"
    plan_path.write_text(
        '{"total_days": 1, "phases": [{"day": 1, "phase_name": "test"}]}',
        encoding="utf-8",
    )
    disabled = Orchestrator(
        project_root=tmp_path / "disabled",
        log_dir=tmp_path / "disabled-logs",
    )
    controller = _EnvironmentControllerSpy()
    planner = _TaskPlannerStub()
    indexer = _IncrementalIndexerStub()
    enabled = Orchestrator(
        project_root=root,
        plan_path=plan_path,
        state_path=root / "memory" / "state.json",
        tasks_path=root / "memory" / "tasks.json",
        log_dir=root / "logs",
        context_builder=_ContextBuilderStub(),
        task_planner=planner,
        incremental_indexer=indexer,
        environment_mode=True,
        environment_controller=controller,
    )
    try:
        assert disabled.environment_mode is False
        assert disabled.environment_controller is None
        assert enabled.environment_mode is True
        enabled.repository_analyzer = None
        enabled.ecosystem_engine = None
        result = enabled.run()

        assert result.overall_success is True
        assert len(controller.calls) == 1
        assert controller.calls[0]["symbol_graph"] is indexer.graph
        assert "environment_intelligence" in planner.context
        assert enabled.latest_evolution_dashboard["environment_intelligence"] == {
            "version": "3.11",
            "execution_performed": False,
        }
        assert controller.calls[0]["task"].startswith("Analyze repository")
    finally:
        for orchestrator in (disabled, enabled):
            if orchestrator.multi_agent_runtime is not None:
                orchestrator.multi_agent_runtime.close()


def test_v311_benchmark_writes_result_history_and_performance_reports(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Benchmark\n", encoding="utf-8")
    (workspace / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (workspace / "module.py").write_text("def public_api():\n    return 1\n", encoding="utf-8")

    result = run_benchmarks(tmp_path / "reports", project_root=workspace, iterations=1)

    assert result["version"] == "3.11"
    assert set(result["metrics"]) == {
        "environment_scan_latency",
        "repository_scan_latency",
        "dependency_analysis_latency",
        "git_analysis_latency",
        "tool_selection_latency",
        "api_discovery_latency",
        "environment_report_generation_latency",
    }
    for filename in (
        "v311_benchmark_results.json",
        "v311_benchmark_history.json",
        "v311_performance_report.json",
    ):
        assert json.loads((tmp_path / "reports" / filename).read_text(encoding="utf-8"))
