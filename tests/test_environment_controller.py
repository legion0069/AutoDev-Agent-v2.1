from core.environment_controller import EnvironmentController
from core.symbol_graph import SymbolGraph
from core.tool_registry import ToolRegistry


def test_environment_controller_assembles_intelligence_report_without_execution(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text(
        "# Project\n\nSee [architecture](docs/architecture.md).\n",
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0\n", encoding="utf-8")
    (root / "architecture.md").write_text("# Architecture\n\nSystem overview.\n", encoding="utf-8")
    (root / "api.py").write_text("def public_api():\n    return 1\n", encoding="utf-8")
    registry = ToolRegistry()
    registry.register("pytest", capabilities=["test"], languages=["python"])

    controller = EnvironmentController(root, tool_registry=registry)
    report = controller.analyze(symbol_graph=SymbolGraph(), task="Test the Python repository")

    assert report["version"] == "3.11"
    assert report["execution_performed"] is False
    assert report["documentation"]["readme"]
    assert report["documentation"]["changelog"]
    assert report["documentation"]["architecture_documents"]
    assert report["documentation"]["cross_references"] == [
        {"source": "README.md", "target": "docs/architecture.md"}
    ]
    assert report["documentation"]["api_metadata"]
    assert controller.status()["report_available"] is True
