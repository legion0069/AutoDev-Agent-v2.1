from core.tool_execution_planner import ToolExecutionPlanner
from core.tool_registry import ToolRegistry
from core.tool_selector import ToolSelector


def test_execution_plan_is_deterministic_ordered_and_never_runs_tools():
    registry = ToolRegistry()
    registry.register("git", capabilities=["version_control", "repository"])
    registry.register("pytest", capabilities=["test"], languages=["python"])
    planner = ToolExecutionPlanner(ToolSelector(registry))

    first = planner.plan("Implement repository tests")
    second = planner.plan("Implement repository tests")

    assert first == second
    assert [step["id"] for step in first["steps"]] == [
        "repository_scan",
        "dependency_analysis",
        "git_analysis",
        "environment_scan",
        "implementation",
        "testing",
        "documentation",
        "benchmarks",
    ]
    assert first["execution_performed"] is False
    assert all(step["order"] == index for index, step in enumerate(first["steps"], 1))
