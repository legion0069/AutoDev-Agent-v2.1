from core.tool_registry import ToolRegistry
from core.tool_selector import ToolSelector


def test_selector_prefers_matching_tool_and_learns_from_success_history():
    registry = ToolRegistry()
    registry.register(
        "pytest",
        capabilities=["test"],
        languages=["python"],
        success_rate=0.2,
    )
    registry.register(
        "jest",
        capabilities=["test"],
        languages=["javascript"],
        success_rate=1.0,
    )
    selector = ToolSelector(registry)

    selected = selector.select(
        "Run Python tests",
        history=[{"tool": "pytest", "success": True}],
    )

    assert selected is not None
    assert selected["tool"]["name"] == "pytest"
    assert selector.rank("Run Python tests") == selector.rank("Run Python tests")


def test_selector_excludes_platform_and_version_mismatches():
    registry = ToolRegistry()
    registry.register(
        "windows-tool",
        capabilities=["run"],
        operating_systems=["windows"],
        minimum_version="2.0",
    )

    assert ToolSelector(registry).select(
        "run",
        environment={"operating_system": "linux"},
        version="2.1",
    ) is None
