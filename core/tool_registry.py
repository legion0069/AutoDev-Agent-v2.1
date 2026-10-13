"""Deterministic metadata registry and discovery for local developer tools."""

from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ToolMetadata:
    """Describes a tool without executing it."""

    name: str
    executable: str = ""
    category: str = "general"
    capabilities: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    operating_systems: tuple[str, ...] = ("any",)
    version: str = ""
    minimum_version: str = ""
    maximum_version: str = ""
    available: bool = True
    confidence: float = 1.0
    success_rate: float = 0.5
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("capabilities", "languages", "operating_systems"):
            result[key] = list(result[key])
        result["metadata"] = dict(sorted(self.metadata.items()))
        return result


class ToolRegistry:
    """Registers tools and resolves deterministic capability matches."""

    def __init__(self, *, discover: bool = False) -> None:
        self._tools: dict[str, ToolMetadata] = {}
        if discover:
            self.discover()

    def register(
        self,
        tool: ToolMetadata | Mapping[str, Any] | str,
        **kwargs: Any,
    ) -> ToolMetadata:
        if isinstance(tool, str):
            data = {"name": tool, **kwargs}
        elif isinstance(tool, ToolMetadata):
            if kwargs:
                raise TypeError("Keyword metadata cannot be combined with ToolMetadata.")
            data = asdict(tool)
        elif isinstance(tool, Mapping):
            data = {**tool, **kwargs}
        else:
            raise TypeError("tool must be a name, ToolMetadata, or metadata mapping.")
        name = str(data.pop("name", "")).strip()
        if not name:
            raise ValueError("Tool name must be non-empty.")
        normalized = {
            "name": name,
            "executable": str(data.get("executable", name)),
            "category": str(data.get("category", "general")),
            "capabilities": _string_tuple(data.get("capabilities", ())),
            "languages": _string_tuple(data.get("languages", ())),
            "operating_systems": _string_tuple(data.get("operating_systems", ("any",))),
            "version": str(data.get("version", "")),
            "minimum_version": str(data.get("minimum_version", "")),
            "maximum_version": str(data.get("maximum_version", "")),
            "available": bool(data.get("available", True)),
            "confidence": _bounded_score(data.get("confidence", 1.0)),
            "success_rate": _bounded_score(data.get("success_rate", 0.5)),
            "metadata": dict(data.get("metadata", {})),
        }
        metadata = ToolMetadata(**normalized)
        self._tools[name.casefold()] = metadata
        return metadata

    def discover(self, executables: Iterable[str] | None = None) -> list[ToolMetadata]:
        """Discover common build/test/package tools visible on PATH."""
        names = sorted(set(_COMMON_TOOLS if executables is None else executables))
        os_name = _platform_name()
        discovered = []
        for name in names:
            path = shutil.which(name)
            if path is None:
                continue
            capabilities, languages, category = _TOOL_CAPABILITIES.get(
                name,
                (("execute",), (), "general"),
            )
            discovered.append(self.register(
                name,
                executable=path,
                category=category,
                capabilities=capabilities,
                languages=languages,
                operating_systems=(os_name,),
                available=True,
                confidence=0.95,
                metadata={"discovery": "PATH"},
            ))
        return discovered

    def get(self, name: str) -> ToolMetadata | None:
        return self._tools.get(name.casefold())

    def list_tools(
        self,
        *,
        available_only: bool = False,
        category: str | None = None,
    ) -> list[ToolMetadata]:
        tools = self._tools.values()
        return [
            tool for tool in sorted(tools, key=lambda item: item.name.casefold())
            if (not available_only or tool.available)
            and (category is None or tool.category.casefold() == category.casefold())
        ]

    def lookup(
        self,
        capability: str,
        *,
        language: str | None = None,
        operating_system: str | None = None,
        version: str | None = None,
    ) -> list[ToolMetadata]:
        capability_key = capability.casefold()
        language_key = language.casefold() if language else None
        os_key = operating_system.casefold() if operating_system else None
        return [
            tool for tool in self.list_tools(available_only=True)
            if capability_key in {item.casefold() for item in tool.capabilities}
            and (language_key is None or not tool.languages or language_key in {item.casefold() for item in tool.languages})
            and (os_key is None or "any" in {item.casefold() for item in tool.operating_systems} or os_key in {item.casefold() for item in tool.operating_systems})
            and (version is None or is_version_compatible(tool, version))
        ]

    def to_dict(self) -> dict[str, Any]:
        return {"tools": [tool.to_dict() for tool in self.list_tools()]}


