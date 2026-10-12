from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.orchestrator import Orchestrator
from core.cache_manager import CacheManager
from core.change_detector import RepositoryChangeDetector
import core.context_builder as context_builder_module
from core.context_builder import ContextBuilder
from core.doc_incremental_builder import DocIncrementalBuilder
from core.execution_scheduler import ExecutionScheduler
from core.incremental_indexer import IncrementalIndexer
from core.incremental_symbol_cache import IncrementalSymbolCache
from core.performance_profiler import PerformanceProfiler
from core.test_selector import TestSelector
from main import parse_arguments


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_change_detector_classifies_changes_and_renames(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "one.py", "def one():\n    return 1\n")
    _write(tmp_path / "tests" / "test_one.py", "def test_one():\n    assert True\n")
    _write(tmp_path / "README.md", "# Original\n")
    detector = RepositoryChangeDetector(tmp_path)
    before = detector.snapshot()

    (tmp_path / "src" / "one.py").rename(tmp_path / "src" / "renamed.py")
    _write(tmp_path / "tests" / "test_one.py", "def test_one():\n    assert False\n")
    _write(tmp_path / "docs" / "architecture.md", "# Architecture\n")
    changes = detector.detect(previous_snapshot=before)

    assert changes.renamed_files == {"src/one.py": "src/renamed.py"}
    assert changes.modified_files == ["tests/test_one.py"]
    assert changes.new_files == ["docs/architecture.md"]
    assert changes.changed_tests == ["tests/test_one.py"]
    assert changes.changed_documentation == ["docs/architecture.md"]
    assert changes.changed_files == [
        "docs/architecture.md",
        "src/one.py",
        "src/renamed.py",
        "tests/test_one.py",
    ]


def test_change_detector_recovers_from_non_object_snapshot(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "memory" / "cache" / "repository_changes" / "snapshot.json"
    _write(snapshot_path, "[]")

    detector = RepositoryChangeDetector(tmp_path)

    assert detector.load() == {}


def test_incremental_index_updates_symbols_deletions_renames_and_hits(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "one.py", "def original():\n    return 1\n")
    _write(tmp_path / "src" / "two.py", "def unchanged():\n    return 2\n")
    indexer = IncrementalIndexer(project_root=tmp_path)

    indexer.index_project()
    assert indexer.graph.find_symbol("original") is not None
    assert len(indexer.graph.file_hashes) == 2

    for _ in range(10):
        indexer.index_project()
    assert indexer.indexer.symbol_cache.statistics()["hit_ratio"] > 0.9
    assert not indexer.indexer.symbol_cache._pending_hashes

    _write(tmp_path / "src" / "one.py", "def replacement():\n    return 3\n")
    indexer.index_project()
    assert indexer.graph.find_symbol("original") is None
    assert indexer.graph.find_symbol("replacement") is not None

    (tmp_path / "src" / "two.py").unlink()
    indexer.index_project()
    assert "src/two.py" not in indexer.graph.file_hashes
    assert indexer.graph.find_symbol("unchanged") is None

    (tmp_path / "src" / "one.py").rename(tmp_path / "src" / "moved.py")
    indexer.index_project()
    assert "src/one.py" not in indexer.graph.file_hashes
    assert "src/moved.py" in indexer.graph.file_hashes
    assert indexer.graph.find_symbol("replacement") is not None

    restored = IncrementalSymbolCache(
        project_root=tmp_path,
        cache_dir=tmp_path / "memory" / "cache" / "symbol_graph",
    )
    restored.load()
    assert restored.loaded
    assert restored.graph.find_symbol("replacement") is not None
    assert restored.graph.find_symbol("unchanged") is None


def test_incremental_index_stress_warm_run_uses_snapshot_hits(tmp_path: Path) -> None:
    for index in range(250):
        _write(
            tmp_path / "src" / f"module_{index:03}.py",
            f"def function_{index}():\n    return {index}\n",
        )
    indexer = IncrementalIndexer(project_root=tmp_path)

    indexer.index_project()
    assert len(indexer.graph.file_hashes) == 250
    for _ in range(10):
        indexer.index_project()
    stats = indexer.indexer.symbol_cache.statistics()
    assert stats["hits"] == 2500
    assert stats["hit_ratio"] > 0.9


def test_symbol_cache_invalid_data_falls_back_to_a_miss(tmp_path: Path) -> None:
    cache_dir = tmp_path / "memory" / "cache" / "symbol_graph"
    cache_dir.mkdir(parents=True)
    (cache_dir / "symbol_graph.json").write_text("{invalid", encoding="utf-8")
    cache = IncrementalSymbolCache(project_root=tmp_path, cache_dir=cache_dir)

    cache.load()

    assert not cache.loaded
    assert cache.statistics()["misses"] == 1
    (cache_dir / "symbol_graph.json").write_text("[]", encoding="utf-8")
    cache.load()
    assert not cache.loaded
    assert cache.statistics()["misses"] == 2


@pytest.mark.parametrize(
    "cache_change",
    [
        lambda payload: payload.update(version=0),
        lambda payload: payload.update(version=999),
        lambda payload: payload["graph"].pop("symbols"),
        lambda payload: payload.update(checksum="invalid"),
        lambda payload: payload["graph"]["symbols"].clear(),
    ],
    ids=["old-version", "future-version", "partial", "corrupt-checksum", "truncated"],
)
def test_symbol_cache_invalid_or_partial_payload_rebuilds_from_source(
    tmp_path: Path,
    cache_change,
) -> None:
    source = tmp_path / "src" / "module.py"
    _write(source, "def cached_symbol():\n    return 1\n")
    indexer = IncrementalIndexer(project_root=tmp_path)
    indexer.index_project()

    cache_file = tmp_path / "memory" / "cache" / "symbol_graph" / "symbol_graph.json"
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    cache_change(payload)
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "memory" / "code_index.json").unlink(missing_ok=True)

    rebuilt = IncrementalIndexer(project_root=tmp_path)
    rebuilt.index_project()

    assert rebuilt.graph.find_symbol("cached_symbol") is not None
    assert rebuilt.indexer.symbol_cache.loaded
    refreshed = json.loads(cache_file.read_text(encoding="utf-8"))
    assert refreshed["checksum"] == IncrementalSymbolCache._checksum(refreshed["graph"])


