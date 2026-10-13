from core.engineering_memory import EngineeringMemory
from core.knowledge_consolidation import KnowledgeConsolidationEngine


def test_consolidation_groups_duplicate_lessons_without_deleting_sources(tmp_path):
    memory = EngineeringMemory(tmp_path)
    memory.store({"type": "lesson", "title": "Use bounded cache", "topic": "cache", "success": True}, record_id="one")
    memory.store({"type": "lesson", "title": "Use bounded cache", "topic": "cache", "success": False}, record_id="two")
    engine = KnowledgeConsolidationEngine(memory)

    groups = engine.consolidate()
    assert len(groups) == 1
    assert groups[0]["occurrences"] == 2
    assert len(memory.records()) == 2
