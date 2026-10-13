import pytest

from core.resource_manager import ResourceManager


def test_capacity_queue_priority_and_release():
    manager = ResourceManager({"workers": 2})
    first = manager.allocate("workers", 1, "first", priority=0)
    low = manager.allocate("workers", 1, "low", priority=1)
    high = manager.allocate("workers", 1, "high", priority=5)
    assert first.status == "ALLOCATED"
    assert low.status == "ALLOCATED"
    assert high.status == "QUEUED"

    manager.release(first.allocation_id)
    assert manager._allocations[high.allocation_id].status == "ALLOCATED"
    assert manager.resource_usage()["queue_count"] == 0


def test_forecast_and_input_validation():
    manager = ResourceManager({"cpu": 1})
    allocation = manager.allocate("cpu", 0.5, "build")
    assert manager.forecast({"cpu": 0.6})["cpu"]["sufficient"] is False
    assert manager.release(allocation.allocation_id)
    assert manager.resource_usage()["resources"]["cpu"]["allocated"] == 0.0
    with pytest.raises(ValueError):
        manager.allocate("cpu", 0, "bad")
    with pytest.raises(KeyError):
        manager.allocate("gpu", 1, "bad")
    with pytest.raises(KeyError):
        manager.forecast({"gpu": 1})
    with pytest.raises(ValueError):
        manager.forecast({"cpu": -1})


def test_new_requests_do_not_bypass_a_waiting_higher_priority_request():
    manager = ResourceManager({"workers": 2})
    occupying = manager.allocate("workers", 1, "occupying")
    waiting = manager.allocate("workers", 1.5, "priority", priority=10)
    lower = manager.allocate("workers", 0.5, "lower", priority=0)
    assert waiting.status == "QUEUED"
    assert lower.status == "QUEUED"

    manager.release(occupying.allocation_id)
    assert manager._allocations[waiting.allocation_id].status == "ALLOCATED"
    assert manager._allocations[lower.allocation_id].status == "ALLOCATED"
