from core.self_optimizer import SelfOptimizer


def test_self_optimizer_covers_domains_without_changing_behavior():
    result = SelfOptimizer().optimize(
        {
            "planning": {"latency_seconds": 2.0},
            "caching": {"hit_ratio": 0.2},
        }
    )

    assert {item["domain"] for item in result["proposals"]} == set(SelfOptimizer.DOMAINS)
    assert result["behavior_changed"] is False
    assert all(not item["changes_external_behavior"] for item in result["proposals"])
