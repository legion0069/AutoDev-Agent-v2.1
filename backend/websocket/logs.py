"""Durable, resumable project-log WebSocket endpoint."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/logs")
async def stream_logs(websocket: WebSocket) -> None:
    await websocket.accept()
    service = websocket.app.state.project_service
    try:
        after = max(0, int(websocket.query_params.get("after", "0")))
    except ValueError:
        after = 0

    queue, unsubscribe = service.subscribe()
    last_event_id = after
    try:
        while True:
            backlog = service.get_logs(after=last_event_id, limit=2000)
            if not backlog:
                break
            for event in backlog:
                await websocket.send_json(event)
                last_event_id = max(last_event_id, event["event_id"])

        while True:
            event = await queue.get()
            if event["event_id"] <= last_event_id:
                continue
            await websocket.send_json(event)
            last_event_id = event["event_id"]
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        raise
    finally:
        unsubscribe()
