"""Persistent per-agent execution, quality, and collaboration measurements."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("AutoDev.AgentMetrics")


class AgentMetricsTracker:
    """Maintains reproducible aggregate metrics and bounded execution history."""

    def __init__(self, storage_dir: str | Path = "memory/agent_metrics") -> None:
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._metrics: dict[str, dict[str, Any]] = {}
        self._load()

    def record(
        self,
        agent_id: str,
        success: bool,
        execution_time: float = 0.0,
        review_score: float = 0.0,
        defects: int = 0,
        collaboration_score: float = 0.0,
        resource_usage: Optional[dict[str, float]] = None,
    ) -> dict[str, Any]:
        if not agent_id:
            raise ValueError("agent_id must not be empty")
        if execution_time < 0 or defects < 0:
            raise ValueError("execution_time and defects must not be negative")
        record = {
            "success": bool(success),
            "execution_time": float(execution_time),
            "review_score": self._bounded(review_score, 100.0),
            "defects": int(defects),
            "collaboration_score": self._bounded(collaboration_score, 100.0),
            "resource_usage": {
                str(key): max(0.0, float(value))
                for key, value in sorted((resource_usage or {}).items())
            },
        }
        with self._lock:
            metric = self._metrics.setdefault(agent_id, {"history": []})
            metric["history"].append(record)
            metric["history"] = metric["history"][-1000:]
            result = self._summarize(metric["history"])
            metric.update(result)
            self._save_agent(agent_id, metric)
            return json.loads(json.dumps(result, sort_keys=True))

    def get_metrics(self, agent_id: str) -> dict[str, Any]:
        with self._lock:
            metric = self._metrics.get(agent_id)
            if metric is None:
                return self._summarize([])
            return {
                key: value
                for key, value in metric.items()
                if key != "history"
            }

    def all_metrics(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {agent_id: self.get_metrics(agent_id) for agent_id in sorted(self._metrics)}

    def _load(self) -> None:
        for path in sorted(self.storage_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or not isinstance(data.get("agent_id"), str):
                    raise ValueError("Agent metrics document has an invalid schema")
                history = data.get("history", [])
                if not isinstance(history, list):
                    raise ValueError("Agent metrics history must be a list")
                self._metrics[data["agent_id"]] = {
                    "history": history[-1000:],
                    **self._summarize(history),
                }
            except (OSError, ValueError, TypeError) as err:
                logger.warning("Ignoring invalid agent metrics file %s: %s", path, err)

    def _save_agent(self, agent_id: str, metric: dict[str, Any]) -> None:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", agent_id)[:100] or "agent"
        target = self.storage_dir / f"{safe_id}.json"
        data = {"agent_id": agent_id, **metric}
        temporary_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.storage_dir, delete=False
            ) as temporary:
                json.dump(data, temporary, sort_keys=True, indent=2)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, target)
        except (OSError, TypeError, ValueError) as err:
            logger.error("Could not persist metrics for agent %s: %s", agent_id, err)
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _summarize(history: list[dict[str, Any]]) -> dict[str, Any]:
        count = len(history)
        successes = sum(1 for entry in history if bool(entry.get("success")))
        failures = count - successes
        if count:
            average_time = sum(float(entry.get("execution_time", 0.0)) for entry in history) / count
            review = sum(float(entry.get("review_score", 0.0)) for entry in history) / count
            defects = sum(int(entry.get("defects", 0)) for entry in history)
            collaboration = sum(float(entry.get("collaboration_score", 0.0)) for entry in history) / count
            resource_names = sorted({
                key for entry in history for key in entry.get("resource_usage", {})
            })
            resources = {
                key: round(
                    sum(float(entry.get("resource_usage", {}).get(key, 0.0)) for entry in history) / count,
                    4,
                )
                for key in resource_names
            }
            recent = history[-max(1, count // 2):]
            earlier = history[:count - len(recent)]
            trend = (
                round(
                    sum(1.0 if entry.get("success") else 0.0 for entry in recent) / len(recent)
                    - sum(1.0 if entry.get("success") else 0.0 for entry in earlier) / len(earlier),
                    4,
                )
                if earlier else 0.0
            )
        else:
            average_time = review = collaboration = 0.0
            defects = 0
            resources = {}
            trend = 0.0
        return {
            "task_count": count,
            "success_rate": round(successes / count, 4) if count else 0.0,
            "failure_rate": round(failures / count, 4) if count else 0.0,
            "average_execution_time": round(average_time, 4),
            "average_review_score": round(review, 4),
            "defect_rate": round(defects / count, 4) if count else 0.0,
            "collaboration_score": round(collaboration, 4),
            "resource_usage": resources,
            "improvement_trend": trend,
        }

    @staticmethod
    def _bounded(value: float, maximum: float) -> float:
        return max(0.0, min(maximum, float(value)))
