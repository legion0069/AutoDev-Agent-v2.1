from core.knowledge_graph import KnowledgeGraph


def test_graph_paths_and_related_nodes_are_stable():
    graph = KnowledgeGraph()
    for node_id in ("a", "b", "c", "d"):
        graph.add_node("module", node_id, node_id)
    graph.add_edge("a", "b", "depends_on")
    graph.add_edge("a", "c", "depends_on")
    graph.add_edge("b", "d", "depends_on")
    graph.add_edge("c", "d", "depends_on")

    assert graph.find_paths("a", "d") == [["a", "b", "d"], ["a", "c", "d"]]
    assert graph.related_nodes("a", max_depth=1) == [
        graph.get_node("b"),
        graph.get_node("c"),
    ]
    assert graph.dependency_graph("a") == {"a": ["b", "c"], "b": [], "c": []}
