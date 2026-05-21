"""缺陷工单 API：NEW → ASSIGNED → IN_REPAIR → REPAIRED → VERIFIED → CLOSED"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import (
    get_db, get_current_user, require_write,
    require_supervisor, require_repairman,
)
from app.config import settings
from app.models.equipment import Equipment, EquipmentStatus
from app.models.defect import Defect, DefectSource, DefectSeverity, DefectStatus
from app.models.user import User
from app.schemas.defect import DefectCreate, DefectAssign, DefectRepair, DefectVerify, DefectResponse
from app.utils.helpers import api_response, paginate_response, generate_defect_no
from app.integration.safety_client import mark_pending, push_one, should_sync
from app.realtime import emit_defect_critical, emit_safety_synced, emit_safety_failed
from app.utils.audit import log as audit_log

router = APIRouter(prefix="/api/defects", tags=["缺陷工单"])


def _to_dict(d: Defect) -> dict:
    data = DefectResponse.model_validate(d).model_dump(mode="json")
    if d.equipment:
        data["equipment_name"] = d.equipment.name
        data["equipment_code"] = d.equipment.code
    return data


def _sla_deadline(severity: DefectSeverity) -> datetime:
    hours_map = {
        DefectSeverity.MINOR: settings.DEFECT_SLA_MINOR,
        DefectSeverity.MAJOR: settings.DEFECT_SLA_MAJOR,
        DefectSeverity.CRITICAL: settings.DEFECT_SLA_CRITICAL,
    }
    return datetime.utcnow() + timedelta(hours=hours_map[severity])


@router.get("")
def list_defects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[DefectStatus] = None,
    severity: Optional[DefectSeverity] = None,
    source: Optional[DefectSource] = None,
    equipment_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Defect).options(joinedload(Defect.equipment))
    if status:
        q = q.filter(Defect.status == status)
    if severity:
        q = q.filter(Defect.severity == severity)
    if source:
        q = q.filter(Defect.source == source)
    if equipment_id:
        q = q.filter(Defect.equipment_id == equipment_id)
    total = q.count()
    rows = q.order_by(Defect.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [_to_dict(r) for r in rows]
    return api_response(data=paginate_response(items, total, page, page_size))


@router.post("")
def create_defect(
    payload: DefectCreate, db: Session = Depends(get_db), current: User = Depends(require_write),
):
    eq = db.query(Equipment).filter(Equipment.id == payload.equipment_id).first()
    if not eq:
        raise HTTPException(404, "设备不存在")
    next_seq = (
        db.query(func.count(Defect.id))
        .filter(func.date(Defect.created_at) == datetime.utcnow().date())
        .scalar() or 0
    ) + 1
    d = Defect(
        defect_no=generate_defect_no(next_seq),
        equipment_id=eq.id,
        source=DefectSource.MANUAL,
        severity=payload.severity,
        status=DefectStatus.NEW,
        title=payload.title,
        description=payload.description,
        photo_url=payload.photo_url,
        reported_by=current.username,
        sla_deadline=_sla_deadline(payload.severity),
    )
    db.add(d)
    db.flush()
    mark_pending(db, d)
    audit_log(db, actor=current.username, action="defect.create",
              target_type="Defect", target_id=d.id, target_no=d.defect_no,
              summary=f"上报{d.severity.value}缺陷：{d.title[:60]}")
    db.commit()
    db.refresh(d)
    if d.severity == DefectSeverity.CRITICAL:
        emit_defect_critical(d)
    # CRITICAL → 立即尝试推送 plant-safety；失败也不阻塞，调度器会重试
    if should_sync(d):
        ok = push_one(db, d)
        db.refresh(d)
        if ok:
            emit_safety_synced(d.defect_no, d.safety_hazard_no)
        else:
            emit_safety_failed(d.defect_no, d.safety_sync_error)
    return api_response(message="缺陷已上报", data=_to_dict(d))


@router.get("/{did}")
def get_defect(did: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    d = db.query(Defect).options(joinedload(Defect.equipment)).filter(Defect.id == did).first()
    if not d:
        raise HTTPException(404, "缺陷不存在")
    return api_response(data=_to_dict(d))


@router.post("/{did}/assign")
def assign(did: int, payload: DefectAssign, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    d = db.query(Defect).filter(Defect.id == did).first()
    if not d:
        raise HTTPException(404, "缺陷不存在")
    if d.status not in (DefectStatus.NEW, DefectStatus.OVERDUE):
        raise HTTPException(400, f"状态 {d.status.value} 不可派工")
    d.status = DefectStatus.ASSIGNED
    d.assigned_to = payload.assigned_to
    d.assigned_at = datetime.utcnow()
    d.assigned_by = current.username
    if payload.notes:
        d.repair_notes = (d.repair_notes or "") + f"[派工备注] {payload.notes}\n"
    audit_log(db, actor=current.username, action="defect.assign",
              target_type="Defect", target_id=d.id, target_no=d.defect_no,
              summary=f"派工给 {payload.assigned_to}")
    db.commit()
    return api_response(message=f"已派工给 {payload.assigned_to}")


@router.post("/{did}/start-repair")
def start_repair(did: int, db: Session = Depends(get_db), current: User = Depends(require_repairman)):
    d = db.query(Defect).filter(Defect.id == did).first()
    if not d:
        raise HTTPException(404, "缺陷不存在")
    if d.status != DefectStatus.ASSIGNED:
        raise HTTPException(400, f"状态 {d.status.value} 不可开始检修")
    d.status = DefectStatus.IN_REPAIR
    d.repair_started_at = datetime.utcnow()
    db.commit()
    return api_response(message="已开始检修")


@router.post("/{did}/repair")
def repair(did: int, payload: DefectRepair, db: Session = Depends(get_db), current: User = Depends(require_repairman)):
    d = db.query(Defect).filter(Defect.id == did).first()
    if not d:
        raise HTTPException(404, "缺陷不存在")
    if d.status not in (DefectStatus.ASSIGNED, DefectStatus.IN_REPAIR):
        raise HTTPException(400, f"状态 {d.status.value} 不可提交修复")
    d.status = DefectStatus.REPAIRED
    d.repair_started_at = d.repair_started_at or datetime.utcnow()
    d.repair_completed_at = datetime.utcnow()
    d.repair_notes = (d.repair_notes or "") + f"[修复记录] {payload.repair_notes}\n"
    d.repair_cost = (d.repair_cost or 0) + payload.repair_cost
    db.commit()
    return api_response(message="已提交修复，待验收")


@router.post("/{did}/verify")
def verify(did: int, payload: DefectVerify, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    d = db.query(Defect).options(joinedload(Defect.equipment)).filter(Defect.id == did).first()
    if not d:
        raise HTTPException(404, "缺陷不存在")
    if d.status != DefectStatus.REPAIRED:
        raise HTTPException(400, f"状态 {d.status.value} 不可验收")
    if payload.pass_:
        d.status = DefectStatus.VERIFIED
        d.verified_by = current.username
        d.verified_at = datetime.utcnow()
        d.verify_notes = payload.verify_notes
        d.closed_at = datetime.utcnow()
        # 缺陷验收通过 → 若是该设备唯一未结缺陷，设备恢复运行 + 健康度回弹
        eq = d.equipment
        if eq:
            open_count = (
                db.query(func.count(Defect.id))
                .filter(
                    Defect.equipment_id == eq.id,
                    Defect.status.notin_([DefectStatus.VERIFIED, DefectStatus.CLOSED, DefectStatus.CANCELLED]),
                )
                .scalar() or 0
            )
            if open_count <= 1:  # 包括自己
                if eq.status == EquipmentStatus.MAINTENANCE:
                    eq.status = EquipmentStatus.RUNNING
            recover = 10 if d.severity == DefectSeverity.CRITICAL else (6 if d.severity == DefectSeverity.MAJOR else 3)
            eq.health_score = min(100, (eq.health_score or 0) + recover)
        d.status = DefectStatus.CLOSED  # 验收即关闭
        msg = "已验收并关闭"
        audit_log(db, actor=current.username, action="defect.verify_pass",
                  target_type="Defect", target_id=d.id, target_no=d.defect_no,
                  summary=f"验收通过并关闭：{d.title[:60]}")
    else:
        d.status = DefectStatus.IN_REPAIR
        d.verify_notes = (d.verify_notes or "") + f"[验收驳回] {payload.verify_notes or ''}\n"
        msg = "验收未通过，回到检修中"
        audit_log(db, actor=current.username, action="defect.verify_reject",
                  target_type="Defect", target_id=d.id, target_no=d.defect_no,
                  summary=f"验收驳回：{payload.verify_notes or ''}")
    db.commit()
    return api_response(message=msg)


@router.post("/{did}/cancel")
def cancel(did: int, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    d = db.query(Defect).filter(Defect.id == did).first()
    if not d:
        raise HTTPException(404, "缺陷不存在")
    if d.status in (DefectStatus.CLOSED, DefectStatus.VERIFIED):
        raise HTTPException(400, "已关闭/验收缺陷不可取消")
    d.status = DefectStatus.CANCELLED
    db.commit()
    return api_response(message="已取消")


@router.post("/{did}/safety-sync")
def safety_sync(did: int, db: Session = Depends(get_db), _: User = Depends(require_supervisor)):
    """手动重推 plant-safety 联动（CRITICAL 缺陷专用）"""
    d = db.query(Defect).options(joinedload(Defect.equipment)).filter(Defect.id == did).first()
    if not d:
        raise HTTPException(404, "缺陷不存在")
    ok = push_one(db, d)
    db.refresh(d)
    if ok:
        emit_safety_synced(d.defect_no, d.safety_hazard_no)
    else:
        emit_safety_failed(d.defect_no, d.safety_sync_error)
    return api_response(
        message="联动成功" if ok else f"联动失败：{d.safety_sync_error or '未知错误'}",
        data=_to_dict(d),
    )


@router.post("/sweep-overdue")
def sweep_overdue(db: Session = Depends(get_db), _: User = Depends(require_write)):
    """扫描超期未关闭的缺陷，置为 OVERDUE（不阻塞流转，主要给 Dashboard 用）"""
    now = datetime.utcnow()
    rows = (
        db.query(Defect)
        .filter(
            Defect.sla_deadline.isnot(None),
            Defect.sla_deadline < now,
            Defect.status.in_([DefectStatus.NEW, DefectStatus.ASSIGNED, DefectStatus.IN_REPAIR]),
        )
        .all()
    )
    for d in rows:
        d.status = DefectStatus.OVERDUE
    db.commit()
    return api_response(message=f"已标记 {len(rows)} 个超期缺陷", data={"overdue": len(rows)})
