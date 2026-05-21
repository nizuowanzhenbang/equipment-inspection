"""WebSocket 推送：缺陷 CRITICAL 新建 / OVERDUE 标记 等事件实时通知前端。

设计：
- 单进程内的 ConnectionManager（够 v2 + 小规模生产用，多实例需要换 Redis pubsub）
- 鉴权：握手时 query token=...，验证后保留连接
- 客户端订阅频道：global（全局通知）。后续可扩展按用户名订阅。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.config import settings

logger = logging.getLogger("equipment_inspection.ws")

# 事件类型常量
EVT_DEFECT_CRITICAL = "defect.critical_created"
EVT_DEFECT_OVERDUE = "defect.overdue_swept"
EVT_TASK_MISSED = "task.missed_swept"
EVT_SAFETY_SYNCED = "defect.safety_synced"
EVT_SAFETY_FAILED = "defect.safety_sync_failed"


class ConnectionManager:
    def __init__(self) -> None:
        self._conns: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        # 跨线程（调度器/同步代码）→ 异步广播：缓存事件，由后台 task 抽取
        self._pending: list[dict] = []
        self._pending_lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, username: str) -> None:
        await ws.accept()
        async with self._lock:
            self._conns.add(ws)
        logger.info("[ws] %s 已连接，当前连接数=%d", username, len(self._conns))
        await ws.send_json({"event": "system.welcome", "ts": datetime.utcnow().isoformat(), "data": {"username": username}})

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._conns.discard(ws)

    async def broadcast(self, event: str, data: dict) -> None:
        msg = {"event": event, "ts": datetime.utcnow().isoformat(), "data": data}
        dead: list[WebSocket] = []
        async with self._lock:
            targets = list(self._conns)
        for ws in targets:
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._conns.discard(ws)

    # 同步代码（调度器线程、HTTP 请求）落事件 → 由后台 task 异步广播
    def emit_sync(self, event: str, data: dict) -> None:
        self._pending.append({"event": event, "data": data})

    async def drain_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            if not self._pending:
                continue
            batch = self._pending[:]
            self._pending.clear()
            for item in batch:
                try:
                    await self.broadcast(item["event"], item["data"])
                except Exception as e:  # noqa: BLE001
                    logger.warning("[ws] broadcast 失败: %s", e)


manager = ConnectionManager()


def authenticate_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


async def ws_endpoint(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    username = authenticate_token(token)
    if not username:
        await websocket.close(code=4401)
        return
    await manager.connect(websocket, username)
    try:
        while True:
            # 接收客户端 ping/订阅指令；目前忽略具体内容
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)


# 便捷封装：同步上下文调用
def emit_defect_critical(defect) -> None:
    manager.emit_sync(EVT_DEFECT_CRITICAL, {
        "defect_no": defect.defect_no,
        "equipment_code": defect.equipment.code if defect.equipment else None,
        "equipment_name": defect.equipment.name if defect.equipment else None,
        "title": defect.title,
        "severity": defect.severity.value if hasattr(defect.severity, "value") else defect.severity,
        "reported_by": defect.reported_by,
    })


def emit_overdue_swept(count: int, defect_nos: list[str]) -> None:
    if count <= 0:
        return
    manager.emit_sync(EVT_DEFECT_OVERDUE, {"count": count, "defects": defect_nos[:20]})


def emit_missed_swept(count: int, task_nos: list[str]) -> None:
    if count <= 0:
        return
    manager.emit_sync(EVT_TASK_MISSED, {"count": count, "tasks": task_nos[:20]})


def emit_safety_synced(defect_no: str, hazard_no: Optional[str]) -> None:
    manager.emit_sync(EVT_SAFETY_SYNCED, {"defect_no": defect_no, "hazard_no": hazard_no})


def emit_safety_failed(defect_no: str, error: Optional[str]) -> None:
    manager.emit_sync(EVT_SAFETY_FAILED, {"defect_no": defect_no, "error": error})
