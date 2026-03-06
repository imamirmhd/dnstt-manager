"""WebSocket endpoint for real-time dashboard updates."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.system_monitor import system_monitor

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        # Background task to push system stats
        async def push_stats():
            while True:
                try:
                    stats = await system_monitor.async_snapshot()
                    await ws.send_json({"type": "system_stats", "data": stats.model_dump()})
                except Exception:
                    break
                await asyncio.sleep(settings.system_monitor_interval)

        stats_task = asyncio.create_task(push_stats())
        try:
            while True:
                # Keep connection alive, handle incoming messages
                msg = await ws.receive_text()
                # Clients can request specific data
                try:
                    request = json.loads(msg)
                    if request.get("type") == "ping":
                        await ws.send_json({"type": "pong"})
                except json.JSONDecodeError:
                    pass
        finally:
            stats_task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(ws)