def test_missing_symbol_cache_rebuilds_and_persists(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "module.py", "class Rebuilt:\n    pass\n")

    indexer = IncrementalIndexer(project_root=tmp_path)
    indexer.index_project()

    assert indexer.graph.find_symbol("Rebuilt") is not None
    assert (tmp_path / "memory" / "cache" / "symbol_graph" / "symbol_graph.json").is_file()


def test_context_cache_reuses_unchanged_content_and_invalidates_changes(tmp_path: Path) -> None:
    _write(
        tmp_path / "memory" / "project_plan.json",
        json.dumps({"project_name": "Cache Test", "phases": []}),
    )
    _write(tmp_path / "memory" / "state.json", json.dumps({"current_day": 1}))
    _write(tmp_path / "src.py", "VALUE = 1\n")
    builder = ContextBuilder(
        project_root=tmp_path,
        plan_path=tmp_path / "memory" / "project_plan.json",
        state_path=tmp_path / "memory" / "state.json",
    )

    first_tree, first_files = builder.scan_project_workspace()
    second_tree, second_files = builder.scan_project_workspace()
    assert first_tree == second_tree
    assert first_files == second_files
    assert second_files["src.py"] == "VALUE = 1\n"

    _write(tmp_path / "src.py", "VALUE = 2\n")
    _, changed_files = builder.scan_project_workspace()
    assert changed_files["src.py"] == "VALUE = 2\n"
    (tmp_path / "src.py").unlink()
    _, deleted_files = builder.scan_project_workspace()
    assert "src.py" not in deleted_files


def test_context_cache_recovers_from_non_object_payload(tmp_path: Path) -> None:
    _write(tmp_path / "src.py", "VALUE = 1\n")
    cache_dir = tmp_path / "cache"
    _write(cache_dir / "context_files.json", "[]")
    builder = ContextBuilder(project_root=tmp_path, cache_dir=cache_dir)

    _, files = builder.scan_project_workspace()

    assert files["src.py"] == "VALUE = 1\n"
    assert json.loads((cache_dir / "context_files.json").read_text(encoding="utf-8"))[
        "version"
    ] == 1


def test_context_cache_uses_snapshot_hash_for_unchanged_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(tmp_path / "src.py", "VALUE = 1\n")
    detector = RepositoryChangeDetector(tmp_path)
    detector.snapshot()
    builder = ContextBuilder(project_root=tmp_path, change_detector=detector)
    builder.scan_project_workspace()
    detector.snapshot()

    original_is_text_file = context_builder_module.is_text_file

    def reject_unchanged_source(path: Path, block_size: int = 1024) -> bool:
        if path.name == "src.py":
            raise AssertionError("Unchanged snapshot-backed file was read again.")
        return original_is_text_file(path, block_size)

    monkeypatch.setattr(context_builder_module, "is_text_file", reject_unchanged_source)
    _, files = builder.scan_project_workspace()
    assert files["src.py"] == "VALUE = 1\n"


