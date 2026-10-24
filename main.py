"""
main.py - AutoDev CLI Interface (Version 1)

Autonomous AI Software Development Agent - Phase 1 Planning Tool.
Interactively collects project requirements and outputs a day-by-day
structured development plan saved to memory/project_plan.json.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from agents.planner_agent import generate_project_plan, save_project_plan


def print_banner() -> None:
    """Prints a friendly ASCII banner for AutoDev."""
    banner = """
============================================================
              AutoDev - AI Software Agent (v1)              
          Autonomous Project Planning & Phasing Tool        
============================================================
"""
    print(banner)


def prompt_for_input(prompt_text: str, default: Optional[str] = None) -> str:
    """
    Prompts the user for a non-empty string input, with optional default.
    """
    while True:
        if default:
            display_prompt = f"{prompt_text} [{default}]: "
        else:
            display_prompt = f"{prompt_text}: "

        try:
            val = input(display_prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nOperation cancelled by user.")
            sys.exit(0)

        if not val and default:
            return default
        if val:
            return val

        print("  [!] Input cannot be empty. Please enter a value.")


def prompt_for_days(prompt_text: str, default: int = 5) -> int:
    """
    Prompts the user for a positive integer representing development days.
    """
    while True:
        display_prompt = f"{prompt_text} [{default}]: "
        try:
            val = input(display_prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nOperation cancelled by user.")
            sys.exit(0)

        if not val:
            return default

        try:
            days = int(val)
            if days > 0:
                return days
            print("  [!] Please enter a positive number of days (at least 1).")
        except ValueError:
            print("  [!] Invalid number. Please enter an integer.")


def display_plan_summary(plan: dict, output_path: Path) -> None:
    """Displays a clean terminal summary of the generated development plan."""
    print("\n" + "=" * 60)
    print("                 GENERATED PROJECT PLAN")
    print("=" * 60)
    print(f"Project Name   : {plan['project_name']}")
    print(f"Description    : {plan['project_description']}")
    print(f"Tech Stack     : {plan['technology_stack']}")
    print(f"Total Duration : {plan['total_days']} day(s)")
    print(f"Saved To       : {output_path.resolve()}")
    print("-" * 60)

    for phase in plan["phases"]:
        day = phase["day"]
        name = phase["phase_name"]
        print(f"\n[ Day {day} ] -> {name}")
        print("  Goals:")
        for g in phase.get("goals", []):
            print(f"    - {g}")
        print("  Tasks:")
        for t in phase.get("tasks", []):
            print(f"    * {t}")
        print("  Deliverables:")
        for d in phase.get("deliverables", []):
            print(f"    + {d}")
        print(f"  Testing Focus  : {phase.get('testing_focus', 'N/A')}")
        print(f"  Git Commit Msg : \"{phase.get('git_commit_message', '')}\"")

    print("\n" + "=" * 60)
    print(f"[OK] Project plan successfully saved to '{output_path.name}'.")
    print("=" * 60 + "\n")


import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from agents.planner_agent import generate_project_plan, save_project_plan
from core.cache_manager import CacheManager
from core.incremental_indexer import IncrementalIndexer
from core.incremental_test_runner import IncrementalTestRunner
from core.performance_profiler import PerformanceProfiler
from core.repository_watcher import RepositoryWatcher

VERSION = "6.0"

def print_banner() -> None:
    """Prints a friendly ASCII banner for AutoDev."""
    banner = f"""
============================================================
           AutoDev - AI Software Agent (v{VERSION})
       Performance & Developer Experience Optimized
