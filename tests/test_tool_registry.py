from core.tool_registry import ToolMetadata, ToolRegistry, is_version_compatible


def test_registry_normalizes_names_and_returns_stable_capability_matches():
    registry = ToolRegistry()
    registry.register("Python", capabilities=["run"], languages=["python"])
    registry.register("python", capabilities=["run"], languages=["python"])

    assert len(registry.list_tools()) == 1
    assert [tool.name for tool in registry.lookup("run", language="python")] == ["python"]


def test_discover_empty_executable_list_does_not_fall_back_to_common_tools():
    assert ToolRegistry().discover(executables=[]) == []


def test_registry_checks_version_bounds_with_different_precision():
    tool = ToolMetadata(name="compiler", minimum_version="3.10.0", maximum_version="4")

    assert is_version_compatible(tool, "3.10")
    assert is_version_compatible(tool, "4.0.0")
    assert not is_version_compatible(tool, "3.9")
    assert not is_version_compatible(tool, "4.0.1")
