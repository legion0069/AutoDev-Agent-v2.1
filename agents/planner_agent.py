"""
planner_agent.py - Planner Agent for AutoDev

Responsible for taking high-level project metadata (name, description,
tech stack, and development duration) and generating a structured, day-by-day
development roadmap exported as JSON.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_WORKFLOW = [
    "User Request",
    "Requirement Understanding",
    "Architecture Design",
    "Project Breakdown",
    "Roadmap Generation",
    "Daily Planning",
    "Today's Work",
    "Code Generation",
    "Incremental Validation",
    "Automatic Bug Fixing",
    "Documentation Update",
    "Git Commit",
    "Git Push",
    "Project State Update",
    "Wait Until Next Execution",
]


def _generate_day_phase(
    day: int,
    total_days: int,
    project_name: str,
    project_description: str,
    tech_stack: str,
) -> Dict[str, Any]:
    """
    Generates a realistic, structured phase definition for a given day
    based on the project's development timeline.
    """
    progress_ratio = day / total_days

    # Single-day quick prototype
    if total_days == 1:
        return {
            "day": 1,
            "phase_name": "Full Prototype & End-to-End Validation",
            "goals": [
                f"Initialize repository structure for {project_name}",
                f"Implement core functionality using {tech_stack}",
                "Write baseline tests and verify end-to-end execution",
            ],
            "tasks": [
                f"Set up project workspace, dependencies, and config for {tech_stack}",
                f"Build core components to address: {project_description}",
                "Add test suite, documentation, and execution guide",
            ],
            "deliverables": [
                "Working prototype codebase",
                "Automated test suite",
                "README and setup instructions",
            ],
            "testing_focus": "Unit tests for core functions and smoke testing",
            "git_commit_message": "feat: initial release of complete prototype",
        }

    # Two-day project
    if total_days == 2:
        if day == 1:
            return {
                "day": 1,
                "phase_name": "Project Setup & Core Feature Implementation",
                "goals": [
                    f"Scaffold project architecture with {tech_stack}",
                    f"Implement foundational logic for {project_name}",
                ],
                "tasks": [
                    "Configure project directory, dependencies, and environment",
                    f"Develop primary data models and business logic for: {project_description}",
                    "Write initial unit tests for data structures",
                ],
                "deliverables": [
                    "Project skeleton and build configuration",
                    "Core business logic modules",
                ],
                "testing_focus": "Unit tests for core logic and data validation",
                "git_commit_message": "feat(core): setup architecture and implement core logic",
            }
        else:
            return {
                "day": 2,
                "phase_name": "Integration, Testing & Final Polish",
                "goals": [
                    "Connect all sub-modules and complete user-facing interfaces",
                    "Achieve high test coverage and finalize documentation",
                ],
                "tasks": [
                    "Implement edge case handling and error boundaries",
                    "Write integration and regression test suites",
                    "Create comprehensive README and finalize release packaging",
                ],
                "deliverables": [
                    "Fully integrated codebase",
                    "Complete automated test suite",
                    "Documentation and setup instructions",
                ],
                "testing_focus": "Integration testing, boundary conditions, and performance sanity",
                "git_commit_message": "chore(release): complete integration, testing, and documentation",
            }

    # Multi-day project (3+ days)
    if day == 1:
        # Day 1: Initialization & Architecture
        return {
            "day": 1,
            "phase_name": "Project Setup & Architectural Skeleton",
            "goals": [
                f"Initialize repository structure for {project_name}",
                f"Configure development environment and tooling for {tech_stack}",
                "Establish base architectural patterns and configuration loading",
            ],
            "tasks": [
                f"Create directory structure and initialize dependency management for {tech_stack}",
                "Implement configuration management and environment variables handling",
                "Create base application entry point with health check / status verification",
            ],
            "deliverables": [
                "Project repository scaffold",
                "Dependency configuration file",
                "Base entry point and architecture blueprint",
            ],
            "testing_focus": "Environment sanity checks and initial boot-up test",
            "git_commit_message": "chore(setup): scaffold project architecture and dependencies",
        }

    if day == total_days:
        # Final Day: Hardening, Polish, Docs & Release
        return {
            "day": day,
            "phase_name": "Final Hardening, Documentation & Release Readiness",
            "goals": [
                f"Perform comprehensive quality assurance on {project_name}",
                "Complete full documentation, setup guides, and code cleanup",
                "Verify end-to-end user workflows and package for distribution",
            ],
            "tasks": [
                "Execute complete test suite (unit, integration, and edge-case verification)",
                "Refactor codebase for readability, performance, and style consistency",
                "Write comprehensive README.md, API/usage documentation, and license",
            ],
            "deliverables": [
                "Production-ready codebase",
                "Complete documentation and usage examples",
                "Verified passing test suite report",
            ],
            "testing_focus": "End-to-end regression testing, stress testing, and edge case coverage",
            "git_commit_message": "chore(release): finalize documentation, polish code, and prepare release",
        }

    # Intermediate days (Days 2 to total_days - 1)
    if progress_ratio <= 0.4:
        return {
            "day": day,
            "phase_name": "Data Architecture & Core Domain Models",
            "goals": [
                "Design and implement data schemas, domain entities, and storage layer",
                f"Establish persistence and data validation logic using {tech_stack}",
            ],
            "tasks": [
                "Define domain models and type definitions",
                "Implement database schemas, migrations, or data storage adapters",
                "Write unit tests for data validation and schema integrity",
            ],
            "deliverables": [
                "Domain models and data schemas",
                "Data access layer and repository interfaces",
                "Model unit test suite",
            ],
            "testing_focus": "Schema validation, serialization/deserialization, and boundary checks",
            "git_commit_message": f"feat(models): implement domain data models and storage layer (Day {day})",
        }
    elif progress_ratio <= 0.7:
        return {
            "day": day,
            "phase_name": "Core Business Logic & Service Implementation",
            "goals": [
                f"Implement main business logic algorithms for: {project_description}",
                "Develop service handlers, controllers, and core computational components",
            ],
            "tasks": [
                "Implement primary business workflows and service interfaces",
                "Integrate domain models with core application logic",
                "Add granular unit tests for service methods and business rules",
            ],
            "deliverables": [
                "Core service modules and business handlers",
                "Service-level unit tests",
            ],
            "testing_focus": "Business logic branching, edge conditions, and error states",
            "git_commit_message": f"feat(services): implement core business logic workflows (Day {day})",
        }
    else:
        return {
            "day": day,
            "phase_name": "API Layer, UI/Interface & System Integration",
            "goals": [
                "Expose business features through public interfaces (API/CLI/UI)",
                "Integrate cross-cutting concerns (logging, error handling, validation)",
            ],
            "tasks": [
                f"Build interface endpoints/commands using {tech_stack}",
                "Wire frontend/interface layer with backend services",
                "Implement structured error handling and operational logging",
            ],
            "deliverables": [
                "API routes or interface components",
                "Integration wiring and middleware",
                "Integration test suite",
            ],
            "testing_focus": "Interface contract testing, integration tests, and error responses",
            "git_commit_message": f"feat(api): implement interface endpoints and system integration (Day {day})",
        }


def generate_project_plan(
    project_name: str,
    project_description: str,
    tech_stack: str,
    days: int,
    github_repository: str | None = None,
    execution_mode: str | None = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Generates a complete structured project plan dictionary.

    Additional metadata such as GitHub repository and execution mode is included to
    support the full AutoDev v5.0 autonomous project lifecycle workflow while
    preserving backward compatibility with the original planner API.
    """
    try:
        total_days = int(days)
    except (TypeError, ValueError) as exc:
        raise ValueError("Number of development days must be a positive integer.") from exc

    if total_days < 1:
        raise ValueError("Number of development days must be at least 1.")

    clean_name = str(project_name).strip()
    clean_desc = str(project_description).strip()
    clean_stack = str(tech_stack).strip()

    repo_url = (
        github_repository
        or kwargs.get("repository_url")
        or kwargs.get("repo_url")
        or kwargs.get("github_url")
        or kwargs.get("repo")
        or ""
    )
    resolved_mode = (
        execution_mode
        or kwargs.get("mode")
        or kwargs.get("execution")
        or "Autonomous"
    )
    normalized_mode = str(resolved_mode).strip() or "Autonomous"

    phases: List[Dict[str, Any]] = [
        _generate_day_phase(
            day=day_idx,
            total_days=total_days,
            project_name=clean_name,
            project_description=clean_desc,
            tech_stack=clean_stack,
        )
        for day_idx in range(1, total_days + 1)
    ]

    plan: Dict[str, Any] = {
        "project_name": clean_name,
        "project_description": clean_desc,
        "technology_stack": clean_stack,
        "total_days": total_days,
        "github_repository": str(repo_url).strip(),
        "execution_mode": normalized_mode,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": list(DEFAULT_WORKFLOW),
        "phases": phases,
        "daily_commit_plan": [
            {
                "day": day_idx,
                "focus": phase["phase_name"],
                "commit_pattern": "conventional",
                "expected_commits": "1-4",
            }
            for day_idx, phase in enumerate(phases, start=1)
        ],
        "project_state": {
            "status": "planned",
            "milestone_count": len(phases),
            "repository": str(repo_url).strip(),
            "execution_mode": normalized_mode,
        },
    }

    return plan


def save_project_plan(
    plan: Dict[str, Any],
    filepath: str | Path = "memory/project_plan.json",
) -> Path:
    """
    Saves a project plan dictionary to a formatted JSON file.

    Args:
        plan: The plan dictionary.
        filepath: Target file path (defaults to memory/project_plan.json).

    Returns:
        The Path object of the saved file.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    return path


def load_project_plan(
    filepath: str | Path = "memory/project_plan.json",
) -> Dict[str, Any]:
    """
    Loads and parses an existing project plan JSON file.

    Args:
        filepath: Path to the JSON file.

    Returns:
        The loaded plan dictionary.
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"Project plan file '{filepath}' was not found.")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
