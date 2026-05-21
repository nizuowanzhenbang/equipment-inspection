"""与 plant-safety 系统的对接：CRITICAL 缺陷自动同步建隐患单。

约定：
- 调用 plant-safety 的 POST {SAFETY_SYSTEM_URL}/api/integration/hazards
- Header: X-Integration-Secret: <INTEGRATION_SECRET>
- 成功返回 {code:200, data:{hazard_no:"HZ-...."}}，写回缺陷的 safety_hazard_no
- 失败/超时 → 写 safety_sync_status=FAILED，记 error，由调度器重试
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.defect import Defect, DefectSeverity

logger = logging.getLogger("equipment_inspection.integration")

SAFETY_SYNC_PENDING = "PENDING"
SAFETY_SYNC_SYNCED = "SYNCED"
SAFETY_SYNC_FAILED = "FAILED"
SAFETY_SYNC_SKIPPED = "SKIPPED"


def _build_payload(d: Defect) -> dict:
    eq = d.equipment
    return {
        "external_no": d.defect_no,
        "source_system": "equipment-inspection",
        "title": d.title,
        "description": d.description or "",
        "severity": d.severity.value,                              # MINOR/MAJOR/CRITICAL
        "equipment_code": eq.code if eq else None,
        "equipment_name": eq.name if eq else None,
        "location": eq.location if eq and hasattr(eq, "location") else None,
        "reported_by": d.reported_by,
        "reported_at": d.reported_at.isoformat() if d.reported_at else None,
        "sla_deadline": d.sla_deadline.isoformat() if d.sla_deadline else None,
    }


def should_sync(d: Defect) -> bool:
    """只有 CRITICAL 缺陷需要联动建隐患单。"""
    return d.severity == DefectSeverity.CRITICAL


def mark_pending(db: Session, d: Defect) -> None:
    """标记缺陷待联动（在 defect 落库后立即调用，便于失败时定时重试）"""
    if not should_sync(d):
        d.safety_sync_status = SAFETY_SYNC_SKIPPED
    elif not settings.SAFETY_SYSTEM_URL:
        d.safety_sync_status = SAFETY_SYNC_SKIPPED
        d.safety_sync_error = "SAFETY_SYSTEM_URL 未配置"
    else:
        d.safety_sync_status = SAFETY_SYNC_PENDING
    db.flush()


def push_one(db: Session, d: Defect) -> bool:
    """同步推送一条缺陷到 plant-safety。返回是否成功。"""
    if d.safety_sync_status == SAFETY_SYNC_SYNCED:
        return True
    if not should_sync(d):
        d.safety_sync_status = SAFETY_SYNC_SKIPPED
        db.commit()
        return True
    if not settings.SAFETY_SYSTEM_URL:
        d.safety_sync_status = SAFETY_SYNC_SKIPPED
        d.safety_sync_error = "SAFETY_SYSTEM_URL 未配置"
        db.commit()
        return False

    url = settings.SAFETY_SYSTEM_URL.rstrip("/") + "/api/integration/hazards"
    headers = {
        "X-Integration-Secret": settings.INTEGRATION_SECRET,
        "Content-Type": "application/json",
    }
    payload = _build_payload(d)
    d.safety_sync_attempts = (d.safety_sync_attempts or 0) + 1
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=settings.INTEGRATION_TIMEOUT_SEC)
        if resp.status_code >= 400:
            d.safety_sync_status = SAFETY_SYNC_FAILED
            d.safety_sync_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            db.commit()
            logger.warning("[safety_sync] %s HTTP %s", d.defect_no, resp.status_code)
            return False
        body = resp.json() if resp.content else {}
        data = body.get("data") or {}
        d.safety_hazard_no = data.get("hazard_no")
        d.safety_sync_status = SAFETY_SYNC_SYNCED
        d.safety_sync_at = datetime.utcnow()
        d.safety_sync_error = None
        db.commit()
        logger.info("[safety_sync] %s -> %s", d.defect_no, d.safety_hazard_no)
        return True
    except Exception as e:  # noqa: BLE001
        d.safety_sync_status = SAFETY_SYNC_FAILED
        d.safety_sync_error = f"{type(e).__name__}: {str(e)[:200]}"
        db.commit()
        logger.warning("[safety_sync] %s 异常: %s", d.defect_no, e)
        return False


def retry_pending(db: Session, limit: int = 50) -> dict:
    """扫描 PENDING/FAILED 的待联动缺陷重试。"""
    rows = (
        db.query(Defect)
        .filter(
            Defect.severity == DefectSeverity.CRITICAL,
            Defect.safety_sync_status.in_([SAFETY_SYNC_PENDING, SAFETY_SYNC_FAILED]),
        )
        .order_by(Defect.created_at.asc())
        .limit(limit)
        .all()
    )
    ok, fail = 0, 0
    for d in rows:
        if push_one(db, d):
            ok += 1
        else:
            fail += 1
    return {"scanned": len(rows), "synced": ok, "failed": fail}
