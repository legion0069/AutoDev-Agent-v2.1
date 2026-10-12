"""
cache_manager.py - Unified Cache Management Subsystem for AutoDev (v3.6.1)

Provides a centralized interface for managing, validating, cleaning, and
tracking statistics for all persistent caches in the system.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger("AutoDev.CacheManager")

@dataclass
class CacheMetadata:
    """Metadata for a single cache entry or subsystem."""
    name: str
    path: Path
    version: str
    created_at: float
    last_accessed: float
    size_bytes: int
    entry_count: int
    hit_count: int = 0
    miss_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "version": self.version,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "size_bytes": self.size_bytes,
            "entry_count": self.entry_count,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "hit_ratio": self.hit_count / (self.hit_count + self.miss_count) if (self.hit_count + self.miss_count) > 0 else 0.0
        }

class CacheManager:
    """
    Centralized manager for all AutoDev caches.
    Ensures version consistency, provides cleanup routines, and tracks performance.
    """

    CACHE_ROOT = Path("memory/cache")
    METADATA_FILE = CACHE_ROOT / "cache_metadata.json"
    VERSION = "1"

    def __init__(self, cache_root: Optional[Union[str, Path]] = None) -> None:
        self.cache_root = Path(cache_root).resolve() if cache_root else self.CACHE_ROOT.resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.cache_root / "cache_metadata.json"
        self.metadata: Dict[str, CacheMetadata] = {}
        self._lock = threading.RLock()
        self._load_metadata()
        self.repair()

    def _load_metadata(self) -> None:
        if self.metadata_file.exists():
            try:
                data = json.loads(self.metadata_file.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Cache metadata must be a JSON object.")
                for name, mdata in data.items():
                    if not isinstance(mdata, dict):
                        raise ValueError(f"Invalid metadata entry for cache {name!r}.")
                    mdata.pop("hit_ratio", None)
                    mdata["path"] = Path(mdata["path"])
                    self.metadata[name] = CacheMetadata(**mdata)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as err:
                logger.warning("Failed to load cache metadata from %s: %s", self.metadata_file, err)
                self.metadata = {}

    def _save_metadata(self) -> None:
        with self._lock:
            data = {name: m.to_dict() for name, m in self.metadata.items()}
            self.cache_root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.cache_root, delete=False
            ) as temp_file:
                json.dump(data, temp_file, indent=2, sort_keys=True)
                temp_path = Path(temp_file.name)
            temp_path.replace(self.metadata_file)

    def register_cache(self, name: str, version: str) -> Path:
        """Registers or retrieves a cache directory."""
        cache_name = Path(name)
        if not name or cache_name.is_absolute() or ".." in cache_name.parts:
            raise ValueError("Cache name must be a non-empty relative path within the cache root.")
        cache_path = self.cache_root / name
        cache_path.resolve().relative_to(self.cache_root)

        with self._lock:
            if name not in self.metadata or self.metadata[name].version != version:
                if name in self.metadata:
                    logger.info("Cache version mismatch for %s. Clearing old cache.", name)
                    self.clear_cache(name)

                now = time.time()
                self.metadata[name] = CacheMetadata(
                    name=name,
                    path=cache_path,
                    version=version,
                    created_at=now,
                    last_accessed=now,
                    size_bytes=0,
                    entry_count=0,
                )
                cache_path.mkdir(parents=True, exist_ok=True)
                self._save_metadata()
            else:
                cache_path.mkdir(parents=True, exist_ok=True)

        return cache_path

    def update_stats(
        self,
        name: str,
        size_bytes: Optional[int] = None,
        entry_count: Optional[int] = None,
        hit: bool = False,
        miss: bool = False,
    ) -> None:
        """Updates statistics for a registered cache."""
        with self._lock:
            if name not in self.metadata:
                return

            metadata = self.metadata[name]
            metadata.last_accessed = time.time()
            if size_bytes is not None:
                metadata.size_bytes = size_bytes
            if entry_count is not None:
                metadata.entry_count = entry_count
            if hit:
                metadata.hit_count += 1
            if miss:
                metadata.miss_count += 1
            self._save_metadata()

    def get_stats(self) -> Dict[str, Any]:
        """Returns statistics for all registered caches."""
        with self._lock:
            total_size = sum(metadata.size_bytes for metadata in self.metadata.values())
            return {
                "total_size_bytes": total_size,
                "cache_count": len(self.metadata),
                "caches": {
                    name: self.metadata[name].to_dict()
                    for name in sorted(self.metadata)
                },
            }

    def clear_cache(self, name: str) -> bool:
        """Clears a specific cache by name."""
        with self._lock:
            metadata = self.metadata.get(name)
            if metadata is None:
                return False
            cache_path = metadata.path.resolve()
            cache_path.relative_to(self.cache_root)
            if cache_path == self.cache_root:
                raise ValueError("Refusing to clear the cache root itself.")
            if cache_path.exists():
                shutil.rmtree(cache_path)
            cache_path.mkdir(parents=True, exist_ok=True)
            metadata.size_bytes = 0
            metadata.entry_count = 0
            metadata.hit_count = 0
            metadata.miss_count = 0
            metadata.last_accessed = time.time()
            self._save_metadata()
            return True

    def clear(self, name: Optional[str] = None) -> None:
        """Clears one registered cache, or all registered caches when omitted."""
        if name is not None:
            self.clear_cache(name)
            return
        for cache_name in sorted(self.metadata):
            self.clear_cache(cache_name)

    def clear_all(self) -> None:
        """Clears all registered caches."""
        self.clear()

    def cleanup(self, max_age_seconds: float) -> list[str]:
        """Clears caches that have not been accessed within the supplied duration."""
        if max_age_seconds < 0:
            raise ValueError("max_age_seconds must not be negative.")
        now = time.time()
        expired = sorted(
            name
            for name, metadata in self.metadata.items()
            if now - metadata.last_accessed > max_age_seconds
        )
        for name in expired:
            self.clear_cache(name)
        return expired

    def validate_cache(self, name: str, max_age_seconds: Optional[int] = None) -> bool:
        """Validates if a cache is still valid based on age or other criteria."""
        with self._lock:
            metadata = self.metadata.get(name)
            if metadata is None or not metadata.path.is_dir():
                return False
            if max_age_seconds is not None and max_age_seconds >= 0:
                if time.time() - metadata.last_accessed > max_age_seconds:
                    logger.info("Cache %s expired.", name)
                    return False
            return True

    def get_cache_path(self, name: str) -> Optional[Path]:
        """Returns the path for a registered cache."""
        return self.metadata[name].path if name in self.metadata else None

    def verify(self) -> Dict[str, bool]:
        """Checks that registered cache paths exist and stay inside the cache root."""
        results: Dict[str, bool] = {}
        with self._lock:
            for name, metadata in sorted(self.metadata.items()):
                try:
                    metadata.path.resolve().relative_to(self.cache_root)
                    results[name] = metadata.path.is_dir()
                except ValueError:
                    results[name] = False
        return results

    def repair(self) -> Dict[str, bool]:
        """Repairs missing cache directories and recomputes their disk statistics."""
        repaired: Dict[str, bool] = {}
        with self._lock:
            for name, metadata in sorted(self.metadata.items()):
                try:
                    cache_path = metadata.path.resolve()
                    cache_path.relative_to(self.cache_root)
                    if cache_path == self.cache_root:
                        raise ValueError("Cache path cannot be the cache root.")
                    existed = cache_path.is_dir()
                    cache_path.mkdir(parents=True, exist_ok=True)
                    size_bytes = 0
                    entry_count = 0
                    for path in cache_path.rglob("*"):
                        if path.is_file():
                            try:
                                size_bytes += path.stat().st_size
                                entry_count += 1
                            except OSError as err:
                                logger.warning("Could not stat cache entry %s: %s", path, err)
                    metadata.path = cache_path
                    metadata.size_bytes = size_bytes
                    metadata.entry_count = entry_count
                    repaired[name] = not existed
                except (OSError, ValueError) as err:
                    logger.error("Could not repair cache %s: %s", name, err)
                    repaired[name] = False
            if repaired:
                self._save_metadata()
        return repaired

    def stats(self) -> Dict[str, Any]:
        """Public alias for :meth:`get_stats`."""
        return self.get_stats()