============================================================
"""
    print(banner)

def prompt_for_input(prompt_text: str, default: Optional[str] = None) -> str:
    """Prompts for a non-empty string, optionally accepting a default."""
    while True:
        display_prompt = f"{prompt_text} [{default}]: " if default else f"{prompt_text}: "
        try:
            value = input(display_prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nOperation cancelled by user.")
            raise SystemExit(0)
        if value:
            return value
        if default:
            return default
        print("  [!] Input cannot be empty. Please enter a value.")


def prompt_for_days(prompt_text: str, default: int = 5) -> int:
    """Prompts for a positive integer representing development days."""
    while True:
        try:
            value = input(f"{prompt_text} [{default}]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nOperation cancelled by user.")
            raise SystemExit(0)
        if not value:
            return default
        try:
            days = int(value)
        except ValueError:
            print("  [!] Invalid number. Please enter an integer.")
            continue
        if days > 0:
            return days
        print("  [!] Please enter a positive number of days (at least 1).")


def display_plan_summary(plan: dict, output_path: Path) -> None:
    """Displays a clean terminal summary of the generated development plan."""
    print("\n" + "=" * 60)
    print("                 GENERATED PROJECT PLAN")
    print("=" * 60)
    print(f"Project Name   : {plan['project_name']}")
    print(f"Description    : {plan['project_description']}")
    print(f"Tech Stack     : {plan['technology_stack']}")
    print(f"GitHub Repo    : {plan.get('github_repository') or 'Not provided'}")
    print(f"Execution Mode : {plan.get('execution_mode', 'Autonomous')}")
    print(f"Total Duration : {plan['total_days']} day(s)")
    print(f"Saved To       : {output_path.resolve()}")
    print("-" * 60)
    for phase in plan["phases"]:
        print(f"\n[ Day {phase['day']} ] -> {phase['phase_name']}")
        print("  Goals:")
        for goal in phase.get("goals", []):
            print(f"    - {goal}")
        print("  Tasks:")
        for task in phase.get("tasks", []):
            print(f"    * {task}")
        print("  Deliverables:")
        for deliverable in phase.get("deliverables", []):
            print(f"    + {deliverable}")
        print(f"  Testing Focus  : {phase.get('testing_focus', 'N/A')}")
        print(f"  Git Commit Msg : \"{phase.get('git_commit_message', '')}\"")
    print("\n" + "=" * 60)
    print(f"[OK] Project plan successfully saved to '{output_path.name}'.")
    print("=" * 60 + "\n")

def handle_plan(args):
    """Handles the planning subcommand."""
    project_name = args.name or prompt_for_input("1. Enter Project Name")
    project_desc = args.desc or prompt_for_input("2. Enter Project Description")
    tech_stack = args.stack or prompt_for_input("3. Enter Technology Stack")
    days = args.days if args.days is not None else prompt_for_days("4. Enter Number of Development Days", default=5)
    repo = getattr(args, "repo", None) or prompt_for_input("5. Enter GitHub Repository URL", default="")
    mode = getattr(args, "mode", None) or prompt_for_input("6. Select Execution Mode", default="Autonomous")

    print("\n[*] Synthesizing structured development phases...")
    try:
        plan = generate_project_plan(
            project_name=project_name,
            project_description=project_desc,
            tech_stack=tech_stack,
            days=days,
            github_repository=repo,
            execution_mode=mode,
        )
        output_path = save_project_plan(plan, filepath=args.output)
        display_plan_summary(plan, output_path)
    except Exception as err:
        print(f"\n[!] Error generating plan: {err}", file=sys.stderr)
        raise SystemExit(1) from err

def handle_benchmark(args):
    """Handles the benchmark subcommand."""
    print("[*] Running performance benchmarks...")
    profiler = PerformanceProfiler()
    indexer = IncrementalIndexer()
    profiler.cache_manager = indexer.cache_manager

    with profiler.profile_subsystem("Indexing"):
        indexer.index_project(force_reindex=True)

    with profiler.profile_subsystem("Warm_Indexing"):
        indexer.index_project()

    report = profiler.generate_report()
    profiler.save_report()
    print(json.dumps(report.to_dict(), indent=2))

def handle_watch(args):
    """Handles the watch subcommand."""
    watcher = RepositoryWatcher(interval=args.interval)
    watcher.start()

def handle_cache(args):
    """Handles the cache subcommand."""
    manager = CacheManager()
    if args.cache_cmd == "stats":
        stats = manager.get_stats()
        print(json.dumps(stats, indent=2))
    elif args.cache_cmd == "clean":
        manager.clear_all()
        print("[OK] All caches cleared.")

def handle_test(args):
    """Handles the test subcommand."""
    if args.test_cmd == "incremental":
        runner = IncrementalTestRunner()
        report = runner.run_tests()
        print(json.dumps(report.to_dict(), indent=2))

def handle_profile(args):
    """Handles the profile subcommand."""
    profiler = PerformanceProfiler()
    report = profiler.generate_report()
    print(json.dumps(report.to_dict(), indent=2))

def parse_arguments(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parses legacy plan options and the newer developer-experience commands."""
    parser = argparse.ArgumentParser(
        description=f"AutoDev (v{VERSION}) - Autonomous AI Software Engineering Planner"
    )
    parser.add_argument("--name", "-n", type=str, help="Project name")
    parser.add_argument("--desc", "-d", type=str, help="Project description")
    parser.add_argument(
        "--stack", "-s", type=str,
        help="Technology stack (e.g. 'Python, FastAPI, SQLite')",
    )
    parser.add_argument("--days", "-t", type=int, help="Number of development days")
    parser.add_argument("--repo", "--github-repository", type=str, help="GitHub repository URL")
    parser.add_argument("--mode", "--execution-mode", type=str, help="Execution mode (Autonomous or Approval)")
    parser.add_argument(
        "--output", "-o", type=str, default="memory/project_plan.json",
        help="Output JSON file path (default: memory/project_plan.json)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    plan_parser = subparsers.add_parser("plan", help="Generate a project plan")
    plan_parser.add_argument("--name", "-n", type=str, default=argparse.SUPPRESS)
    plan_parser.add_argument("--desc", "-d", type=str, default=argparse.SUPPRESS)
    plan_parser.add_argument("--stack", "-s", type=str, default=argparse.SUPPRESS)
    plan_parser.add_argument("--days", "-t", type=int, default=argparse.SUPPRESS)
    plan_parser.add_argument("--repo", "--github-repository", type=str, default=argparse.SUPPRESS)
    plan_parser.add_argument("--mode", "--execution-mode", type=str, default=argparse.SUPPRESS)
    plan_parser.add_argument("--output", "-o", type=str, default=argparse.SUPPRESS)

    # Benchmark
    subparsers.add_parser("benchmark", help="Run performance benchmarks")

    # Watch
    watch_parser = subparsers.add_parser("watch", help="Watch for changes and auto-index/test")
    watch_parser.add_argument("--interval", "-i", type=float, default=1.0)

    # Cache
    cache_parser = subparsers.add_parser("cache", help="Manage caches")
    cache_subparsers = cache_parser.add_subparsers(dest="cache_cmd")
    cache_subparsers.add_parser("stats", help="Show cache statistics")
    cache_subparsers.add_parser("clean", help="Clear all caches")

    # Test
    test_parser = subparsers.add_parser("test", help="Run tests")
    test_subparsers = test_parser.add_subparsers(dest="test_cmd")
    test_subparsers.add_parser("incremental", help="Run only affected tests")

    # Profile
    subparsers.add_parser("profile", help="Show performance history and profiles")

    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    """Runs the legacy planner by default or dispatches a developer subcommand."""
    args = parse_arguments(argv)

    if not args.command:
        args.command = "plan"

    print_banner()

    if args.command == "plan":
        handle_plan(args)
    elif args.command == "benchmark":
        handle_benchmark(args)
    elif args.command == "watch":
        handle_watch(args)
    elif args.command == "cache":
        handle_cache(args)
    elif args.command == "test":
        handle_test(args)
    elif args.command == "profile":
        handle_profile(args)

if __name__ == "__main__":
    main()
