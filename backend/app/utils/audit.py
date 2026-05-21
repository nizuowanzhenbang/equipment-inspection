"""审计日志工具：在 API 内一行落审计"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditLog

logger = logging.getLogger("equipment_inspection.audit")


def log(
    db: Session,
    *,
    actor: Optional[str],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    target_no: Optional[str] = None,
    summary: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """记录一条审计日志。失败不抛异常（审计不应阻塞业务）。"""
    try:
        entry = AuditLog(
            actor=actor, action=action,
            target_type=target_type, target_id=target_id, target_no=target_no,
            summary=summary, extra=extra,
        )
        db.add(entry)
        db.flush()
    except Exception as e:  # noqa: BLE001
        logger.warning("[audit] %s 落表失败: %s", action, e)
