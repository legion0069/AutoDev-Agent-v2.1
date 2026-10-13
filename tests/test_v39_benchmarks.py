from benchmarks.v39_benchmarks import run_benchmarks


def test_v39_benchmarks_measure_all_requested_latencies(tmp_path):
    result = run_benchmarks(tmp_path, iterations=2)
    assert set(result["metrics"]) == {
        "organization_creation_latency",
        "team_formation_latency",
        "sprint_planning_latency",
        "resource_allocation_latency",
        "risk_analysis_latency",
        "analytics_generation_latency",
        "dashboard_generation_latency",
    }
    assert all(metric["iterations"] == 2 for metric in result["metrics"].values())
    assert (tmp_path / "v39_benchmark_results.json").exists()
    assert (tmp_path / "v39_benchmark_history.json").exists()
    assert (tmp_path / "v39_performance_report.json").exists()
