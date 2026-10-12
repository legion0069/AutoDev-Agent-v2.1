"""Deterministic impact-based test selection with safe full-suite fallback."""

from __future__ import annotations

import ast
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from core.change_detector import RepositoryChangeDetector

logger = logging.getLogger("AutoDev.TestSelector")


@dataclass
class TestSelection:
    """Selected tests and the deterministic reason for the chosen validation scope."""

    tests: list[str] = field(default_factory=list)
    fallback_to_full_suite: bool = False
    reason: str = ""
    confidence: Optional[float] = None


class TestSelector:
    """Selects a minimal test subset and escalates when impact confidence is low."""

    __test__ = False
    CONFIDENCE_THRESHOLD = 0.60

    def __init__(
        self,
        project_root: str | Path,
        impact_analyzer: Optional[Any] = None,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        change_detector: Optional[RepositoryChangeDetector] = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.impact_analyzer = impact_analyzer
        self.confidence_threshold = confidence_threshold
        self.change_detector = change_detector or RepositoryChangeDetector(self.project_root)
        self.all_tests = self._discover_tests()
        self.last_selection = TestSelection()

    def refresh_tests(self) -> list[str]:
        """Refreshes discovery so newly generated test files are selectable."""
        self.all_tests = self._discover_tests()
        return list(self.all_tests)

    def select_tests(
        self,
        changed_files: Iterable[str],
        affected_symbols: Optional[Iterable[str]] = None,
        impact_report: Optional[Any] = None,
    ) -> list[str]:
        """Returns the minimal deterministic list of tests for the supplied changes."""
        normalized = sorted({self._relative(path) for path in changed_files})
        if not normalized:
            self.last_selection = TestSelection(reason="No changed files.")
            return []

        reports = [impact_report] if impact_report is not None else []
        if not reports and self.impact_analyzer is not None:
            for path in normalized:
                if not RepositoryChangeDetector._is_test_file(path) and not self._is_documentation(path):
                    reports.append(self.impact_analyzer.analyze_file(path))

        confidence_values = [
            float(getattr(report, "confidence", 0.0))
            for report in reports
            if getattr(report, "confidence", None) is not None
        ]
        confidence = min(confidence_values) if confidence_values else None
        if confidence is not None and confidence < self.confidence_threshold:
            return self._select_full_suite(
                f"Impact confidence {confidence:.2f} is below the {self.confidence_threshold:.2f} threshold.",
                confidence,
            )

        changed_tests = {
            path for path in normalized
            if RepositoryChangeDetector._is_test_file(path) and path in self.all_tests
        }
        changed_code = [
            path for path in normalized
            if not self._is_documentation(path)
            and not RepositoryChangeDetector._is_test_file(path)
        ]
        if not changed_code:
            selected = sorted(changed_tests)
            self.last_selection = TestSelection(
                tests=selected,
                reason="Only test files or documentation changed.",
                confidence=confidence,
            )
            return selected

        selected = set(changed_tests)
        for report in reports:
            selected.update(
                test_path
                for test_path in getattr(report, "affected_tests", [])
                if test_path in self.all_tests
            )

        stems = {Path(path).stem.lower() for path in changed_code}
        symbols = {symbol.lower() for symbol in (affected_symbols or [])}
        parser_change = any("parser" in path.lower() or "parse" in path.lower() for path in changed_code)
        orchestrator_change = any("orchestrator" in path.lower() for path in changed_code)
        utility_change = any(
            "util" in Path(path).stem.lower()
            or Path(path).stem.lower() in {"helpers", "common"}
            for path in changed_code
        )

        for test_path in self.all_tests:
            test_name = Path(test_path).stem.lower()
            if any(f"test_{stem}" in test_name or f"{stem}_test" in test_name for stem in stems):
                selected.add(test_path)
            if parser_change and any(token in test_name for token in ("parser", "parse")):
                selected.add(test_path)
            if orchestrator_change and (
                "orchestrat" in test_name or "integration" in test_name or "scenario" in test_name
            ):
                selected.add(test_path)
            if utility_change and any(token in test_name for token in ("util", "helper", "common")):
                selected.add(test_path)
            if symbols and self._test_references_symbols(test_path, symbols):
                selected.add(test_path)

        for path in changed_code:
            if path.startswith("core/"):
                module_path = Path(path).with_suffix("").as_posix().replace("/", ".")
                module_name = Path(path).stem
                for test_path in self.all_tests:
                    if self._test_imports_module(test_path, module_path, module_name):
                        selected.add(test_path)

        if selected:
            result = sorted(selected)
            self.last_selection = TestSelection(
                tests=result,
                reason="Selected tests matching changed modules, imports, and impact results.",
                confidence=confidence,
            )
            return result

        if confidence is None or confidence < self.confidence_threshold:
            return self._select_full_suite(
                "No reliable dependency mapping was found for changed source files.",
                confidence,
            )

        return self._select_full_suite(
            "No matching tests were found; running the full suite is safer.",
            confidence,
        )

    def select(self, *args: Any, **kwargs: Any) -> TestSelection:
        """Returns selection details while keeping :meth:`select_tests` list-shaped."""
        self.select_tests(*args, **kwargs)
        return self.last_selection

    def _select_full_suite(self, reason: str, confidence: Optional[float]) -> list[str]:
        selected = list(self.all_tests)
        self.last_selection = TestSelection(
            tests=selected,
            fallback_to_full_suite=True,
            reason=reason,
            confidence=confidence,
        )
        logger.info("%s Selected %d tests.", reason, len(selected))
        return selected

    def _discover_tests(self) -> list[str]:
        tests: list[str] = []
        tests_dir = self.project_root / "tests"
        if not tests_dir.is_dir():
            return tests
        for current_root, directories, files in os.walk(tests_dir):
            directories[:] = sorted(d for d in directories if not d.startswith("."))
            for file_name in sorted(files):
                if file_name.startswith("test_") and file_name.endswith(".py"):
                    tests.append(
                        (Path(current_root) / file_name)
                        .relative_to(self.project_root)
                        .as_posix()
                    )
                elif file_name.endswith("_test.py"):
                    tests.append(
                        (Path(current_root) / file_name)
                        .relative_to(self.project_root)
                        .as_posix()
                    )
        return sorted(set(tests))

    def _test_imports_module(
        self,
        test_path: str,
        module_path: str,
        module_name: str,
    ) -> bool:
        file_path = self.project_root / test_path
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        except (OSError, SyntaxError, UnicodeError):
            return False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(
                    alias.name == module_path or module_name in alias.name.split(".")
                    for alias in node.names
                ):
                    return True
            elif isinstance(node, ast.ImportFrom):
                if node.module and (
                    node.module == module_path or module_name in node.module.split(".")
                ):
                    return True
        return False

    def _test_references_symbols(self, test_path: str, symbols: set[str]) -> bool:
        try:
            content = (self.project_root / test_path).read_text(
                encoding="utf-8",
                errors="replace",
            ).lower()
        except OSError as err:
            logger.warning("Could not inspect test file %s: %s", test_path, err)
            return False
        return any(symbol and symbol in content for symbol in symbols)

    def _relative(self, path: str) -> str:
        file_path = Path(path)
        if file_path.is_absolute():
            try:
                file_path = file_path.resolve().relative_to(self.project_root)
            except ValueError:
                return file_path.as_posix()
        return file_path.as_posix().replace("\\", "/")

    def _is_documentation(self, path: str) -> bool:
        return self.change_detector._is_documentation_file(path)
