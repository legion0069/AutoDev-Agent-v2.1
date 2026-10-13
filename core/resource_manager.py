"""Deterministic resource allocation, queueing, and capacity forecasting."""

from __future__ import annotations

import math
import threading
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class ResourceAllocation:
    allocation_id: str
    resource: str
    amount: float
    owner: str
    priority: int
    status: str
    sequence: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ResourceManager:
    """Allocates named CPU, memory, and worker capacity with a stable priority queue."""

    def __init__(self, capacities: Optional[dict[str, float]] = None) -> None:
        defaults = {"cpu": 1.0, "memory": 1024.0, "workers": 4.0}
        if capacities:
            defaults.update({self._normalize(key): float(value) for key, value in capacities.items()})
        if any(not math.isfinite(value) or value < 0 for value in defaults.values()):
            raise ValueError("Resource capacities must be finite and non-negative.")
        self._capacities = defaults
        self._allocations: dict[str, ResourceAllocation] = {}
        self._lock = threading.RLock()
        self._sequence = 0

    def allocate(
        self,
        resource: str,
        amount: float,
        owner: str,
        priority: int = 0,
    ) -> ResourceAllocation:
        normalized = self._normalize(resource)
        value = float(amount)
        if not normalized or not owner.strip():
            raise ValueError("Resource and owner must not be empty.")
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Allocation amount must be finite and greater than zero.")
        with self._lock:
            if normalized not in self._capacities:
                raise KeyError(f"Unknown resource {normalized!r}.")
            self._sequence += 1
            has_waiting_requests = any(
                item.resource == normalized and item.status == "QUEUED"
                for item in self._allocations.values()
            )
            allocation = ResourceAllocation(
                allocation_id=f"ALLOC-{self._sequence:06d}",
                resource=normalized,
                amount=value,
                owner=owner,
                priority=int(priority),
                status=(
                    "ALLOCATED"
                    if not has_waiting_requests and self._available(normalized) >= value
                    else "QUEUED"
                ),
                sequence=self._sequence,
            )
            self._allocations[allocation.allocation_id] = allocation
            self._drain_queue(normalized)
            return ResourceAllocation(**allocation.to_dict())

    def release(self, allocation_id: str) -> bool:
        with self._lock:
            allocation = self._allocations.get(allocation_id)
            if allocation is None or allocation.status in {"RELEASED", "CANCELLED"}:
                return False
            resource = allocation.resource
            allocation.status = "RELEASED" if allocation.status == "ALLOCATED" else "CANCELLED"
            self._drain_queue(resource)
            return True

    def forecast(self, demand: Optional[dict[str, float]] = None) -> dict[str, dict[str, float | bool]]:
        with self._lock:
            forecast: dict[str, dict[str, float | bool]] = {}
            requested = {self._normalize(k): float(v) for k, v in (demand or {}).items()}
            unknown = sorted(set(requested) - set(self._capacities))
            if unknown:
                raise KeyError(f"Unknown resource demand: {unknown}.")
            if any(not math.isfinite(value) or value < 0 for value in requested.values()):
                raise ValueError("Forecast demand must be finite and non-negative.")
            for resource in sorted(self._capacities):
                used = self._used(resource)
                amount = requested.get(resource, 0.0)
                forecast[resource] = {
                    "capacity": self._capacities[resource],
                    "allocated": used,
                    "available": max(0.0, self._capacities[resource] - used),
                    "requested": amount,
                    "sufficient": amount <= max(0.0, self._capacities[resource] - used),
                }
            return forecast

    def resource_usage(self) -> dict[str, object]:
        with self._lock:
            by_resource = self.forecast()
            queue = [
                item.to_dict()
                for item in sorted(
                    (item for item in self._allocations.values() if item.status == "QUEUED"),
                    key=lambda item: (-item.priority, item.sequence),
                )
            ]
            return {"resources": by_resource, "queued": queue, "queue_count": len(queue)}

    def _drain_queue(self, resource: str) -> None:
        queued = sorted(
            (
                item for item in self._allocations.values()
                if item.resource == resource and item.status == "QUEUED"
            ),
            key=lambda item: (-item.priority, item.sequence),
        )
        for allocation in queued:
            if self._available(resource) >= allocation.amount:
                allocation.status = "ALLOCATED"
            else:
                break

    def _used(self, resource: str) -> float:
        return sum(
            item.amount
            for item in self._allocations.values()
            if item.resource == resource and item.status == "ALLOCATED"
        )

    def _available(self, resource: str) -> float:
        return max(0.0, self._capacities[resource] - self._used(resource))

    @staticmethod
    def _normalize(resource: str) -> str:
        return str(resource).strip().lower().replace("-", "_")
