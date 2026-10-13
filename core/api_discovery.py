"""Static discovery of REST, GraphQL, CLI, Python, and configuration APIs."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Iterable


class APIDiscoveryEngine:
    """Extracts searchable API metadata from source and configuration files."""

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def discover(self, paths: Iterable[str | Path] | None = None) -> list[dict[str, Any]]:
        files = self._files(paths)
        results: list[dict[str, Any]] = []
        for path in files:
            relative = path.relative_to(self.project_root).as_posix()
            suffix = path.suffix.lower()
            if suffix == ".py":
                results.extend(self._python_apis(path, relative))
            elif suffix in {".yaml", ".yml", ".json"} and path.name.lower() in {
                "openapi.json", "swagger.json", "openapi.yaml", "openapi.yml",
            }:
                results.extend(self._openapi_apis(path, relative))
            elif suffix in {".graphql", ".gql"}:
                results.extend(self._graphql_file(path, relative))
            elif path.name.lower() in {"pyproject.toml", "setup.cfg", ".env.example", "config.schema.json"}:
                results.append({
                    "kind": "configuration",
                    "name": path.name,
                    "path": relative,
                    "format": suffix.lstrip(".") or "ini",
                })
        return sorted(
            results,
            key=lambda item: (item["kind"], item["path"], item.get("name", ""), item.get("method", ""), item.get("route", "")),
        )

    def search(self, query: str, *, limit: int = 20, apis: Iterable[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        if limit < 0:
            raise ValueError("limit must not be negative.")
        tokens = {item for item in re.findall(r"[a-z0-9_./-]+", query.casefold()) if item}
        items = list(apis) if apis is not None else self.discover()
        scored = []
        for item in items:
            text = " ".join(str(value) for value in item.values()).casefold()
            matches = sum(token in text for token in tokens)
            if not tokens or matches:
                result = dict(item)
                result["score"] = round(matches / max(1, len(tokens)), 6) if tokens else 0.0
                scored.append(result)
        return sorted(scored, key=lambda item: (-item["score"], item["path"], item.get("name", "")))[:limit]

    def _files(self, paths: Iterable[str | Path] | None) -> list[Path]:
        ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}
        if paths is not None:
            candidates = [Path(item) if Path(item).is_absolute() else self.project_root / item for item in paths]
            return sorted(
                {path.resolve() for path in candidates if path.is_file() and path.resolve().is_relative_to(self.project_root)},
                key=lambda item: item.as_posix(),
            )
        found = []
        for path in self.project_root.rglob("*"):
            if any(part in ignored for part in path.parts):
                continue
            if path.is_file() and (
                path.suffix.lower() in {".py", ".graphql", ".gql"}
                or path.name.lower() in {"openapi.json", "swagger.json", "openapi.yaml", "openapi.yml", "pyproject.toml", "setup.cfg", ".env.example", "config.schema.json"}
            ):
                found.append(path)
        return sorted(found, key=lambda item: item.as_posix())

    def _python_apis(self, path: Path, relative: str) -> list[dict[str, Any]]:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeError, SyntaxError):
            return []
        found = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorators = [_decorator_text(item) for item in node.decorator_list]
                route = next((item for item in decorators if _is_route_decorator(item)), None)
                if route:
                    found.append({
                        "kind": "rest",
                        "name": node.name,
                        "path": relative,
                        "line": node.lineno,
                        "method": _route_method(route),
                        "route": _route_path(route),
                        "framework": _framework(route),
                    })
                if any("click.command" in item or "typer.command" in item for item in decorators):
                    found.append({"kind": "cli", "name": node.name, "path": relative, "line": node.lineno})
                if not node.name.startswith("_") and not route:
                    found.append({
                        "kind": "python",
                        "name": node.name,
                        "path": relative,
                        "line": node.lineno,
                        "async": isinstance(node, ast.AsyncFunctionDef),
                        "parameters": [arg.arg for arg in node.args.args],
                    })
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                found.append({
                    "kind": "python_class",
                    "name": node.name,
                    "path": relative,
                    "line": node.lineno,
                })
            elif isinstance(node, ast.Call):
                text = ast.unparse(node.func) if hasattr(ast, "unparse") else ""
                if text.endswith((".add_argument", ".command", ".option", ".add_subparsers", ".add_parser")):
                    found.append({
                        "kind": "cli_option",
                        "name": _cli_name(node, text),
                        "path": relative,
                        "line": node.lineno,
                    })
        return found

    def _openapi_apis(self, path: Path, relative: str) -> list[dict[str, Any]]:
        if path.suffix.lower() != ".json":
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                return []
            return _openapi_yaml_apis(content, path.stem, relative)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return []
        paths = data.get("paths", {})
        found = []
        if isinstance(paths, dict):
            for route, operations in sorted(paths.items()):
                if not isinstance(operations, dict):
                    continue
                for method, details in sorted(operations.items()):
                    if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                        continue
                    found.append({
                        "kind": "rest",
                        "name": str((details or {}).get("operationId", f"{method.upper()} {route}")),
                        "path": relative,
                        "route": route,
                        "method": method.upper(),
                        "framework": "OpenAPI",
                    })
        return found

    def _graphql_file(self, path: Path, relative: str) -> list[dict[str, Any]]:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return []
        return [
            {"kind": "graphql", "name": name, "operation": operation, "path": relative}
            for operation, name in re.findall(
                r"\b(type|query|mutation|subscription)\s+([A-Za-z_][A-Za-z0-9_]*)",
                text,
            )
        ]


def _decorator_text(node: ast.expr) -> str:
    return ast.unparse(node) if hasattr(ast, "unparse") else ""


def _is_route_decorator(value: str) -> bool:
    return any(name in value.casefold() for name in (".get(", ".post(", ".put(", ".patch(", ".delete(", ".route(", ".api_route("))


def _route_method(value: str) -> str:
    methods = re.search(r"\bmethods\s*=\s*\[([^\]]+)\]", value, re.I)
    if methods:
        found = re.search(r"['\"]([A-Za-z]+)['\"]", methods.group(1))
        if found:
            return found.group(1).upper()
    match = re.search(r"\.(get|post|put|patch|delete|api_route|route)\s*\(", value, re.I)
    return match.group(1).upper() if match else "ROUTE"


def _route_path(value: str) -> str:
    match = re.search(r"\(\s*(['\"])(.*?)\1", value)
    return match.group(2) if match else ""


def _framework(value: str) -> str:
    return "FastAPI/Starlette" if "api_route" in value or any(f".{name}(" in value for name in ("get", "post", "put", "patch", "delete")) else "Python web framework"


def _cli_name(node: ast.Call, fallback: str) -> str:
    if not node.args:
        return fallback
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return ast.unparse(first) if hasattr(ast, "unparse") else fallback


def _openapi_yaml_apis(text: str, name: str, relative: str) -> list[dict[str, Any]]:
    path_indent: int | None = None
    route: str | None = None
    found = []
    methods = {"get", "post", "put", "patch", "delete", "head", "options"}
    for line in text.splitlines():
        content = line.split("#", 1)[0].rstrip()
        if not content.strip():
            continue
        indent = len(content) - len(content.lstrip())
        value = content.strip()
        if value == "paths:":
            path_indent = indent
            route = None
            continue
        if path_indent is None:
            continue
        if indent <= path_indent:
            path_indent = None
            route = None
            continue
        if indent == path_indent + 2 and value.endswith(":"):
            route = value[:-1].strip().strip("'\"")
            continue
        method_match = re.fullmatch(r"([A-Za-z]+)\s*:", value)
        if route and indent == path_indent + 4 and method_match:
            method = method_match.group(1).casefold()
            if method in methods:
                found.append({
                    "kind": "rest",
                    "name": f"{method.upper()} {route}",
                    "path": relative,
                    "route": route,
                    "method": method.upper(),
                    "framework": "OpenAPI",
                })
    return found or [{
        "kind": "rest_schema",
        "name": name,
        "path": relative,
        "format": "yaml",
    }]
