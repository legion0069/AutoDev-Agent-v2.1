"""Deterministic organization dashboard aggregation and JSON/Markdown/HTML exports."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Optional


class ExecutiveDashboard:
    """Builds and exports executive views without altering the legacy enterprise dashboard."""

    def build(
        self,
        organization: Optional[dict[str, Any]] = None,
        projects: Optional[dict[str, Any]] = None,
        releases: Optional[list[dict[str, Any]]] = None,
        risks: Optional[dict[str, Any]] = None,
        performance: Optional[dict[str, Any]] = None,
        learning: Optional[dict[str, Any]] = None,
        benchmarks: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return {
            "organization": organization if organization is not None else {"team_count": 0, "agent_count": 0, "teams": []},
            "projects": projects if projects is not None else {"project_count": 0, "projects": []},
            "releases": sorted(releases or [], key=lambda item: str(item.get("release_id", ""))),
            "risks": risks if risks is not None else {"risk_count": 0, "risks": [], "mitigation_plan": []},
            "performance": performance if performance is not None else {},
            "learning": learning if learning is not None else {},
            "benchmarks": benchmarks if benchmarks is not None else {},
        }

    def export_json(self, dashboard: dict[str, Any], output_path: Optional[str | Path] = None) -> str:
        content = json.dumps(dashboard, indent=2, sort_keys=True, ensure_ascii=False)
        self._write(output_path, content)
        return content

    def export_markdown(self, dashboard: dict[str, Any], output_path: Optional[str | Path] = None) -> str:
        sections = ["# Executive Dashboard"]
        for name in ("organization", "projects", "releases", "risks", "performance", "learning", "benchmarks"):
            content = json.dumps(dashboard.get(name, {}), indent=2, sort_keys=True, ensure_ascii=False)
            sections.extend((f"## {name.replace('_', ' ').title()}", "```json", content, "```"))
        result = "\n\n".join(sections) + "\n"
        self._write(output_path, result)
        return result

    def export_html(self, dashboard: dict[str, Any], output_path: Optional[str | Path] = None) -> str:
        rows = []
        for name in ("organization", "projects", "releases", "risks", "performance", "learning", "benchmarks"):
            content = json.dumps(dashboard.get(name, {}), indent=2, sort_keys=True, ensure_ascii=False)
            rows.append(
                f"<section><h2>{html.escape(name.replace('_', ' ').title())}</h2>"
                f"<pre>{html.escape(content)}</pre></section>"
            )
        result = "<!doctype html><html><head><meta charset=\"utf-8\"><title>Executive Dashboard</title></head><body><h1>Executive Dashboard</h1>" + "".join(rows) + "</body></html>\n"
        self._write(output_path, result)
        return result

    @staticmethod
    def _write(output_path: Optional[str | Path], content: str) -> None:
        if output_path is not None:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