def test_documentation_builder_preserves_unmanaged_sections(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    _write(document, "# Existing introduction\n\nKeep this text.\n")
    builder = DocIncrementalBuilder()

    assert builder.update_document(document, {"performance": "Generated performance notes."})
    first_result = document.read_text(encoding="utf-8")
    assert first_result.startswith("# Existing introduction\n\nKeep this text.\n")
    assert "Generated performance notes." in first_result
    assert not builder.update_document(document, {"performance": "Generated performance notes."})
    assert document.read_text(encoding="utf-8") == first_result
    assert builder.document_kind(document) == "readme"

    document.write_text("# External edit\n\n" + first_result, encoding="utf-8")
    assert not builder.update_document(document, {"performance": "Generated performance notes."})
    assert document.read_text(encoding="utf-8").startswith("# External edit\n")


def test_documentation_builder_changes_only_requested_managed_section(tmp_path: Path) -> None:
    document = tmp_path / "architecture.md"
    builder = DocIncrementalBuilder()
    builder.update_document(
        document,
        {"api": "API v1.", "design": "System design v1."},
    )
    before = document.read_text(encoding="utf-8")

    assert builder.update_document(
        document,
        {"api": "API v2.", "design": "System design v1."},
    )
    after = document.read_text(encoding="utf-8")
    assert "API v2." in after
    assert "System design v1." in after
    assert before.replace("API v1.", "API v2.") == after


def test_parallel_documentation_builder_updates_many_independent_documents(
    tmp_path: Path,
) -> None:
    builder = DocIncrementalBuilder(max_workers=8)
    documents = {
        tmp_path / "docs" / f"api_{index:03}.md": {"api": f"API document {index}"}
        for index in range(100)
    }

    first_result = builder.update_documents(documents)
    second_result = builder.update_documents(documents)

    assert len(first_result) == 100
    assert all(first_result.values())
    assert not any(second_result.values())


def test_documentation_builder_detects_mutated_section_mapping(tmp_path: Path) -> None:
    document = tmp_path / "architecture.md"
    sections = {"design": "System design v1."}
    builder = DocIncrementalBuilder()

    assert builder.update_document(document, sections)
    sections["design"] = "System design v2."

    assert builder.update_document(document, sections)
    assert "System design v2." in document.read_text(encoding="utf-8")


def test_test_selector_maps_utilities_and_falls_back_on_low_confidence(tmp_path: Path) -> None:
    _write(tmp_path / "tests" / "test_utils.py", "from core.utils import normalize\n")
    _write(tmp_path / "tests" / "test_parser.py", "def test_parser():\n    assert True\n")
    selector = TestSelector(project_root=tmp_path)

    selected = selector.select_tests(["core/utils.py"])
    assert selected == ["tests/test_utils.py"]
    assert not selector.last_selection.fallback_to_full_suite
    selected = selector.select_tests(
        ["core/unknown.py"],
        impact_report=SimpleNamespace(confidence=0.2, affected_tests=[]),
    )
    assert selected == ["tests/test_parser.py", "tests/test_utils.py"]
    assert selector.last_selection.fallback_to_full_suite


def test_scheduler_respects_dependencies_and_runs_independent_work_concurrently() -> None:
    scheduler = ExecutionScheduler(max_workers=2)
    barrier = threading.Barrier(2)
    completed: list[str] = []

    def independent(name: str) -> str:
        barrier.wait(timeout=2)
        completed.append(name)
        return name

    scheduler.add_task("docs", independent, args=("docs",))
    scheduler.add_task("index", independent, args=("index",))
    scheduler.add_task(
        "finish",
        lambda: completed.append("finish") or "done",
        dependencies={"docs", "index"},
    )

    result = scheduler.execute()
    assert set(completed[:2]) == {"docs", "index"}
    assert completed[2] == "finish"
    assert result == {"docs": "docs", "finish": "done", "index": "index"}


def test_scheduler_rejects_missing_dependencies_and_cycles() -> None:
    missing = ExecutionScheduler()
    missing.add_task("a", lambda: None, dependencies={"missing"})
    with pytest.raises(ValueError, match="unknown dependencies"):
        missing.execute()

    cyclic = ExecutionScheduler()
    cyclic.add_task("a", lambda: None, dependencies={"b"})
    cyclic.add_task("b", lambda: None, dependencies={"a"})
    with pytest.raises(ValueError, match="cycle"):
        cyclic.execute()


def test_scheduler_propagates_task_failure() -> None:
    scheduler = ExecutionScheduler()
    scheduler.add_task("broken", lambda: (_ for _ in ()).throw(ValueError("failure")))
    with pytest.raises(RuntimeError, match="broken") as error:
        scheduler.execute()
    assert isinstance(error.value.__cause__, ValueError)


def test_cache_manager_repairs_clears_and_reports_cache(tmp_path: Path) -> None:
    manager = CacheManager(tmp_path / "cache")
    cache_path = manager.register_cache("symbols", "1")
    _write(cache_path / "entries.json", "{}")
    manager.repair()
    assert manager.verify() == {"symbols": True}
    assert manager.stats()["caches"]["symbols"]["entry_count"] == 1

    cache_path.rename(tmp_path / "missing_cache")
    assert manager.verify() == {"symbols": False}
    assert manager.repair() == {"symbols": True}
    assert manager.verify() == {"symbols": True}
    manager.clear()
    assert list(cache_path.iterdir()) == []
    assert manager.stats()["caches"]["symbols"]["size_bytes"] == 0


def test_cache_manager_persists_metadata_across_instances(tmp_path: Path) -> None:
    manager = CacheManager(tmp_path / "cache")
    manager.register_cache("symbols", "1")
    manager.update_stats("symbols", hit=True, miss=True)

    restored = CacheManager(tmp_path / "cache")
    cache_stats = restored.stats()["caches"]["symbols"]
    assert cache_stats["hit_count"] == 1
    assert cache_stats["miss_count"] == 1
    assert cache_stats["hit_ratio"] == 0.5


def test_cache_manager_version_change_clears_stale_entries(tmp_path: Path) -> None:
    manager = CacheManager(tmp_path / "cache")
    old_path = manager.register_cache("symbols", "1")
    _write(old_path / "old.json", "{}")

    new_path = manager.register_cache("symbols", "2")

    assert new_path == old_path
    assert list(new_path.iterdir()) == []
    assert manager.stats()["caches"]["symbols"]["version"] == "2"


def test_large_repository_incremental_recovery_and_test_selection(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    test_root = tmp_path / "tests"
    for index in range(1001):
        imports = (
            f"from .module_{index - 1:04d} import function_{index - 1}\n"
            if index
            else ""
        )
        _write(
            source_root / f"module_{index:04d}.py",
            f"{imports}def function_{index}():\n    return {index}\n",
        )
    for index in range(501):
        _write(
            test_root / f"test_module_{index:04d}.py",
            f"def test_module_{index}():\n    assert True\n",
        )

    indexer = IncrementalIndexer(project_root=tmp_path)
    indexer.index_project()
    assert len(indexer.graph.file_hashes) == 1502
    assert len(indexer.graph.symbols) >= 1001
    assert len(indexer.graph.dependencies) >= 1000

    original = source_root / "module_0000.py"
    renamed = source_root / "renamed_module.py"
    original.rename(renamed)
    (source_root / "module_0001.py").unlink()
    indexer.index_project()
    assert "src/module_0000.py" not in indexer.graph.file_hashes
    assert "src/renamed_module.py" in indexer.graph.file_hashes
    assert "src/module_0001.py" not in indexer.graph.file_hashes
    assert indexer.graph.find_symbol("function_0") is not None
    assert indexer.graph.find_symbol("function_1") is None

    selector = TestSelector(project_root=tmp_path)
    selected = selector.select_tests(["src/module_0500.py"])
    assert selected
    assert len(selected) < 501


def test_performance_profiler_persists_history_and_report(tmp_path: Path) -> None:
    profiler = PerformanceProfiler(
        history_file=tmp_path / "benchmarks" / "history.json",
        report_file=tmp_path / "benchmarks" / "performance_report.json",
    )
    with profiler.profile_subsystem("indexing"):
        sum(range(100))

    report_path = profiler.save_report()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["subsystems"]["indexing"]["count"] == 1
    assert data["subsystems"]["indexing"]["mean"] >= 0
    assert data["memory_usage_bytes"]["indexing"] >= 0


def test_legacy_and_subcommand_cli_arguments_remain_supported() -> None:
    legacy = parse_arguments(["--name", "Legacy", "--days", "2"])
    assert legacy.command is None
    assert legacy.name == "Legacy"
    assert legacy.days == 2
    assert legacy.output == "memory/project_plan.json"

    subcommand = parse_arguments(["plan", "--name", "Subcommand", "--days", "3"])
    assert subcommand.command == "plan"
    assert subcommand.name == "Subcommand"
    assert subcommand.days == 3


def test_orchestrator_preserves_legacy_test_runner_signature(tmp_path: Path) -> None:
    class LegacyRunner:
        def __init__(self) -> None:
            self.project_root: Path | None = None

        def run_tests(self, project_root: Path) -> str:
            self.project_root = project_root
            return "full-suite"

    orchestrator = object.__new__(Orchestrator)
    orchestrator.project_root = tmp_path
    orchestrator.tester_agent = LegacyRunner()
    orchestrator.logger = logging.getLogger("test.orchestrator.incremental")

    assert orchestrator._run_tests(["tests/test_example.py"]) == "full-suite"
    assert orchestrator.tester_agent.project_root == tmp_path
