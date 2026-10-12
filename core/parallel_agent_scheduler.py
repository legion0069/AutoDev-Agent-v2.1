"""
parallel_agent_scheduler.py - Concurrent Task Execution Engine for AutoDev (v3.6.1)

Executes independent engineering sub-tasks concurrently to reduce overall latency.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("AutoDev.ParallelAgentScheduler")

@dataclass
class ScheduledTask:
    """A task scheduled for execution."""
    id: str
    func: Callable
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    dependencies: Set[str] = field(default_factory=set)
    priority: int = 1
    description: str = ""

class ParallelAgentScheduler:
    """
    Schedules and executes tasks concurrently while respecting dependency constraints.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers
        self.tasks: Dict[str, ScheduledTask] = {}

    def add_task(
        self,
        task_id: str,
        func: Callable,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        dependencies: Optional[Set[str]] = None,
        priority: int = 1,
        description: str = ""
    ) -> None:
        """Adds a task to the scheduler."""
        self.tasks[task_id] = ScheduledTask(
            id=task_id,
            func=func,
            args=args or [],
            kwargs=kwargs or {},
            dependencies=dependencies or set(),
            priority=priority,
            description=description
        )

    def execute(self) -> Dict[str, Any]:
        """
        Executes all tasks in the optimal concurrent order.
        Returns a mapping of task_id to their results.
        """
        start_time = time.time()
        results: Dict[str, Any] = {}
        completed: Set[str] = set()
        in_progress: Set[str] = set()
        
        # Simple topological-ish concurrent execution
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while len(completed) < len(self.tasks):
                # Find ready tasks
                ready_tasks = [
                    t for t in self.tasks.values()
                    if t.id not in completed 
                    and t.id not in in_progress
                    and t.dependencies.issubset(completed)
                ]
                
                if not ready_tasks and not in_progress:
                    # Circular dependency detected or all tasks stuck
                    logger.error("Deadlock or circular dependency detected in task scheduler.")
                    break
                
                # Submit ready tasks
                future_to_task = {}
                for task in ready_tasks:
                    logger.info(f"Submitting task: {task.id} ({task.description})")
                    future = executor.submit(task.func, *task.args, **task.kwargs)
                    future_to_task[future] = task.id
                    in_progress.add(task.id)
                
                # Wait for at least one task to complete if we can't submit more
                if in_progress:
                    # We use as_completed to get the first one that finishes
                    # But we only want to process what was just submitted or already running
                    for future in as_completed(list(future_to_task.keys()) if ready_tasks else list(executor._threads)): # This is a bit hacky
                        # Wait for ANY future to complete
                        break

                    # Check all futures for completion
                    # (In a more robust version, we'd manage futures more carefully)
                    for future in list(future_to_task.keys()):
                        if future.done():
                            tid = future_to_task.pop(future)
                            try:
                                results[tid] = future.result()
                                completed.add(tid)
                                in_progress.remove(tid)
                                logger.info(f"Task completed: {tid}")
                            except Exception as e:
                                logger.error(f"Task {tid} failed: {e}", exc_info=True)
                                results[tid] = e
                                completed.add(tid) # Mark as completed even on failure to avoid deadlock
                                in_progress.remove(tid)

                # Small sleep to avoid tight loop if waiting for results
                if not ready_tasks:
                    time.sleep(0.05)

        logger.info(f"Parallel execution of {len(self.tasks)} tasks completed in {time.time() - start_time:.4f}s")
        return results
