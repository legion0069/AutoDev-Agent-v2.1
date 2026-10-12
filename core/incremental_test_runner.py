"""
incremental_test_runner.py - Incremental Test Runner for AutoDev (v3.6.1)

Optimizes test execution by identifying and running only tests affected by recent changes.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from core.code_indexer import CodeIndexer
from core.change_detector import RepositoryChangeDetector
from core.impact_analyzer import ImpactAnalyzer
from core.symbol_graph import SymbolGraph
from core.test_selector import TestSelector

logger = logging.getLogger("AutoDev.IncrementalTestRunner")

@dataclass
class IncrementalTestReport:
    """Report for an incremental test run."""
    affected_tests: List[str]
    executed_tests: List[str]
    skipped_tests: List[str]
    duration: float
    success_rate: float
    passed_count: int
    failed_count: int
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "affected_tests": self.affected_tests,
            "executed_tests": self.executed_tests,
            "skipped_tests": self.skipped_tests,
            "duration": round(self.duration, 4),
            "success_rate": round(self.success_rate, 2),
            "passed_count": self.passed_count,
            "failed_count": self.failed_count
        }

class IncrementalTestRunner:
    """
    Identifies and executes tests affected by code changes.
    """

    def __init__(
        self,
        project_root: Optional[Union[str, Path]] = None,
        indexer: Optional[CodeIndexer] = None,
        impact_analyzer: Optional[ImpactAnalyzer] = None
    ) -> None:
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd()
        self.indexer = indexer or CodeIndexer(project_root=self.project_root)
        self.impact_analyzer = impact_analyzer or ImpactAnalyzer(symbol_graph=self.indexer.graph)
        self.change_detector = RepositoryChangeDetector(self.project_root)
        self.test_selector = TestSelector(
            project_root=self.project_root,
            impact_analyzer=self.impact_analyzer,
        )

    def get_modified_files(self) -> List[str]:
        """Uses git diff to find modified files in the workspace."""
        try:
            # Get changed files (modified, added, but not deleted)
            cmd = ["git", "diff", "--name-only", "HEAD"]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
            if result.returncode != 0:
                logger.warning(f"Git diff failed: {result.stderr}")
                return []
            
            files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
            
            # Also get untracked files
            cmd = ["git", "ls-files", "--others", "--exclude-standard"]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
            if result.returncode == 0:
                files.extend([f.strip() for f in result.stdout.splitlines() if f.strip()])
                
            return sorted(set(files))
        except (OSError, subprocess.SubprocessError) as err:
            logger.error("Failed to get modified files via git: %s", err)
            return []

    def find_affected_tests(self, modified_files: List[str]) -> Set[str]:
        """Determines which tests are affected by the given modified files."""
        affected_tests = set()
        
        # Ensure index is up to date
        changes = self.change_detector.detect()
        symbol_cache = getattr(self.indexer, "symbol_cache", None)
        if (
            getattr(symbol_cache, "loaded", False)
            and callable(getattr(self.indexer, "update_files", None))
        ):
            self.indexer.update_files(changes.changed_files)
        else:
            self.indexer.index_project()
        self.change_detector.save(changes.current_snapshot)
        self.impact_analyzer.graph = self.indexer.graph
        self.test_selector.refresh_tests()

        affected_tests.update(
            self.test_selector.select_tests(
                changed_files=modified_files,
            )
        )
        return affected_tests

    def run_tests(self, test_files: Optional[List[str]] = None) -> IncrementalTestReport:
        """
        Runs the specified tests (or affected tests if None) and returns a report.
        """
        start_time = time.perf_counter()
        
        if test_files is None:
            modified = self.get_modified_files()
            if not modified:
                logger.info("No modified files detected. Skipping incremental tests.")
                return IncrementalTestReport([], [], [], 0.0, 1.0, 0, 0)
            
            test_files = sorted(self.find_affected_tests(modified))
            
            if not test_files:
                logger.info("No affected tests found for modified files. Falling back to full suite?")
                # Fallback to full suite or skip? Requirement says: "If no dependency can be determined, fallback to full suite."
                # But running the FULL suite might be too much. 
                # Let's see if we have any tests at all.
                test_files = self._get_all_tests()

        test_files = sorted(set(test_files))
        executed_tests = []
        passed_count = 0
        failed_count = 0
        all_stdout = ""
        all_stderr = ""
        
        if not test_files:
            return IncrementalTestReport([], [], [], 0.0, 1.0, 0, 0)

        logger.info(f"Executing {len(test_files)} tests...")
        
        # In a real system, we'd use pytest.
        # For simplicity and to stay within stdlib/existing dependencies:
        try:
            cmd = [sys.executable, "-m", "pytest"] + sorted(test_files) + ["-v"]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
            
            all_stdout = result.stdout
            all_stderr = result.stderr
            
            executed_tests = test_files
            
            # Parse pytest output for counts (simplified)
            # Example: "1 passed, 1 failed in 0.05s"
            if "failed" in result.stdout or result.returncode != 0:
                # We should really parse the output, but let's assume if it failed, it's failed.
                # A better implementation would parse the result JSON if using --json-report
                pass
            
            # Dummy parsing for now to fulfill the report structure
            # Real implementation would use pytest-json-report or similar if available.
            import re
            match = re.search(r"(\d+) passed", result.stdout)
            if match:
                passed_count = int(match.group(1))
            match = re.search(r"(\d+) failed", result.stdout)
            if match:
                failed_count = int(match.group(1))
            
            if passed_count == 0 and failed_count == 0:
                if result.returncode == 0:
                    passed_count = len(test_files) # Fallback if parsing fails
                else:
                    failed_count = len(test_files)

        except (OSError, subprocess.SubprocessError) as err:
            logger.error("Test execution failed: %s", err)
            all_stderr += f"\nInternal Error: {err}"
            failed_count = len(test_files)

        duration = time.perf_counter() - start_time
        success_rate = passed_count / (passed_count + failed_count) if (passed_count + failed_count) > 0 else 0.0
        
        all_tests = self._get_all_tests()
        skipped_tests = [t for t in all_tests if t not in executed_tests]

        return IncrementalTestReport(
            affected_tests=test_files,
            executed_tests=executed_tests,
            skipped_tests=skipped_tests,
            duration=duration,
            success_rate=success_rate,
            passed_count=passed_count,
            failed_count=failed_count,
            stdout=all_stdout,
            stderr=all_stderr
        )

    def _get_all_tests(self) -> List[str]:
        """Discovers all test files in the project."""
        all_tests = []
        for root, directories, files in os.walk(self.project_root / "tests"):
            directories.sort()
            for f in sorted(files):
                if f.endswith(".py") and (f.startswith("test_") or f.endswith("_test.py")):
                    rel_path = str(Path(root) / f).replace(str(self.project_root), "").lstrip("/")
                    all_tests.append(rel_path)
        return sorted(all_tests)
