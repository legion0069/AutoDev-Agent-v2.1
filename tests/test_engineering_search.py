from core.engineering_memory import EngineeringMemory
from core.engineering_search import EngineeringSearchEngine
from core.knowledge_graph import KnowledgeGraph


def test_search_finds_memory_and_graph_entities(tmp_path):
    memory = EngineeringMemory(tmp_path)
    memory.store({
        "type": "bug",
        "title": "Cache invalidation failure",
        "problem": "stale values after updates",
        "success": False,
    })
    graph = KnowledgeGraph()
    graph.add_node("module", "module:core/cache.py", "cache manager")
    engine = EngineeringSearchEngine(memory, graph)

    results = engine.search("cache invalidation")
    assert results
    assert any(item["kind"] == "memory" for item in results)
    assert any(item["kind"] == "graph" for item in results)
    assert engine.search("cache.py", mode="dependency")[0]["node_id"] == "module:core/cache.py"
