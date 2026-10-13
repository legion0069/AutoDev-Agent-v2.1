from core.repository_intelligence import RepositoryIntelligence
from core.symbol_graph import SymbolGraph


def test_repository_analysis_includes_package_ownership_and_build_graph(tmp_path):
    root = tmp_path / "project"
    package = root / "src" / "sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "module.py").write_text("def public_api():\n    return 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    (root / "CODEOWNERS").write_text("src/* @team\n", encoding="utf-8")

    report = RepositoryIntelligence(root).analyze(SymbolGraph())

    assert report["packages"] == [
        {"name": "sample", "path": "src/sample", "files": ["src/sample/__init__.py"]}
    ]
    assert report["ownership"]
    assert report["build_graph"]["pyproject.toml"] == ["python", "test"]
    assert 0 <= report["repository_health"]["score"] <= 100
