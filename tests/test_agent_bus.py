from core.agent_bus import AgentBus, AgentMessageType


def test_priority_order_and_fifo_ties() -> None:
    bus = AgentBus()
    first = bus.publish(AgentMessageType.STATUS, "sender", "worker", {"n": 1})
    bus.publish(AgentMessageType.STATUS, "sender", "worker", {"n": 2}, priority=3)
    third = bus.publish(AgentMessageType.STATUS, "sender", "worker", {"n": 3})

    assert bus.receive("worker").payload == {"n": 2}
    assert bus.receive("worker").message_id == first.message_id
    assert bus.receive("worker").message_id == third.message_id


def test_broadcast_subscription_acknowledgement_and_request_response() -> None:
    bus = AgentBus()
    received = []
    bus.register_inbox("worker")
    bus.subscribe(AgentMessageType.LEARNING_EVENT, received.append)
    def respond(message) -> None:
        bus.publish(
            "TASK_RESULT",
            "worker",
            message.sender,
            {"ok": True},
            correlation_id=message.message_id,
        )

    bus.subscribe(AgentMessageType.TASK_REQUEST, respond)
    event = bus.broadcast("orchestrator", {"status": "done"}, "LEARNING_EVENT")
    assert received[0].message_id == event.message_id
    assert bus.receive("worker").message_id == event.message_id
    assert bus.acknowledge(event.message_id)
    assert bus.history()[0].acknowledged

    response = bus.send_request("caller", "worker", timeout=0.1)
    assert response is not None
    assert response.payload == {"ok": True}
