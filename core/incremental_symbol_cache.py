"""Per-file persistent SymbolGraph cache for incremental source indexing."""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from core.symbol_graph import SymbolGraph

logger = logging.getLogger("AutoDev.IncrementalSymbolCache")


class IncrementalSymbolCache:
    """Keeps a content-addressed symbol graph and updates only changed files."""

    VERSION = 1

    def __init__(
        self,
        project_root: Optional[Union[str, Path]] = None,
        cache_dir: Optional[Union[str, Path]] = None,
        graph: Optional[SymbolGraph] = None,
        parser: Optional[Callable[[str, str], Any]] = None,
    ) -> None:
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
        self.cache_dir = (
            Path(cache_dir).resolve()
            if cache_dir is not None
            else self.project_root / "memory" / "cache" / "symbol_graph"
        )
        self.cache_file = self.cache_dir / "symbol_graph.json"
        self.graph = graph or SymbolGraph()
        self.parser = parser
        self._pending_hashes: Dict[str, str] = {}
        self._hits = 0
        self._misses = 0
        self._updated = 0
        self._invalidated = 0
        self.loaded = False

    def load(self) -> SymbolGraph:
        """Loads and validates cached graph data, leaving the current graph on a miss."""
        if not self.cache_file.is_file():
            self._misses += 1
            self.loaded = False
            return self.graph
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Symbol graph cache root must be a JSON object.")
            graph_data = data.get("graph")
            if data.get("version") != self.VERSION or not self._valid_graph_data(graph_data):
                raise ValueError("Unsupported or malformed symbol graph cache.")
            checksum = data.get("checksum")
            if checksum is not None and checksum != self._checksum(graph_data):
                raise ValueError("Symbol graph cache checksum mismatch.")
            self.graph.import_json(json.dumps(graph_data, sort_keys=True))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as err:
            logger.warning("Ignoring invalid symbol graph cache %s: %s", self.cache_file, err)
            self._misses += 1
            self.loaded = False
            return self.graph
        self.loaded = True
        return self.graph

    def save(self) -> None:
        """Persists the graph atomically using deterministic JSON serialization."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        graph_data = {
            "file_hashes": dict(sorted(self.graph.file_hashes.items())),
            "symbols": [
                self.graph.symbols[symbol_id].to_dict()
                for symbol_id in sorted(self.graph.symbols)
            ],
            "dependencies": [
                dependency.to_dict()
                for dependency in sorted(
                    self.graph.dependencies,
                    key=lambda item: (
                        item.source_file,
                        item.target_file,
                        item.line,
                        item.raw_import_statement,
                    ),
                )
            ],
        }
        checksum = self._checksum(graph_data)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.cache_dir, delete=False
        ) as temp_file:
            json.dump(
                {"version": self.VERSION, "graph": graph_data, "checksum": checksum},
                temp_file,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            temp_path = Path(temp_file.name)
        temp_path.replace(self.cache_file)
        self.loaded = True

    @staticmethod
    def _valid_graph_data(graph_data: Any) -> bool:
        """Rejects incomplete cache payloads before importing any graph state."""
        return (
            isinstance(graph_data, dict)
            and isinstance(graph_data.get("file_hashes"), dict)
            and all(
                isinstance(path, str) and isinstance(content_hash, str)
                for path, content_hash in graph_data["file_hashes"].items()
            )
            and isinstance(graph_data.get("symbols"), list)
            and all(isinstance(symbol, dict) for symbol in graph_data["symbols"])
            and isinstance(graph_data.get("dependencies"), list)
            and all(
                isinstance(dependency, dict)
                for dependency in graph_data["dependencies"]
            )
        )

    @staticmethod
    def _checksum(graph_data: Dict[str, Any]) -> str:
        canonical_data = json.dumps(
            graph_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical_data).hexdigest()

    def has_changed(self, file: Union[str, Path]) -> bool:
        """Checks a file's current byte hash against the graph's cached hash."""
        rel_path = self._relative_path(file)
        abs_path = self._absolute_path(file)
        if not abs_path.is_file():
            self._pending_hashes.pop(rel_path, None)
            return rel_path in self.graph.file_hashes
        try:
            raw_content = abs_path.read_bytes()
        except OSError as err:
            logger.warning("Could not read %s while checking its cache hash: %s", abs_path, err)
            return True
        file_hash = hashlib.sha256(raw_content).hexdigest()
        self._pending_hashes[rel_path] = file_hash
        return self.graph.file_hashes.get(rel_path) != file_hash

    def update(self, file: Union[str, Path], force: bool = False) -> bool:
        """Rebuilds one changed file's symbols and records its current content hash."""
        rel_path = self._relative_path(file)
        abs_path = self._absolute_path(file)
        if not abs_path.is_file():
            return self.invalidate(rel_path)
        pending_hash = self._pending_hashes.get(rel_path)
        if pending_hash is None:
            self.has_changed(file)
            pending_hash = self._pending_hashes.get(rel_path)
        changed = force or self.graph.file_hashes.get(rel_path) != pending_hash
        if not changed:
            self._pending_hashes.pop(rel_path, None)
            self._hits += 1
            return False

        try:
            raw_content = abs_path.read_bytes()
        except OSError as err:
            raise OSError(f"Unable to read source file for incremental update: {abs_path}") from err
        file_hash = hashlib.sha256(raw_content).hexdigest()
        content = raw_content.decode("utf-8", errors="replace")
        self.graph.remove_file_symbols(rel_path)
        parser = self.parser
        if parser is None:
            from core.code_indexer import CodeIndexer

            from core.cache_manager import CacheManager

            indexer = CodeIndexer(
                project_root=self.project_root,
                auto_load=False,
                cache_manager=CacheManager(self.project_root / "memory" / "cache"),
            )
            indexer.graph = self.graph
            parser = lambda path, source: indexer.index_file(path, content=source)
        parser(rel_path, content)
        self.graph.file_hashes[rel_path] = file_hash
        self._pending_hashes.pop(rel_path, None)
        self._updated += 1
        self._misses += 1
        return True

    def invalidate(self, file: Union[str, Path]) -> bool:
        """Removes one file's symbols, edges, and hash from the cached graph."""
        rel_path = self._relative_path(file)
        existed = rel_path in self.graph.file_hashes or rel_path in self.graph.files
        self.graph.remove_file_symbols(rel_path)
        self._pending_hashes.pop(rel_path, None)
        if existed:
            self._invalidated += 1
        return existed

    def statistics(self) -> Dict[str, Any]:
        """Returns deterministic counts and the observed cache hit ratio."""
        total = self._hits + self._misses
        return {
            "files": len(self.graph.file_hashes),
            "symbols": len(self.graph.symbols),
            "hits": self._hits,
            "misses": self._misses,
            "updated": self._updated,
            "invalidated": self._invalidated,
            "hit_ratio": self._hits / total if total else 0.0,
        }

    def record_hits(self, count: int) -> None:
        """Records files verified unchanged by an authoritative repository snapshot."""
        if count < 0:
            raise ValueError("Cache hit count must not be negative.")
        self._hits += count

    def _relative_path(self, file: Union[str, Path]) -> str:
        path = Path(file)
        if not path.is_absolute():
            return path.as_posix().replace("\\", "/")
        try:
            return path.resolve().relative_to(self.project_root).as_posix()
        except ValueError:
            return path.as_posix().replace("\\", "/")

    def _absolute_path(self, file: Union[str, Path]) -> Path:
        path = Path(file)
        return path.resolve() if path.is_absolute() else (self.project_root / path).resolve()
