"""Public incremental indexing facade backed by CodeIndexer and its hash cache."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from core.cache_manager import CacheManager
from core.change_detector import ChangeSet, RepositoryChangeDetector
from core.code_indexer import CodeIndexer
from core.symbol_graph import SymbolGraph


class IncrementalIndexer:
    """Indexes changed source files while preserving the CodeIndexer public API."""

    VERSION = "3.6.1"

    def __init__(
        self,
        project_root: Optional[Union[str, Path]] = None,
        indexer: Optional[CodeIndexer] = None,
        output_path: Optional[Union[str, Path]] = None,
        change_detector: Optional[RepositoryChangeDetector] = None,
        cache_manager: Optional[CacheManager] = None,
    ) -> None:
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
        self.cache_manager = cache_manager or CacheManager(
            self.project_root / "memory" / "cache"
        )
        self.cache_path = self.cache_manager.register_cache("code_index", self.VERSION)
        self.change_detector = change_detector or RepositoryChangeDetector(self.project_root)
        self.indexer = indexer or CodeIndexer(
            project_root=self.project_root,
            output_path=output_path or self.project_root / "memory" / "code_index.json",
            cache_manager=self.cache_manager,
        )
        self.last_changed_files: list[str] = []
        self.last_deleted_files: list[str] = []
        self.last_changes = ChangeSet()

    @property
    def graph(self) -> SymbolGraph:
        return self.indexer.graph

    def index_project(
        self,
        force_reindex: bool = False,
        parallel: bool = True,
        changes: Optional[ChangeSet] = None,
    ) -> SymbolGraph:
        """Runs a content-hash incremental index and reports changed file paths."""
        self.last_changes = changes or self.change_detector.detect()
        symbol_cache = getattr(self.indexer, "symbol_cache", None)
        if (
            not force_reindex
            and getattr(symbol_cache, "loaded", False)
            and callable(getattr(self.indexer, "update_files", None))
        ):
            graph = self.indexer.update_files(self.last_changes.changed_files)
            if (
                not self.last_changes.changed_files
                and callable(getattr(symbol_cache, "record_hits", None))
            ):
                symbol_cache.record_hits(len(self.indexer.graph.file_hashes))
        else:
            graph = self.indexer.index_project(
                force_reindex=force_reindex,
                parallel=parallel,
            )
        self.change_detector.save(self.last_changes.current_snapshot)
        self.last_changed_files = list(getattr(self.indexer, "last_changed_files", []))
        self.last_deleted_files = list(getattr(self.indexer, "last_deleted_files", []))
        return graph

    def get_graph(self) -> SymbolGraph:
        return self.indexer.get_graph()

    def update_files(self, files: list[str | Path]) -> SymbolGraph:
        """Updates only explicitly changed source paths, without walking the repository."""
        graph = self.indexer.update_files(files)
        self.last_changed_files = list(getattr(self.indexer, "last_changed_files", []))
        self.last_deleted_files = list(getattr(self.indexer, "last_deleted_files", []))
        return graph

    def statistics(self):
        return self.indexer.statistics()
