import pytest

from core.software_knowledge_graph import SoftwareKnowledgeGraph


def test_graph_traversal_and_exports_are_deterministic_and_isolated():
    graph = SoftwareKnowledgeGraph()
    original = {"tags": ["stable"]}
    returned = graph.add_node("module", "module:a.py", "a.py", original)
    original["tags"].append("mutated")
    returned["attributes"]["tags"].append("mutated")
    graph.add_node("function", "function:run", "run")
    graph.add_node("experiment", "experiment:one", "experiment one")
    graph.add_edge("module:a.py", "function:run", "defines")
    graph.add_edge("function:run", "experiment:one", "evaluated_by")

    assert graph.get_node("module:a.py")["attributes"]["tags"] == ["stable"]
    assert graph.traverse("module:a.py", max_depth=2) == [
        "experiment:one",
        "function:run",
    ]
    assert graph.shortest_path("module:a.py", "experiment:one") == [
        "module:a.py",
        "function:run",
        "experiment:one",
    ]
    assert graph.export_json() == graph.export_json()


def test_graph_rejects_invalid_edges_and_traversal_directions():
    graph = SoftwareKnowledgeGraph()
    graph.add_node("module", "module:a.py", "a.py")

    with pytest.raises(KeyError):
        graph.add_edge("module:a.py", "missing", "depends_on")
    with pytest.raises(ValueError, match="direction"):
        graph.neighbors("missing", direction="sideways")
