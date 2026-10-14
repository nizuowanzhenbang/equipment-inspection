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
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.defect import Defect, DefectSeverity
from app.models.safety_outbox import SafetyOutbox

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


def _reference(value):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= 50
            and all(ord(char) >= 32 for char in value))


def _lock_defect(db, did):
    db.query(Defect).filter(Defect.id == did).update(
        {Defect.updated_at: Defect.updated_at}, synchronize_session=False)
    return db.query(Defect).filter(Defect.id == did).populate_existing().first()


def _message(db, d):
    row = db.get(SafetyOutbox, d.id)
    if row is None:
        row = SafetyOutbox(defect_id=d.id, payload=_build_payload(d))
        db.add(row)
        db.flush()
    return row


def mark_pending(db: Session, d: Defect) -> None:
    """与 CRITICAL 缺陷一起提交原消息，未配置端点也保留原始事件。"""
    if not should_sync(d):
        d.safety_sync_status = SAFETY_SYNC_SKIPPED
    else:
        _message(db, d)
        if not settings.SAFETY_SYSTEM_URL:
            d.safety_sync_status = SAFETY_SYNC_SKIPPED
            d.safety_sync_error = "SAFETY_SYSTEM_URL 未配置"
        else:
            d.safety_sync_status = SAFETY_SYNC_PENDING
            d.safety_sync_error = None
    db.flush()


class DeliveryError(Exception):
    """仅允许受控的联动原因进入业务记录。"""


def push_one(db: Session, d: Defect) -> bool:
    """原消息可重发；串行投递并核对身份，未持久确认绝不返回成功。"""
    did = d.id
    d = _lock_defect(db, did)
    if d is None:
        db.rollback()
        return False
    if d.safety_sync_status == SAFETY_SYNC_SYNCED and _reference(d.safety_hazard_no):
        db.commit()
        return True
    if not should_sync(d):
        d.safety_sync_status = SAFETY_SYNC_SKIPPED
        db.commit()
        return False
    _message(db, d)
    if not settings.SAFETY_SYSTEM_URL:
        d.safety_sync_status = SAFETY_SYNC_SKIPPED
        d.safety_sync_error = "SAFETY_SYSTEM_URL 未配置"
        db.commit()
        return False
    # 历史消息先提交，再开始网络；已有 outbox 不重新构造。
    d.safety_sync_status = SAFETY_SYNC_PENDING
    db.commit()
    d = _lock_defect(db, did)
    if d.safety_sync_status == SAFETY_SYNC_SYNCED and _reference(d.safety_hazard_no):
        db.commit()
        return True
    payload = db.get(SafetyOutbox, did).payload
    d.safety_sync_attempts = (d.safety_sync_attempts or 0) + 1
    success = False
    try:
        response = httpx.post(settings.SAFETY_SYSTEM_URL.rstrip("/")+"/api/integration/hazards",
                              json=payload, headers={"X-Integration-Secret": settings.INTEGRATION_SECRET},
                              timeout=settings.INTEGRATION_TIMEOUT_SEC, follow_redirects=False)
        if response.status_code != 200:
            raise DeliveryError(f"HTTP {response.status_code}")
        body = response.json()
        data = body.get('data') if isinstance(body, dict) else None
        if (not isinstance(body, dict) or body.get('code') != 200 or not isinstance(data, dict)
                or type(data.get('id')) is not int or data['id'] <= 0
                or not _reference(data.get('hazard_no'))):
            raise DeliveryError("联动回执缺少有效隐患引用")
        if (data.get('source_system') != payload['source_system']
                or data.get('external_no') != payload['external_no']):
            raise DeliveryError("联动回执来源或单号不匹配")
        d.safety_hazard_no = data['hazard_no'].strip()
        d.safety_sync_status = SAFETY_SYNC_SYNCED
        d.safety_sync_at = datetime.utcnow()
        d.safety_sync_error = None
        success = True
    except DeliveryError as exc:
        d.safety_sync_status = SAFETY_SYNC_FAILED
        d.safety_sync_error = str(exc)
    except httpx.HTTPError as exc:
        d.safety_sync_status = SAFETY_SYNC_FAILED
        d.safety_sync_error = f"网络请求失败（{type(exc).__name__}）"
    except (ValueError, TypeError):
        d.safety_sync_status = SAFETY_SYNC_FAILED
        d.safety_sync_error = "联动回执格式不正确"
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[safety_sync] local confirmation was not saved; queued message remains")
        return False
    return success


def retry_pending(db: Session, limit: int = 50) -> dict:
    """分段核对历史引用，limit 只限制待投递项，正常成功项不占名额。"""
    rows, after_id = [], 0
    while len(rows) < limit:
        page = db.query(Defect).filter(
            Defect.id > after_id, Defect.severity == DefectSeverity.CRITICAL,
            Defect.safety_sync_status.in_([SAFETY_SYNC_PENDING, SAFETY_SYNC_FAILED, SAFETY_SYNC_SYNCED]),
        ).order_by(Defect.id.asc()).limit(100).all()
        if not page:
            break
        after_id = page[-1].id
        for item in page:
            if item.safety_sync_status != SAFETY_SYNC_SYNCED or not _reference(item.safety_hazard_no):
                rows.append(item)
                if len(rows) == limit:
                    break
    ok = fail = 0
    for d in rows:
        if push_one(db, d):
            ok += 1
        else:
            fail += 1
    return {"scanned": len(rows), "synced": ok, "failed": fail}
