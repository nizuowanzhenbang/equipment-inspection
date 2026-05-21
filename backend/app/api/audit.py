"""审计日志查看 API（ADMIN-only）"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.audit import AuditLog
from app.models.user import User
from app.utils.helpers import api_response, paginate_response

router = APIRouter(prefix="/api/audit", tags=["审计日志"])


@router.get("")
def list_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    actor: Optional[str] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(AuditLog)
    if actor:
        q = q.filter(AuditLog.actor == actor)
    if action:
        q = q.filter(AuditLog.action.like(f"{action}%"))
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter((AuditLog.summary.like(like)) | (AuditLog.target_no.like(like)))
    total = q.count()
    rows = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [
        {
            "id": r.id, "actor": r.actor, "action": r.action,
            "target_type": r.target_type, "target_id": r.target_id, "target_no": r.target_no,
            "summary": r.summary, "extra": r.extra,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return api_response(data=paginate_response(items, total, page, page_size))
