import json

from benchmark_v38 import run_benchmarks


def test_benchmark_writes_results_and_history(tmp_path) -> None:
    result = run_benchmarks(tmp_path, iterations=2)
    result_path = tmp_path / "v38_multi_agent_results.json"
    history_path = tmp_path / "v38_benchmark_history.json"

    assert result["version"] == "3.8"
    assert result["metrics"]["warm_cache_hit_ratio"] == 1.0
    assert result_path.is_file()
    assert history_path.is_file()
    assert json.loads(result_path.read_text(encoding="utf-8")) == result
    assert len(json.loads(history_path.read_text(encoding="utf-8"))) == 1
