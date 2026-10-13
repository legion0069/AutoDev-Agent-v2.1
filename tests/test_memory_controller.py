from core.memory_controller import MemoryController


def test_controller_records_outcomes_and_provides_context(tmp_path):
    controller = MemoryController(tmp_path)
    stored = controller.record_task_outcome({
        "task_id": "task-1",
        "title": "Cache implementation",
        "success": True,
        "summary": "Added bounded cache",
    })

    assert stored["record_id"]
    assert controller.retrieve_context("cache")["item_count"] == 1
    assert controller.status()["memory"]["total_records"] == 1
    assert controller.status()["knowledge_graph"]["nodes"] == 2


def test_controller_rejects_outcomes_without_boolean_success(tmp_path):
    controller = MemoryController(tmp_path)
    try:
        controller.record_task_outcome({"task_id": "missing-status", "success": "yes"})
    except ValueError as error:
        assert "boolean success" in str(error)
    else:
        raise AssertionError("Expected invalid task outcome to be rejected.")
