from benchmarks.v40_benchmarks import run_benchmarks


def test_v40_benchmark_report_contains_all_required_measurements(tmp_path):
    result = run_benchmarks(tmp_path, iterations=1)

    assert set(result["metrics"]) == {
        "research_planning_latency",
        "architecture_analysis_latency",
        "experiment_execution_latency",
        "knowledge_graph_construction_latency",
        "optimization_latency",
        "evolution_cycle_latency",
    }
    assert all(
        metric["iterations"] == 1
        for metric in result["metrics"].values()
    )
    assert (tmp_path / "v40_benchmark_results.json").is_file()
    assert (tmp_path / "v40_benchmark_history.json").is_file()
    assert (tmp_path / "v40_performance_report.json").is_file()
