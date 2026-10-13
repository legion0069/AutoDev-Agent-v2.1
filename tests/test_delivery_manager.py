from core.delivery_manager import DeliveryManager


def test_release_readiness_requires_all_gates_and_no_risks():
    manager = DeliveryManager()
    checks = {gate: True for gate in manager.REQUIRED_GATES}
    assert manager.assess_release("REL-1", checks)["ready"]
    blocked = manager.assess_release("REL-1", checks, {"risk_count": 1})
    assert not blocked["ready"]
    assert blocked["blockers"] == ["unresolved_risks"]
    assert blocked["confidence"] < 1


def test_unknown_checks_are_reported_as_blockers():
    result = DeliveryManager().assess_release("REL-2")
    assert not result["ready"]
    assert len(result["blockers"]) == len(DeliveryManager.REQUIRED_GATES)
    assert result["confidence"] == 0
