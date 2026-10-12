from threading import Lock

from core.execution_scheduler import ScheduledTask
from core.parallel_scheduler import ParallelTaskScheduler


def test_dependency_execution_returns_stable_results() -> None:
    scheduler = ParallelTaskScheduler(max_workers=3)
    events: list[str] = []
    lock = Lock()

    def record(value: str) -> str:
        with lock:
            events.append(value)
        return value

    tasks = [
        ScheduledTask("a", record, args=("a",)),
        ScheduledTask("b", record, args=("b",)),
        ScheduledTask("c", record, args=("c",), dependencies={"a", "b"}),
    ]
    results = scheduler.schedule(tasks)

    assert list(results) == ["a", "b", "c"]
    assert events.index("a") < events.index("c")
    assert events.index("b") < events.index("c")


def test_scheduler_rejects_dependency_cycles() -> None:
    scheduler = ParallelTaskScheduler()
    try:
        scheduler.schedule(
            [
                ScheduledTask("a", lambda: None, dependencies={"b"}),
                ScheduledTask("b", lambda: None, dependencies={"a"}),
            ]
        )
    except ValueError as error:
        assert "cycle" in str(error)
    else:
        raise AssertionError("dependency cycle should be rejected")


def test_scheduler_handles_one_thousand_independent_tasks() -> None:
    scheduler = ParallelTaskScheduler(max_workers=8)
    tasks = [
        ScheduledTask(
            f"task-{index:04d}",
            lambda value: value,
            args=(index,),
        )
        for index in range(1000)
    ]

    results = scheduler.schedule(tasks)

    assert len(results) == 1000
    assert list(results) == [f"task-{index:04d}" for index in range(1000)]
    assert results["task-0999"] == 999
