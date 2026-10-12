"""Opt-in runtime for deterministic agent discovery and task dispatch."""

from __future__ import annotations

import concurrent.futures
import threading
from typing import Any, Callable, Optional

from core.agent_bus import AgentBus, AgentMessageType
from core.agent_metrics import AgentMetricsTracker
from core.capability_manager import AgentCapabilityManager
from core.multi_agent.agent_registry import AgentDescriptor, AgentRegistry, AgentRole, AgentStatus
from core.task_negotiation import NegotiationResult, TaskNegotiationEngine


class MultiAgentRuntime:
    """Combines the legacy registry with typed bus, capabilities, and negotiation."""

    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        bus: Optional[AgentBus] = None,
        capability_manager: Optional[AgentCapabilityManager] = None,
        metrics_tracker: Optional[AgentMetricsTracker] = None,
        max_workers: int = 4,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least one")
        self.registry = registry or AgentRegistry()
        self.bus = bus or AgentBus()
        self.capability_manager = capability_manager or AgentCapabilityManager(self.registry)
        self.metrics_tracker = metrics_tracker
        self.negotiator = TaskNegotiationEngine(self.capability_manager, metrics_tracker)
        self.max_workers = max_workers
        self._lock = threading.RLock()
        self._handlers: dict[str, Callable[[Any], Any]] = {}
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

    def register_agent(
        self,
        agent: Any = None,
        *,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        capabilities: Optional[list[str]] = None,
        languages: Optional[list[str]] = None,
        domains: Optional[list[str]] = None,
        preferred_workloads: Optional[list[str]] = None,
        handler: Optional[Callable[[Any], Any]] = None,
        role: AgentRole = AgentRole.TASK_SCHEDULER,
        priority: int = 50,
        max_workload: int = 1,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AgentDescriptor:
        descriptor = agent if isinstance(agent, AgentDescriptor) else None
        resolved_id = descriptor.agent_id if descriptor else (agent_id or getattr(agent, "agent_id", ""))
        if not resolved_id:
            raise ValueError("agent_id or an AgentDescriptor with an ID is required")
        if descriptor is None:
            resolved_name = name or getattr(agent, "name", resolved_id)
            descriptor = AgentDescriptor(
                agent_id=resolved_id,
                name=resolved_name,
                role=role,
                capabilities=sorted(set(capabilities or [])),
                priority=priority,
                max_workload=max_workload,
                metadata=dict(metadata or {}),
            )
        self.registry.register_agent(descriptor)
        self.bus.register_inbox(resolved_id)
        self.capability_manager.register(
            resolved_id,
            skills=capabilities or descriptor.capabilities,
            languages=languages,
            domains=domains,
            preferred_workloads=preferred_workloads,
        )
        selected_handler = handler or self._find_handler(agent)
        if selected_handler is not None:
            with self._lock:
                self._handlers[resolved_id] = selected_handler
        return descriptor

    def remove_agent(self, agent_id: str) -> bool:
        with self._lock:
            removed = self.registry.remove_agent(agent_id)
            if removed:
                self._handlers.pop(agent_id, None)
                self.bus.remove_inbox(agent_id)
            return removed

    def discover(
        self,
        capability: Optional[str] = None,
        required_capabilities: Optional[list[str]] = None,
        required_languages: Optional[list[str]] = None,
        required_domains: Optional[list[str]] = None,
        available_only: bool = True,
    ) -> list[AgentDescriptor]:
        skills = list(required_capabilities or [])
        if capability:
            skills.append(capability)
        results = self.capability_manager.discover(
            skills=skills,
            languages=required_languages,
            domains=required_domains,
            available_only=available_only,
        )
        return [item["agent"] for item in results]

    def dispatch(
        self,
        task: Any,
        required_capabilities: Optional[list[str]] = None,
        timeout: Optional[float] = None,
        record_metrics: bool = True,
        execute_handler: bool = True,
    ) -> dict[str, Any]:
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must not be negative")
        negotiation = self.negotiator.negotiate(task, required_capabilities)
        if not negotiation.agent_id:
            raise RuntimeError(negotiation.reason)
        agent_id = negotiation.agent_id
        handler = self._handlers.get(agent_id)
        payload = self._task_payload(task)
        message = self.bus.publish(
            AgentMessageType.TASK_REQUEST,
            sender="multi_agent_runtime",
            receiver=agent_id,
            payload=payload,
        )
        if not execute_handler:
            return {
                "agent_id": agent_id,
                "message_id": message.message_id,
                "status": "queued",
                "negotiation": negotiation.to_dict(),
            }
        if handler is None:
            return {
                "agent_id": agent_id,
                "message_id": message.message_id,
                "status": "queued",
                "negotiation": negotiation.to_dict(),
            }
        self.registry.update_workload(agent_id, 1)
        self.registry.set_status(agent_id, AgentStatus.BUSY)
        try:
            future = self._executor.submit(handler, task)
            result = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            if future.cancel():
                self.registry.record_completion(
                    agent_id,
                    success=False,
                    duration=timeout or 0.0,
                )
            else:
                future.add_done_callback(
                    lambda _: self.registry.record_completion(
                        agent_id,
                        success=False,
                        duration=timeout or 0.0,
                    )
                )
            raise TimeoutError(f"Agent {agent_id!r} did not complete task before timeout")
        except Exception:
            self.registry.record_completion(agent_id, success=False, duration=0.0)
            raise
        else:
            self.registry.record_completion(agent_id, success=True, duration=0.0)
            if record_metrics and self.metrics_tracker is not None:
                self.metrics_tracker.record(agent_id, success=True)
            self.bus.acknowledge(message.message_id)
            return {
                "agent_id": agent_id,
                "message_id": message.message_id,
                "status": "completed",
                "result": result,
                "negotiation": negotiation.to_dict(),
            }

    def broadcast(
        self,
        message: Any,
        payload: Optional[dict[str, Any]] = None,
        message_type: AgentMessageType | str = AgentMessageType.SYSTEM_EVENT,
    ) -> Any:
        if isinstance(message, str):
            sender = message
            body = payload or {}
        else:
            sender = "multi_agent_runtime"
            body = self._task_payload(message)
        return self.bus.broadcast(sender, body, message_type)

    def get_status(self, agent_id: Optional[str] = None) -> Any:
        if agent_id is not None:
            descriptor = self.registry.get_agent(agent_id)
            return descriptor.to_dict() if descriptor else None
        return {
            "agents": [agent.to_dict() for agent in self.registry.get_all_agents()],
            "agent_count": int(self.registry.count),
            "messages": len(self.bus.history()),
        }

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    @staticmethod
    def _task_payload(task: Any) -> dict[str, Any]:
        if isinstance(task, dict):
            return dict(task)
        if hasattr(task, "to_dict"):
            return task.to_dict()
        if hasattr(task, "__dict__"):
            return dict(task.__dict__)
        return {"task": str(task)}

    @staticmethod
    def _find_handler(agent: Any) -> Optional[Callable[[Any], Any]]:
        for method_name in ("handle_task", "execute_task", "process_task", "run_task"):
            method = getattr(agent, method_name, None)
            if callable(method):
                return method
        return agent if callable(agent) else None
