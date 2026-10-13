import shutil
import subprocess

import pytest

from core.git_intelligence import GitIntelligence


def test_git_intelligence_reports_unavailable_for_non_repository(tmp_path):
    report = GitIntelligence(tmp_path).analyze()

    assert report["available"] is False
    assert report["commits"] == []
    assert report["hotspots"] == []


@pytest.mark.skipif(shutil.which("git") is None, reason="Git executable is unavailable")
def test_git_intelligence_reports_commits_and_file_hotspots(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    source = root / "module.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "module.py"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "Add module"], check=True)
    source.write_text("value = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "commit", "-qam", "Fix module"], check=True)

    report = GitIntelligence(root).analyze()

    assert report["available"] is True
    assert len(report["commits"]) == 2
    assert report["hotspots"][0] == {"path": "module.py", "change_count": 2}
    assert report["ownership"][0]["author"] == "Test User"
