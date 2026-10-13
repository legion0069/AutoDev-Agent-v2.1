"""Persisted engineering delivery metrics with deterministic aggregation."""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional


class EngineeringAnalytics:
    """Records delivery measurements and derives aggregate velocity and quality metrics."""

    def __init__(self, storage_dir: str | Path = "memory/engineering_metrics") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.storage_dir / "engineering_metrics.json"
        self._lock = threading.RLock()
        self._events: list[dict[str, Any]] = []
        self._load()

    def record(
        self,
        *,
        completed: bool,
        lead_time_hours: float = 0.0,
        cycle_time_hours: float = 0.0,
        review_duration_hours: float = 0.0,
        defects: int = 0,
        deployments: int = 0,
        deployment_ready: Optional[bool] = None,
    ) -> dict[str, Any]:
        durations = (lead_time_hours, cycle_time_hours, review_duration_hours)
        if (
            any(not math.isfinite(value) or value < 0 for value in durations)
            or defects < 0
            or deployments < 0
            or (deployment_ready is not None and not isinstance(deployment_ready, bool))
        ):
            raise ValueError("Metrics must contain non-negative values and an optional boolean readiness flag.")
        event = {
            "completed": bool(completed),
            "lead_time_hours": float(lead_time_hours),
            "cycle_time_hours": float(cycle_time_hours),
            "review_duration_hours": float(review_duration_hours),
            "defects": int(defects),
            "deployments": int(deployments),
            "deployment_ready": deployment_ready,
        }
        with self._lock:
            self._events.append(event)
            self._save()
            return dict(event)

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            count = len(self._events)
            average = lambda key: round(
                sum(float(item[key]) for item in self._events) / count, 4
            ) if count else 0.0
            completed = sum(bool(item["completed"]) for item in self._events)
            return {
                "sample_count": count,
                "velocity": completed,
                "throughput": completed,
                "lead_time_hours": average("lead_time_hours"),
                "cycle_time_hours": average("cycle_time_hours"),
                "review_duration_hours": average("review_duration_hours"),
                "defect_escape_rate": round(
                    sum(int(item["defects"]) > 0 for item in self._events) / count, 4
                ) if count else 0.0,
                "defects_per_delivery": round(
                    sum(int(item["defects"]) for item in self._events) / count, 4
                ) if count else 0.0,
                "deployments": sum(int(item["deployments"]) for item in self._events),
                "completion_rate": round(completed / count, 4) if count else 0.0,
                "deployment_readiness": round(
                    sum(item.get("deployment_ready") is True for item in self._events)
                    / sum(item.get("deployment_ready") is not None for item in self._events), 4
                ) if any(item.get("deployment_ready") is not None for item in self._events) else 0.0,
            }

    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._events]

    def _load(self) -> None:
        try:
            data = json.loads(self.history_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot load engineering metrics from {self.history_file}: {exc}") from exc
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise ValueError(f"Invalid engineering metrics format in {self.history_file}.")
        required = {
            "completed",
            "lead_time_hours",
            "cycle_time_hours",
            "review_duration_hours",
            "defects",
            "deployments",
        }
        if any(not required.issubset(item) for item in data):
            raise ValueError(f"Engineering metrics entries in {self.history_file} are incomplete.")
        self._events = data

    def _save(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        temporary_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.storage_dir, delete=False
            ) as stream:
                json.dump(self._events, stream, sort_keys=True, indent=2)
                temporary_path = Path(stream.name)
            os.replace(temporary_path, self.history_file)
        except (OSError, TypeError, ValueError):
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
