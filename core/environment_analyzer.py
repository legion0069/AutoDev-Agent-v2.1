"""Read-only analysis of the host and project development environment."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from core.project_environment_detector import ProjectEnvironmentDetector


class EnvironmentAnalyzer:
    """Combines existing project-stack detection with local host facts."""

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.project_detector = ProjectEnvironmentDetector(self.project_root)

    def analyze(self) -> dict[str, Any]:
        root = self.project_root
        project_environment = self.project_detector.detect(root).to_dict()
        memory_bytes = _available_memory()
        disk = shutil.disk_usage(root if root.exists() else Path.cwd())
        tools = {}
        for name in _KNOWN_TOOLS:
            executable = shutil.which(name)
            if executable is not None:
                tools[name] = executable
        return {
            "operating_system": platform.system().casefold() or sys.platform.casefold(),
            "platform": platform.platform(),
            "python": {
                "version": platform.python_version(),
                "implementation": platform.python_implementation(),
                "executable": str(Path(sys.executable).resolve()),
                "virtual_environment": sys.prefix != getattr(sys, "base_prefix", sys.prefix),
                "environment_prefix": sys.prefix,
            },
            "git_repository": _is_git_repository(root),
            "package_managers": sorted(
                name for name in ("pip", "uv", "poetry", "pipenv", "npm", "pnpm", "yarn", "cargo", "go")
                if name in tools
            ),
            "build_systems": _build_systems(root, project_environment),
            "ci_configurations": _ci_configurations(root),
            "docker": {
                "configured": any((root / name).exists() for name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")),
                "available": "docker" in tools or "podman" in tools,
                "container": Path("/.dockerenv").exists() or bool(os.environ.get("KUBERNETES_SERVICE_HOST")),
            },
            "workspace": {
                "root": str(root),
                "exists": root.is_dir(),
                "top_level_entries": sorted(path.name for path in root.iterdir()) if root.is_dir() else [],
                "layout": _layout(root),
            },
            "resources": {
                "available_memory_bytes": memory_bytes,
                "cpu_count": os.cpu_count() or 1,
                "disk_total_bytes": disk.total,
                "disk_free_bytes": disk.free,
                "disk_used_bytes": disk.used,
            },
            "available_tools": dict(sorted(tools.items())),
            "project": project_environment,
        }


_KNOWN_TOOLS = (
    "python", "python3", "pytest", "pip", "uv", "poetry", "pipenv", "node",
    "npm", "pnpm", "yarn", "git", "docker", "podman", "make", "cmake",
    "cargo", "rustc", "go", "javac", "mvn", "gradle", "dotnet",
)


def _available_memory() -> int | None:
    try:
        if hasattr(os, "sysconf"):
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            pages = int(os.sysconf("SC_AVPHYS_PAGES"))
            if page_size > 0 and pages >= 0:
                return page_size * pages
    except (OSError, ValueError, TypeError):
        return None
    return None


def _is_git_repository(root: Path) -> bool:
    return (root / ".git").exists() or (root / ".git").is_file()


def _build_systems(root: Path, project: dict[str, Any]) -> list[str]:
    systems = set(map(str, project.get("build_tools", [])))
    patterns = {
        "Makefile": "make",
        "CMakeLists.txt": "cmake",
        "Cargo.toml": "cargo",
        "go.mod": "go",
        "pom.xml": "maven",
        "build.gradle": "gradle",
        "build.gradle.kts": "gradle",
        "package.json": "npm",
    }
    for filename, system in patterns.items():
        if (root / filename).is_file():
            systems.add(system)
    return sorted(systems)


def _ci_configurations(root: Path) -> list[str]:
    found = []
    github_workflows = root / ".github" / "workflows"
    if github_workflows.is_dir():
        found.extend(
            f".github/workflows/{path.name}"
            for path in sorted(github_workflows.iterdir())
            if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
        )
    for name in (".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml", ".circleci/config.yml"):
        if (root / name).is_file():
            found.append(name)
    return sorted(found)


def _layout(root: Path) -> dict[str, list[str]]:
    categories: dict[str, list[str]] = {"packages": [], "tests": [], "docs": [], "source": []}
    if not root.is_dir():
        return categories
    for child in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        low = child.name.casefold()
        if low in {"tests", "test"}:
            key = "tests"
        elif low in {"docs", "doc", "documentation"}:
            key = "docs"
        elif low in {"src", "source", "lib"}:
            key = "source"
        else:
            key = "packages"
        categories[key].append(child.name)
    return categories
