from core.code_quality_engine import CodeQualityEngine


def test_quality_analysis_reports_metrics_and_parse_errors(tmp_path):
    (tmp_path / "sample.py").write_text(
        "class Example:\n"
        "    def first(self):\n"
        "        return self.value\n"
        "    def second(self):\n"
        "        return self.value\n",
        encoding="utf-8",
    )
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    report = CodeQualityEngine().analyze(tmp_path)

    assert report["file_count"] == 2
    assert 0 <= report["maintainability_index"] <= 100
    assert report["analysis_errors"][0]["file"] == "broken.py"
    assert "cohesion" in report
    assert "coupling" in report
    assert "duplication_ratio" in report
