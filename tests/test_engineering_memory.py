import json

from core.engineering_memory import EngineeringMemory


def test_structured_memory_persists_and_filters_private_reasoning(tmp_path):
    memory = EngineeringMemory(tmp_path)
    record = memory.store({
        "type": "task",
        "task_id": "task-1",
        "title": "Add cache",
        "success": True,
        "chain_of_thought": "must not persist",
        "nested": {"private_reasoning": "must not persist"},
    })

    restored = EngineeringMemory(tmp_path).retrieve(record["record_id"])
    assert restored is not None
    assert restored["task_id"] == "task-1"
    assert "chain_of_thought" not in restored
    assert "private_reasoning" not in json.dumps(restored)


def test_memory_crud_and_search_are_deterministic(tmp_path):
    memory = EngineeringMemory(tmp_path)
    stored = memory.store("bug", {"title": "Cache invalidation", "problem": "stale cache"}, record_id="bug-1")
    updated = memory.update("bug-1", {"solution": "invalidate by key"})

    assert updated["solution"] == "invalidate by key"
    assert memory.search("cache", record_type="bug")[0]["record_id"] == stored["record_id"]
    assert memory.forget("bug-1")
    assert memory.retrieve("bug-1") is None
