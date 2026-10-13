import json

from core.executive_dashboard import ExecutiveDashboard


def test_dashboard_exports_json_markdown_and_html(tmp_path):
    dashboard = ExecutiveDashboard()
    model = dashboard.build(
        organization={"team_count": 1},
        risks={"risk_count": 0},
    )
    json_path = tmp_path / "dashboard.json"
    markdown_path = tmp_path / "dashboard.md"
    html_path = tmp_path / "dashboard.html"

    assert json.loads(dashboard.export_json(model, json_path))["organization"]["team_count"] == 1
    assert "## Organization" in dashboard.export_markdown(model, markdown_path)
    html_content = dashboard.export_html(model, html_path)
    assert "<title>Executive Dashboard</title>" in html_content
    assert json_path.exists() and markdown_path.exists() and html_path.exists()


def test_html_output_escapes_embedded_values():
    content = ExecutiveDashboard().export_html({"organization": {"name": "<script>"}})
    assert "&lt;script&gt;" in content
    assert "<script>" not in content


def test_build_preserves_explicit_empty_sections():
    model = ExecutiveDashboard().build(organization={}, projects={}, risks={})
    assert model["organization"] == {}
    assert model["projects"] == {}
    assert model["risks"] == {}
