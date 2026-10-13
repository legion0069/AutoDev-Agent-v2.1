from core.architecture_evolution import ArchitectureEvolutionEngine
from core.symbol_graph import SymbolGraph


def test_architecture_report_has_deterministic_maintainability_estimate(tmp_path):
    (tmp_path / "module.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    report = ArchitectureEvolutionEngine().analyze(tmp_path, SymbolGraph())

    assert report["module_count"] >= 1
    assert 0 <= report["maintainability_estimate"] <= 100
    assert [item["name"] for item in report["alternatives"]] == [
        "retain_current_boundaries",
        "reduce_coupling_and_split_hotspots",
    ]
