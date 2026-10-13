from core.resource_manager import ResourceManager
from core.risk_manager import RiskManager


def test_risk_categories_and_mitigations_are_deterministic():
    manager = RiskManager()
    report = manager.analyze({
        "overdue_milestones": 1,
        "architecture_risk_score": 80,
        "technical_debt_items": 2,
        "dependency_bottlenecks": 1,
        "quality_score": 70,
        "resource_demand": {"workers": 3},
    }, ResourceManager({"workers": 1}))

    assert report.risk_count == 6
    assert [item["category"] for item in report.risks] == [
        "architecture", "dependency", "quality", "resource", "schedule", "technical_debt"
    ]
    assert len(report.mitigation_plan) == report.risk_count


def test_no_risks_for_healthy_signals():
    report = RiskManager().analyze({"quality_score": 95})
    assert report.to_dict() == {"risk_count": 0, "risks": [], "mitigation_plan": []}
