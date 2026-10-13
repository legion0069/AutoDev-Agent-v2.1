from core.api_discovery import APIDiscoveryEngine


def test_api_discovery_finds_rest_python_cli_graphql_and_configuration(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "service.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/items')\n"
        "def list_items(limit=10):\n    return []\n"
        "def public_helper():\n    return None\n"
        "parser.add_argument('--verbose')\n",
        encoding="utf-8",
    )
    (root / "schema.graphql").write_text("type Query { items: [Item] }\n", encoding="utf-8")
    (root / "openapi.yaml").write_text(
        "openapi: 3.0.0\npaths:\n  /health:\n    get:\n      operationId: health\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")

    apis = APIDiscoveryEngine(root).discover()

    assert any(item.get("route") == "/items" and item.get("method") == "GET" for item in apis)
    assert any(item.get("name") == "public_helper" for item in apis)
    assert any(item["kind"] == "cli_option" and item["name"] == "--verbose" for item in apis)
    assert any(item["kind"] == "graphql" and item["name"] == "Query" for item in apis)
    assert any(item["kind"] == "configuration" for item in apis)
    assert any(
        item.get("route") == "/health" and item.get("method") == "GET"
        for item in apis
    )
    assert APIDiscoveryEngine(root).search("items", apis=apis)
