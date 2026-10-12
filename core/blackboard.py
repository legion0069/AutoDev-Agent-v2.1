"""Versioned shared blackboard with locking and optimistic conflict detection."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass
from typing import Any, Optional


class BlackboardConflictError(RuntimeError):
    """Raised when a writer observes a stale version or another owner's lock."""


@dataclass(frozen=True)
class BlackboardVersion:
    key: str
    version: int
    value: Any
    writer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "value": copy.deepcopy(self.value),
            "writer": self.writer,
        }


class Blackboard:
    """Thread-safe, copy-isolated shared values with rollback-able history."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._values: dict[str, Any] = {}
        self._versions: dict[str, int] = {}
        self._history: dict[str, list[BlackboardVersion]] = {}
        self._owners: dict[str, str] = {}

    def read(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return copy.deepcopy(self._values.get(key, default))

    def write(
        self,
        key: str,
        value: Any,
        writer: str = "system",
        expected_version: Optional[int] = None,
    ) -> int:
        if not key:
            raise ValueError("key must not be empty")
        with self._lock:
            owner = self._owners.get(key)
            if owner is not None and owner != writer:
                raise BlackboardConflictError(f"key {key!r} is locked by {owner!r}")
            current = self._versions.get(key, 0)
            if expected_version is not None and expected_version != current:
                raise BlackboardConflictError(
                    f"stale version for {key!r}: expected {expected_version}, current {current}"
                )
            version = current + 1
            stored = copy.deepcopy(value)
            self._values[key] = stored
            self._versions[key] = version
            self._history.setdefault(key, []).append(
                BlackboardVersion(key, version, stored, writer)
            )
            return version

    def lock(self, key: str, owner: str) -> bool:
        if not key or not owner:
            raise ValueError("key and owner are required")
        with self._lock:
            current = self._owners.get(key)
            if current is not None and current != owner:
                return False
            self._owners[key] = owner
            return True

    def unlock(self, key: str, owner: str) -> bool:
        with self._lock:
            if self._owners.get(key) != owner:
                return False
            del self._owners[key]
            return True

    def history(self, key: str) -> list[BlackboardVersion]:
        with self._lock:
            return copy.deepcopy(self._history.get(key, []))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "values": copy.deepcopy(self._values),
                "versions": dict(self._versions),
                "history": {
                    key: [entry.to_dict() for entry in entries]
                    for key, entries in sorted(self._history.items())
                },
            }

    def rollback(self, key: str, version: Optional[int] = None, writer: str = "system") -> int:
        with self._lock:
            entries = self._history.get(key, [])
            candidates = [entry for entry in entries if entry.version == version] if version is not None else entries[:-1]
            if not candidates:
                raise KeyError(f"No prior version exists for key {key!r}")
            previous = candidates[-1]
            return self.write(key, previous.value, writer=writer)

    def version(self, key: str) -> int:
        with self._lock:
            return self._versions.get(key, 0)
