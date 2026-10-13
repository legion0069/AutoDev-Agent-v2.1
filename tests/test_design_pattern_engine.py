from core.design_pattern_engine import DesignPatternEngine


def test_pattern_engine_detects_patterns_and_antipatterns(tmp_path):
    (tmp_path / "sample.py").write_text(
        "class UserRepository:\n"
        "    def get(self, key):\n"
        "        try:\n"
        "            return key\n"
        "        except:\n"
        "            return None\n"
        "\n"
        "def create_user():\n"
        "    return UserRepository()\n",
        encoding="utf-8",
    )

    report = DesignPatternEngine().analyze(tmp_path)

    assert {item["kind"] for item in report["patterns"]} >= {"repository", "factory"}
    assert any(item["kind"] == "bare_except" for item in report["anti_patterns"])
    assert report["recommendations"]
