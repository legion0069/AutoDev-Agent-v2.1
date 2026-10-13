from core.documentation_intelligence import DocumentationIntelligence
from core.engineering_memory import EngineeringMemory


def test_document_sections_can_be_indexed_and_searched(tmp_path):
    (tmp_path / "README.md").write_text(
        "# Overview\nGeneral project.\n\n## Cache Design\nBounded cache behavior.\n",
        encoding="utf-8",
    )
    intelligence = DocumentationIntelligence(tmp_path, EngineeringMemory(tmp_path))
    sections = intelligence.analyze()

    assert [section["heading"] for section in sections] == ["Overview", "Cache Design"]
    matches = intelligence.search("bounded cache")
    assert matches[0]["heading"] == "Cache Design"
