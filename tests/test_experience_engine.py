from core.engineering_memory import EngineeringMemory
from core.experience_engine import ExperienceEngine


def test_experience_retrieves_relevant_successes_and_failures(tmp_path):
    memory = EngineeringMemory(tmp_path)
    memory.store({"type": "task", "task_id": "ok", "title": "Improve cache", "success": True, "solution": "use bounded entries"})
    memory.store({"type": "failure", "task_id": "bad", "title": "Cache outage", "success": False, "root_cause": "unbounded memory"})
    engine = ExperienceEngine(memory)

    records = engine.retrieve("cache memory")
    assert records
    assert any(item["task_id"] == "ok" for item in records)
    assert engine.failure_lessons("cache", limit=2)
