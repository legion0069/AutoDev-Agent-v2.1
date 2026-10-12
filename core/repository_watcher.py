"""
repository_watcher.py - Repository Watch Mode for AutoDev (v3.6.1)

Watches the filesystem for changes and automatically triggers indexing,
caching, and incremental test execution.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union

from core.code_indexer import CodeIndexer
from core.incremental_test_runner import IncrementalTestRunner

logger = logging.getLogger("AutoDev.RepositoryWatcher")

class RepositoryWatcher:
    """
    Monitors a project directory for changes using standard library only.
    """

    def __init__(
        self,
        project_root: Optional[Union[str, Path]] = None,
        on_change: Optional[Callable[[List[str]], None]] = None,
        interval: float = 1.0
    ) -> None:
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd()
        self.on_change = on_change
        self.interval = max(interval, 1.0)
        self.indexer = CodeIndexer(project_root=self.project_root)
        self.test_runner = IncrementalTestRunner(project_root=self.project_root, indexer=self.indexer)
        
        self.last_snapshot: Dict[str, float] = self._take_snapshot()

    def _take_snapshot(self) -> Dict[str, float]:
        """Takes a snapshot of file mtimes in the project."""
        snapshot = {}
        for root, dirs, files in os.walk(self.project_root):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if d not in self.indexer.IGNORE_DIRS and not d.startswith(".")]
            
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in self.indexer.SUPPORTED_EXTENSIONS:
                    abs_path = Path(root) / f
                    try:
                        snapshot[str(abs_path)] = abs_path.stat().st_mtime
                    except OSError:
                        pass
        return snapshot

    def _get_changes(self) -> List[str]:
        """Compares current state with last snapshot to find changes."""
        current_snapshot = self._take_snapshot()
        changed_files = []
        
        # Check for modifications and new files
        for path, mtime in current_snapshot.items():
            if path not in self.last_snapshot or mtime > self.last_snapshot[path]:
                changed_files.append(path)
        
        # Check for deletions
        for path in self.last_snapshot:
            if path not in current_snapshot:
                changed_files.append(path)
                
        self.last_snapshot = current_snapshot
        return changed_files

    def start(self) -> None:
        """Starts the watch loop."""
        logger.info(f"Starting repository watch on {self.project_root} (interval: {self.interval}s)")
        print(f"[*] AutoDev Watch Mode Active: Monitoring {self.project_root}...")
        
        try:
            while True:
                time.sleep(self.interval)
                changes = self._get_changes()
                
                if changes:
                    rel_changes = [str(Path(f).relative_to(self.project_root)) for f in changes if Path(f).is_absolute()]
                    # Also include those that are already relative or handled differently
                    rel_changes.extend([f for f in changes if not Path(f).is_absolute()])
                    
                    logger.info(f"Detected changes in {len(rel_changes)} files: {rel_changes[:3]}...")
                    print(f"\n[*] Change detected: {', '.join(rel_changes[:2])}{'...' if len(rel_changes) > 2 else ''}")
                    
                    # 1. Update Index
                    print("[*] Updating symbol graph...")
                    self.indexer.index_project()
                    
                    # 2. Run Affected Tests
                    print("[*] Running affected tests...")
                    report = self.test_runner.run_tests()
                    
                    if report.executed_tests:
                        status = "PASSED" if report.failed_count == 0 else "FAILED"
                        print(f"[*] Tests {status}: {report.passed_count} passed, {report.failed_count} failed in {report.duration:.2f}s")
                    else:
                        print("[*] No affected tests to run.")
                        
                    if self.on_change:
                        self.on_change(rel_changes)
                        
        except KeyboardInterrupt:
            print("\n[*] Watch mode stopped.")
        except Exception as e:
            logger.error(f"Error in watch loop: {e}", exc_info=True)
            print(f"\n[!] Watch mode error: {e}")
