"""Deterministic research planning and findings for autonomous evolution."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.statistical_analyzer import StatisticalAnalyzer


_SEVERITY = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


class ResearchEngine:
    """Finds engineering problems, evaluates research plans, and publishes results."""

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir is not None else None
        self.findings: list[dict[str, Any]] = []
        if self.storage_dir is not None:
            self._load_findings()

    def discover_problems(
        self,
        observations: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Returns evidence-backed problems ordered by severity and stable ID."""
        data = observations or {}
        candidates: list[dict[str, Any]] = []

        def add(title: str, severity: str, evidence: Mapping[str, Any]) -> None:
            normalized = dict(sorted(evidence.items()))
            problem_id = _stable_id(title, normalized)
            candidates.append({
                "problem_id": problem_id,
                "title": title,
                "severity": severity,
                "evidence": normalized,
                "confidence": 0.9 if normalized else 0.5,
            })

        for problem in data.get("problems", []):
            if not isinstance(problem, Mapping):
                continue
            title = str(problem.get("title", "")).strip()
            if title:
                severity = str(problem.get("severity", "MEDIUM")).upper()
                if severity not in _SEVERITY:
                    severity = "MEDIUM"
                add(title, severity, problem.get("evidence", {}))

        quality = data.get("code_quality", {})
        if isinstance(quality, Mapping):
            for cycle in quality.get("architecture_violations", []):
                add("Architecture boundary violation", "HIGH", {"violation": str(cycle)})
            if quality.get("duplication_ratio", 0) >= 10:
                add(
                    "Elevated code duplication",
                    "MEDIUM",
                    {"duplication_ratio": quality["duplication_ratio"]},
                )
            if quality.get("dead_code_candidates"):
                add(
                    "Potential dead code",
                    "LOW",
                    {"candidate_count": len(quality["dead_code_candidates"])},
                )
            if quality.get("complexity_hotspots"):
                add(
                    "High-complexity modules",
                    "HIGH",
                    {"hotspots": list(quality["complexity_hotspots"])},
                )

        architecture = data.get("architecture", {})
        if isinstance(architecture, Mapping) and architecture.get("circular_dependencies"):
            add(
                "Circular module dependencies",
                "HIGH",
                {"cycles": list(architecture["circular_dependencies"])},
            )

        performance = data.get("performance", {})
        if isinstance(performance, Mapping):
            for stage in ("planning", "scheduling", "execution", "learning"):
                value = performance.get(stage)
                if isinstance(value, (int, float)) and value > 1.0:
                    add(
                        f"High {stage} latency",
                        "MEDIUM",
                        {"stage": stage, "latency_seconds": float(value)},
                    )

        return sorted(
            candidates,
            key=lambda item: (
                -_SEVERITY[item["severity"]],
                -item["confidence"],
                item["problem_id"],
            ),
        )

    def discover_problem(
        self,
        observations: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Returns the highest-priority discovered problem, or ``None``."""
        problems = self.discover_problems(observations)
        return problems[0] if problems else None

    def generate_research_plan(
        self,
        problem: Mapping[str, Any] | str,
        alternatives: Sequence[str] | None = None,
        *,
        metric: str = "maintainability",
        higher_is_better: bool = True,
    ) -> dict[str, Any]:
        """Creates a measurable, stable plan for comparing engineering alternatives."""
        problem_data = (
            dict(problem)
            if isinstance(problem, Mapping)
            else {"problem_id": _stable_id(str(problem)), "title": str(problem)}
        )
        title = str(problem_data.get("title", "Engineering improvement"))
        options = sorted({
            str(value).strip()
            for value in (alternatives or ("current_design", "simplified_design"))
            if str(value).strip()
        })
        if len(options) < 2:
            options = sorted(set(options) | {"current_design", "simplified_design"})
        plan_id = _stable_id(str(problem_data.get("problem_id", title)), options, metric)
        baseline = (
            "current_design"
            if "current_design" in options
            else options[0]
        )
        return {
            "plan_id": plan_id,
            "problem_id": str(problem_data.get("problem_id", _stable_id(title))),
            "goal": f"Improve {metric} for: {title}",
            "alternatives": options,
            "baseline": baseline,
            "metric": metric,
            "higher_is_better": bool(higher_is_better),
            "evaluation_criteria": [
                "Compare equivalent inputs and workloads.",
                "Require repeatable measurements before selecting a winner.",
                "Retain the baseline when evidence is inconclusive.",
            ],
            "steps": [
                "Record a baseline using the declared metric.",
                "Evaluate each alternative in an isolated experiment.",
                "Compare results and publish the evidence-backed finding.",
            ],
        }

    def evaluate_results(
        self,
        plan: Mapping[str, Any],
        results: Mapping[str, Any],
        *,
        alpha: float = 0.05,
    ) -> dict[str, Any]:
        """Ranks alternative result samples and reports statistical evidence."""
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be between 0 and 1.")
        higher_is_better = bool(plan.get("higher_is_better", True))
        evaluated: list[dict[str, Any]] = []
        for name in sorted(results):
            value = results[name]
            if isinstance(value, Mapping):
                raw_samples = value.get("samples", [value.get("score", 0.0)])
            else:
                raw_samples = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else [value]
            samples = [float(sample) for sample in raw_samples]
            if not samples:
                raise ValueError(f"Alternative {name!r} has no result samples.")
            if any(not math.isfinite(sample) for sample in samples):
                raise ValueError(f"Alternative {name!r} contains a non-finite result sample.")
            evaluated.append({
                "alternative": str(name),
                "samples": samples,
                "mean": StatisticalAnalyzer.mean(samples),
                "statistics": StatisticalAnalyzer.summarize(samples).to_dict(),
            })

        if not evaluated:
            winner = None
        else:
            evaluated.sort(
                key=lambda item: (
                    -item["mean"] if higher_is_better else item["mean"],
                    item["alternative"],
                )
            )
            winner = evaluated[0]["alternative"]
        baseline_name = str(plan.get("baseline", "current_design"))
        baseline = next(
            (item for item in evaluated if item["alternative"] == baseline_name),
            None,
        )
        comparisons = {}
        if baseline is not None:
            for item in evaluated:
                if item is baseline:
                    continue
                test = StatisticalAnalyzer.t_test_two_sample(
                    sample_a=item["samples"],
                    sample_b=baseline["samples"],
                    alpha=alpha,
                )
                comparisons[item["alternative"]] = test.to_dict()
        return {
            "plan_id": str(plan.get("plan_id", "")),
            "winner": winner,
            "is_conclusive": any(
                comparison["is_significant"] for comparison in comparisons.values()
            ),
            "alternatives": evaluated,
            "comparisons": comparisons,
        }

    def publish_findings(
        self,
        finding: Mapping[str, Any],
        *,
        knowledge_graph: Any = None,
    ) -> dict[str, Any]:
        """Stores a stable finding in memory and optionally links it to the graph."""
        record = dict(finding)
        record.setdefault("finding_id", _stable_id(record))
        record = json.loads(json.dumps(record, sort_keys=True, default=str))
        if not any(item.get("finding_id") == record["finding_id"] for item in self.findings):
            self.findings.append(record)
            self.findings.sort(key=lambda item: item["finding_id"])
        if knowledge_graph is not None:
            knowledge_graph.add_node(
                "research",
                record["finding_id"],
                str(record.get("title", record.get("goal", "Research finding"))),
                record,
            )
        if self.storage_dir is not None:
            self._persist_findings()
        return record

    def _persist_findings(self) -> None:
        assert self.storage_dir is not None
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        target = self.storage_dir / "research_findings.json"
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.storage_dir, delete=False
            ) as stream:
                json.dump(self.findings, stream, indent=2, sort_keys=True)
                temporary = Path(stream.name)
            os.replace(temporary, target)
        except OSError:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise

    def _load_findings(self) -> None:
        assert self.storage_dir is not None
        target = self.storage_dir / "research_findings.json"
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except json.JSONDecodeError as exc:
            raise ValueError(f"Research findings file {target} is not valid JSON.") from exc
        if not isinstance(data, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("finding_id"), str)
            for item in data
        ):
            raise ValueError(f"Research findings file {target} must contain findings with string IDs.")
        self.findings = sorted(data, key=lambda item: item["finding_id"])


def _stable_id(*parts: Any) -> str:
    encoded = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
