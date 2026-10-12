"""Deterministic priority message bus for collaborating engineering agents."""

from __future__ import annotations

import copy
import heapq
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class AgentMessageType(str, Enum):
    TASK_REQUEST = "TASK_REQUEST"
    TASK_RESULT = "TASK_RESULT"
    QUESTION = "QUESTION"
    ANSWER = "ANSWER"
    ERROR = "ERROR"
    STATUS = "STATUS"
    LEARNING_EVENT = "LEARNING_EVENT"
    SYSTEM_EVENT = "SYSTEM_EVENT"


@dataclass
class AgentMessage:
    message_id: str
    message_type: AgentMessageType
    sender: str
    receiver: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    correlation_id: Optional[str] = None
    acknowledged: bool = False
    created_sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "sender": self.sender,
            "receiver": self.receiver,
            "payload": copy.deepcopy(self.payload),
            "priority": self.priority,
            "correlation_id": self.correlation_id,
            "acknowledged": self.acknowledged,
            "created_sequence": self.created_sequence,
        }


RequestMessage = AgentMessage
ResponseMessage = AgentMessage
BroadcastEvent = AgentMessage


class AgentBus:
    """Routes typed messages and delivers each inbox in priority/FIFO order."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._sequence = 0
        self._inboxes: dict[str, list[tuple[int, int, AgentMessage]]] = {}
        self._history: list[AgentMessage] = []
        self._subscribers: dict[AgentMessageType, list[Callable[[AgentMessage], None]]] = {}
        self._pending_responses: dict[str, AgentMessage] = {}

    def subscribe(
        self,
        message_type: AgentMessageType | str,
        handler: Callable[[AgentMessage], None],
    ) -> None:
        kind = self._message_type(message_type)
        with self._lock:
            self._subscribers.setdefault(kind, []).append(handler)

    def register_inbox(self, agent_id: str) -> None:
        if not agent_id:
            raise ValueError("agent_id must not be empty")
        with self._lock:
            self._inboxes.setdefault(agent_id, [])

    def unsubscribe(
        self,
        message_type: AgentMessageType | str,
        handler: Callable[[AgentMessage], None],
    ) -> bool:
        kind = self._message_type(message_type)
        with self._lock:
            handlers = self._subscribers.get(kind, [])
            if handler not in handlers:
                return False
            handlers.remove(handler)
            return True

    def remove_inbox(self, agent_id: str) -> bool:
        """Removes an agent's queued messages and inbox."""
        with self._condition:
            removed = self._inboxes.pop(agent_id, None) is not None
            self._condition.notify_all()
            return removed

    def publish(
        self,
        message_type: AgentMessageType | str,
        sender: str,
        receiver: str,
        payload: Optional[dict[str, Any]] = None,
        priority: int = 0,
        correlation_id: Optional[str] = None,
    ) -> AgentMessage:
        if not sender or not receiver:
            raise ValueError("sender and receiver are required")
        kind = self._message_type(message_type)
        if not isinstance(priority, int):
            raise TypeError("priority must be an integer")
        with self._condition:
            self._sequence += 1
            message = AgentMessage(
                message_id=f"agent-msg-{self._sequence:08d}",
                message_type=kind,
                sender=sender,
                receiver=receiver,
                payload=copy.deepcopy(payload or {}),
                priority=priority,
                correlation_id=correlation_id,
                created_sequence=self._sequence,
            )
            self._history.append(copy.deepcopy(message))
            if kind == AgentMessageType.TASK_RESULT and correlation_id:
                self._pending_responses[correlation_id] = copy.deepcopy(message)
            if receiver == "*":
                targets = sorted(self._inboxes)
                for subscriber_type in (kind,):
                    handlers = list(self._subscribers.get(subscriber_type, []))
            else:
                targets = [receiver]
                handlers = list(self._subscribers.get(kind, []))
                self._inboxes.setdefault(receiver, [])
            for target in targets:
                heapq.heappush(
                    self._inboxes.setdefault(target, []),
                    (-priority, self._sequence, copy.deepcopy(message)),
                )
            self._condition.notify_all()
        for handler in handlers:
            handler(copy.deepcopy(message))
        return copy.deepcopy(message)

    def send_request(
        self,
        sender: str,
        receiver: str,
        payload: Optional[dict[str, Any]] = None,
        timeout: float = 5.0,
        priority: int = 0,
    ) -> Optional[AgentMessage]:
        if timeout < 0:
            raise ValueError("timeout must not be negative")
        request = self.publish(
            AgentMessageType.TASK_REQUEST, sender, receiver, payload, priority
        )
        deadline = time.monotonic() + timeout
        with self._condition:
            while request.message_id not in self._pending_responses:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            return copy.deepcopy(self._pending_responses.pop(request.message_id))

    def receive(self, agent_id: str, timeout: Optional[float] = None) -> Optional[AgentMessage]:
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must not be negative")
        deadline = time.monotonic() + timeout if timeout is not None else None
        with self._condition:
            inbox = self._inboxes.setdefault(agent_id, [])
            while not inbox:
                if deadline is None:
                    self._condition.wait()
                else:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    self._condition.wait(remaining)
            return copy.deepcopy(heapq.heappop(inbox)[2])

    def acknowledge(self, message_id: str) -> bool:
        with self._lock:
            for message in self._history:
                if message.message_id == message_id:
                    message.acknowledged = True
                    return True
            return False

    def broadcast(
        self,
        sender: str,
        payload: Optional[dict[str, Any]] = None,
        message_type: AgentMessageType | str = AgentMessageType.SYSTEM_EVENT,
        priority: int = 0,
    ) -> AgentMessage:
        return self.publish(message_type, sender, "*", payload, priority)

    def history(self, limit: Optional[int] = None) -> list[AgentMessage]:
        with self._lock:
            messages = self._history if limit is None else self._history[-max(0, limit):]
            return copy.deepcopy(messages)

    def inbox_size(self, agent_id: str) -> int:
        with self._lock:
            return len(self._inboxes.get(agent_id, []))

    @staticmethod
    def _message_type(value: AgentMessageType | str) -> AgentMessageType:
        return value if isinstance(value, AgentMessageType) else AgentMessageType(value)
