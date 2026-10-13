from core.context_intelligence import ContextIntelligence
from core.engineering_memory import EngineeringMemory
from core.experience_engine import ExperienceEngine


def test_context_is_bounded_and_excludes_private_fields(tmp_path):
    memory = EngineeringMemory(tmp_path)
    memory.store({"type": "task", "title": "Cache support", "success": True, "summary": "Reuse existing cache interface"})
    context = ContextIntelligence(ExperienceEngine(memory)).build_context(
        "cache support",
        max_items=1,
        max_chars=1000,
    )

    assert context["item_count"] == 1
    assert context["character_count"] <= 1000
    assert "chain_of_thought" not in str(context)
