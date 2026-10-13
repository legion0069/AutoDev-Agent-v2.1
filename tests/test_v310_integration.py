import inspect
import json

from core.memory_controller import MemoryController
from core.orchestrator import Orchestrator
from tests.benchmark_v310 import run_benchmarks


def test_memory_mode_remains_optional_with_later_opt_in_features():
    parameters = inspect.signature(Orchestrator.__init__).parameters
    assert parameters["memory_mode"].default is False


def test_orchestrator_only_initializes_memory_when_enabled(tmp_path):
    disabled = Orchestrator(
        project_root=tmp_path / "disabled",
        log_dir=tmp_path / "disabled-logs",
    )
    enabled = Orchestrator(
        project_root=tmp_path / "enabled",
        log_dir=tmp_path / "enabled-logs",
        memory_mode=True,
    )

    assert disabled.memory_controller is None
    assert enabled.memory_controller is not None


def test_memory_capabilities_share_persistent_records(tmp_path):
    controller = MemoryController(tmp_path)
    controller.record_task_outcome({
        "task_id": "integration-task",
        "title": "Add documentation search",
        "success": True,
        "recommendation": "Index headings before searching",
    })

    assert controller.search("documentation search")
    assert controller.recommendations.recommend("documentation")


def test_benchmark_harness_writes_all_required_reports(tmp_path):
    result = run_benchmarks(tmp_path)

    assert result["version"] == "3.10"
    assert len(result["metrics"]) == 9
    for name in (
        "v310_benchmark_results.json",
        "v310_benchmark_history.json",
        "v310_performance_report.json",
    ):
        assert json.loads((tmp_path / name).read_text(encoding="utf-8"))
