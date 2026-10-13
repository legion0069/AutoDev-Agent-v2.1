from core.evolution_controller import EvolutionController
from core.symbol_graph import SymbolGraph


class _BenchmarkEngine:
    def generate_report(self):
        return {"runs": 2, "success_rate": 1.0}


def test_evolution_cycle_generates_deterministic_report_and_graph_links(tmp_path):
    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir()
    source.write_text("def run():\n    return 1\n", encoding="utf-8")
    graph = SymbolGraph()
    controller = EvolutionController(tmp_path, benchmark_engine=_BenchmarkEngine())

    result = controller.run_cycle(
        symbol_graph=graph,
        observations={
            "problems": [{
                "title": "Slow execution",
                "severity": "HIGH",
                "evidence": {"latency_seconds": 2.0},
            }],
            "performance": {"execution": {"latency_seconds": 2.0}},
            "benchmarks": {"baseline": {"mean_seconds": 1.0}},
        },
    )

    assert result["order"] == [
        "research",
        "experiment",
        "architecture",
        "self_optimization",
        "continuous_improvement",
        "knowledge_graph",
        "evolution_controller",
    ]
    assert result["problem"]["title"] == "Slow execution"
    assert result["benchmarks"]["benchmark_engine"]["runs"] == 2
    assert result["roadmap"]["roadmap"]
    assert result["knowledge_graph"]["nodes"]
    assert {
        edge["relation"] for edge in result["knowledge_graph"]["edges"]
    } >= {"includes_research", "includes_benchmark"}