_COMMON_TOOLS = (
    "python", "python3", "pytest", "pip", "uv", "poetry", "pipenv",
    "node", "npm", "npx", "pnpm", "yarn", "git", "docker", "podman",
    "make", "cmake", "cargo", "rustc", "go", "javac", "mvn", "gradle",
    "dotnet", "terraform", "az",
)
_TOOL_CAPABILITIES: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    "python": (("run", "test", "build"), ("python",), "runtime"),
    "python3": (("run", "test", "build"), ("python",), "runtime"),
    "pytest": (("test",), ("python",), "test"),
    "pip": (("package", "install"), ("python",), "package_manager"),
    "uv": (("package", "install", "run", "test"), ("python",), "package_manager"),
    "poetry": (("package", "install", "build", "test"), ("python",), "package_manager"),
    "pipenv": (("package", "install", "run"), ("python",), "package_manager"),
    "node": (("run", "build"), ("javascript", "typescript"), "runtime"),
    "npm": (("package", "install", "run", "build", "test"), ("javascript", "typescript"), "package_manager"),
    "npx": (("run", "test", "build"), ("javascript", "typescript"), "runtime"),
    "pnpm": (("package", "install", "run", "build", "test"), ("javascript", "typescript"), "package_manager"),
    "yarn": (("package", "install", "run", "build", "test"), ("javascript", "typescript"), "package_manager"),
    "git": (("history", "repository", "version_control"), (), "version_control"),
    "docker": (("container", "build", "run"), (), "container"),
    "podman": (("container", "build", "run"), (), "container"),
    "make": (("build", "test"), (), "build"),
    "cmake": (("build",), ("c", "c++"), "build"),
    "cargo": (("package", "build", "test"), ("rust",), "package_manager"),
    "rustc": (("build", "run"), ("rust",), "runtime"),
    "go": (("package", "build", "test", "run"), ("go",), "build"),
    "javac": (("build",), ("java",), "compiler"),
    "mvn": (("package", "build", "test"), ("java",), "build"),
    "gradle": (("package", "build", "test"), ("java", "kotlin"), "build"),
    "dotnet": (("package", "build", "test", "run"), ("c#", "f#"), "build"),
    "terraform": (("infrastructure", "validate"), (), "infrastructure"),
    "az": (("cloud",), (), "cloud"),
}


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        value = (value,)
    return tuple(sorted({str(item).strip() for item in value if str(item).strip()}))


def _bounded_score(value: Any) -> float:
    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise ValueError("confidence and success_rate must be between 0 and 1.")
    return score


def _platform_name() -> str:
    name = platform.system().casefold()
    return name or sys.platform.casefold()


def is_version_compatible(tool: ToolMetadata, version: str) -> bool:
    """Checks a requested dotted numeric version against optional tool bounds."""
    requested = _version_parts(version)
    if requested is None:
        raise ValueError(f"Unsupported version format: {version!r}.")
    minimum = _version_parts(tool.minimum_version) if tool.minimum_version else None
    maximum = _version_parts(tool.maximum_version) if tool.maximum_version else None
    if tool.minimum_version and minimum is None:
        raise ValueError(f"Unsupported minimum version for tool {tool.name!r}.")
    if tool.maximum_version and maximum is None:
        raise ValueError(f"Unsupported maximum version for tool {tool.name!r}.")
    width = max(
        len(requested),
        len(minimum) if minimum else 0,
        len(maximum) if maximum else 0,
    )
    requested = requested + (0,) * (width - len(requested))
    minimum = minimum + (0,) * (width - len(minimum)) if minimum else None
    maximum = maximum + (0,) * (width - len(maximum)) if maximum else None
    return not (minimum and requested < minimum) and not (maximum and requested > maximum)


def _version_parts(value: str) -> tuple[int, ...] | None:
    import re

    match = re.fullmatch(r"\s*(\d+(?:\.\d+)*)\s*", value)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))
