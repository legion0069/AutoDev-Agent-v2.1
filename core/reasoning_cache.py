"""Versioned, deterministic JSON cache for structured reasoning results."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("AutoDev.ReasoningCache")


class ReasoningCache:
    """Stores JSON-safe reasoning outputs using content-addressed keys."""

    VERSION = 1

    def __init__(
        self,
        name: str,
        project_root: str | Path = ".",
        cache_manager: Optional[Any] = None,
        cache_root: Optional[str | Path] = None,
    ) -> None:
        if cache_manager is not None:
            self.root = Path(cache_manager.register_cache(f"reasoning/{name}", str(self.VERSION)))
        elif cache_root is not None:
            self.root = Path(cache_root).resolve() / name
        else:
            self.root = Path(project_root).resolve() / "memory" / "cache" / "reasoning" / name
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._repairs = 0

    @staticmethod
    def key(value: Any) -> str:
        payload = json.dumps(
            ReasoningCache._normalize(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): ReasoningCache._normalize(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [ReasoningCache._normalize(item) for item in value]
        if isinstance(value, (set, frozenset)):
            return sorted(
                (ReasoningCache._normalize(item) for item in value),
                key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=True),
            )
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Path):
            return value.as_posix()
        if is_dataclass(value):
            return ReasoningCache._normalize(asdict(value))
        if hasattr(value, "to_dict"):
            return ReasoningCache._normalize(value.to_dict())
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    def get(self, key: Any) -> Optional[Any]:
        entry_path = self.root / f"{self.key(key)}.json"
        with self._lock:
            try:
                entry = json.loads(entry_path.read_text(encoding="utf-8"))
                if (
                    not isinstance(entry, dict)
                    or entry.get("version") != self.VERSION
                    or entry.get("key") != self.key(key)
                    or "value" not in entry
                ):
                    raise ValueError("Invalid or incompatible reasoning cache entry.")
                self._hits += 1
                return entry["value"]
            except FileNotFoundError:
                self._misses += 1
                return None
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as err:
                logger.warning("Discarding invalid reasoning cache entry %s: %s", entry_path, err)
                self._repairs += 1
                self._misses += 1
                try:
                    entry_path.unlink(missing_ok=True)
                except OSError as unlink_error:
                    logger.warning("Could not remove invalid cache entry %s: %s", entry_path, unlink_error)
                return None

    def set(self, key: Any, value: Any) -> None:
        entry_path = self.root / f"{self.key(key)}.json"
        data = {"version": self.VERSION, "key": self.key(key), "value": value}
        with self._lock:
            try:
                with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=self.root, delete=False
                ) as temporary:
                    json.dump(data, temporary, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                    temporary_path = Path(temporary.name)
                os.replace(temporary_path, entry_path)
            except (OSError, TypeError, ValueError) as err:
                logger.warning("Could not persist reasoning cache entry %s: %s", entry_path, err)
                try:
                    temporary_path.unlink(missing_ok=True)
                except (OSError, UnboundLocalError):
                    pass

    def clear(self) -> int:
        removed = 0
        with self._lock:
            for path in sorted(self.root.glob("*.json")):
                try:
                    path.unlink()
                    removed += 1
                except OSError as err:
                    logger.warning("Could not clear reasoning cache entry %s: %s", path, err)
        return removed

    def statistics(self) -> dict[str, int | float]:
        requests = self._hits + self._misses
        return {
            "entries": sum(1 for path in self.root.glob("*.json") if path.is_file()),
            "hits": self._hits,
            "misses": self._misses,
            "repairs": self._repairs,
            "hit_ratio": self._hits / requests if requests else 0.0,
        }
