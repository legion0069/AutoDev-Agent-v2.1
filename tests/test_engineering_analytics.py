import pytest

from core.engineering_analytics import EngineeringAnalytics


def test_analytics_are_aggregated_and_persisted(tmp_path):
    analytics = EngineeringAnalytics(tmp_path)
    analytics.record(
        completed=True, lead_time_hours=4, cycle_time_hours=2,
        review_duration_hours=1, defects=1, deployments=1,
    )
    analytics.record(completed=False, lead_time_hours=2, cycle_time_hours=1)
    metrics = analytics.metrics()
    assert metrics["sample_count"] == 2
    assert metrics["velocity"] == 1
    assert metrics["lead_time_hours"] == 3
    assert metrics["defect_escape_rate"] == 0.5
    assert EngineeringAnalytics(tmp_path).metrics() == metrics


def test_deployment_readiness_is_tracked_and_inputs_are_validated(tmp_path):
    analytics = EngineeringAnalytics(tmp_path)
    analytics.record(completed=True, deployment_ready=True)
    analytics.record(completed=False, deployment_ready=False)
    assert analytics.metrics()["deployment_readiness"] == 0.5
    with pytest.raises(ValueError):
        analytics.record(completed=True, deployment_ready="yes")
