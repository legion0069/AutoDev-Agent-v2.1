from core.environment_analyzer import EnvironmentAnalyzer


def test_environment_report_detects_workspace_ci_and_build_files(tmp_path):
    root = tmp_path / "project"
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "src").mkdir()
    (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")

    report = EnvironmentAnalyzer(root).analyze()

    assert report["workspace"]["exists"] is True
    assert report["workspace"]["layout"]["source"] == ["src"]
    assert report["ci_configurations"] == [".github/workflows/ci.yml"]
    assert "pip" in report["build_systems"]
    assert report["resources"]["cpu_count"] >= 1
    assert isinstance(report["python"]["virtual_environment"], bool)
