"""点检任务 + 记录 API（点检异常自动联动生成缺陷）"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_current_user, require_inspector, require_write
from app.config import settings
from app.models.equipment import Equipment, Criticality, EquipmentStatus
from app.models.route import InspectionRoute, InspectionPoint
from app.models.task import InspectionTask, TaskStatus, InspectionRecord, PointStatus
from app.models.defect import Defect, DefectSource, DefectSeverity, DefectStatus
from app.models.user import User
from app.schemas.task import TaskGenerate, TaskResponse, RecordSubmit, RecordResponse
from app.utils.helpers import api_response, paginate_response, generate_task_no, generate_defect_no
from app.integration.safety_client import mark_pending, push_one, should_sync
from app.realtime import emit_defect_critical, emit_safety_synced, emit_safety_failed

router = APIRouter(prefix="/api/tasks", tags=["点检任务"])


def _task_to_dict(t: InspectionTask) -> dict:
    data = TaskResponse.model_validate(t).model_dump(mode="json")
    if t.route:
        data["route_name"] = t.route.name
    data["record_count"] = len(t.records or [])
    data["total_points"] = len(t.route.points or []) if t.route else 0
    return data


def _record_to_dict(r: InspectionRecord) -> dict:
    data = RecordResponse.model_validate(r).model_dump(mode="json")
    if r.point:
        data["point_no"] = r.point.point_no
        if r.point.equipment:
            data["equipment_name"] = r.point.equipment.name
    return data


def _decide_severity(eq: Equipment, point_status: PointStatus) -> DefectSeverity:
    if point_status == PointStatus.SEVERE:
        if eq.criticality == Criticality.A:
            return DefectSeverity.CRITICAL
        if eq.criticality == Criticality.B:
            return DefectSeverity.MAJOR
        return DefectSeverity.MAJOR  # C 级 + SEVERE 也算 MAJOR
    # ABNORMAL
    if eq.criticality == Criticality.A:
        return DefectSeverity.MAJOR
    return DefectSeverity.MINOR


def _sla_deadline(severity: DefectSeverity) -> datetime:
    hours_map = {
        DefectSeverity.MINOR: settings.DEFECT_SLA_MINOR,
        DefectSeverity.MAJOR: settings.DEFECT_SLA_MAJOR,
        DefectSeverity.CRITICAL: settings.DEFECT_SLA_CRITICAL,
    }
    return datetime.utcnow() + timedelta(hours=hours_map[severity])


@router.get("")
def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[TaskStatus] = None,
    route_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(InspectionTask).options(
        joinedload(InspectionTask.route).joinedload(InspectionRoute.points),
        joinedload(InspectionTask.records),
    )
    if status:
        q = q.filter(InspectionTask.status == status)
    if route_id:
        q = q.filter(InspectionTask.route_id == route_id)
    total = q.count()
    rows = q.order_by(InspectionTask.scheduled_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [_task_to_dict(t) for t in rows]
    return api_response(data=paginate_response(items, total, page, page_size))


@router.post("/generate")
def generate_task(payload: TaskGenerate, db: Session = Depends(get_db), _: User = Depends(require_write)):
    """按路线生成一条点检任务（也可用 cron 调用）"""
    r = db.query(InspectionRoute).filter(InspectionRoute.id == payload.route_id).first()
    if not r:
        raise HTTPException(404, "路线不存在")
    if not r.is_active:
        raise HTTPException(400, "路线已停用")

    next_seq = (
        db.query(func.count(InspectionTask.id))
        .filter(func.date(InspectionTask.created_at) == datetime.utcnow().date())
        .scalar() or 0
    ) + 1
    task = InspectionTask(
        task_no=generate_task_no(next_seq),
        route_id=r.id,
        scheduled_at=payload.scheduled_at,
        assigned_to=payload.assigned_to,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return api_response(message="任务已生成", data=_task_to_dict(task))


@router.get("/{tid}")
def get_task(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    t = (
        db.query(InspectionTask)
        .options(
            joinedload(InspectionTask.route).joinedload(InspectionRoute.points).joinedload(InspectionPoint.equipment),
            joinedload(InspectionTask.records).joinedload(InspectionRecord.point).joinedload(InspectionPoint.equipment),
        )
        .filter(InspectionTask.id == tid)
        .first()
    )
    if not t:
        raise HTTPException(404, "任务不存在")
    data = _task_to_dict(t)
    data["records"] = [_record_to_dict(r) for r in (t.records or [])]
    data["pending_points"] = [
        {
            "id": p.id, "point_no": p.point_no, "sequence": p.sequence,
            "check_items": p.check_items, "standard": p.standard,
            "equipment_id": p.equipment_id,
            "equipment_name": p.equipment.name if p.equipment else None,
            "equipment_code": p.equipment.code if p.equipment else None,
        }
        for p in (t.route.points if t.route else [])
        if not any(r.point_id == p.id for r in (t.records or []))
    ]
    return api_response(data=data)


@router.post("/{tid}/start")
def start_task(tid: int, db: Session = Depends(get_db), current: User = Depends(require_inspector)):
    t = db.query(InspectionTask).filter(InspectionTask.id == tid).first()
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status != TaskStatus.PENDING:
        raise HTTPException(400, f"任务状态 {t.status.value}，不可开始")
    t.status = TaskStatus.IN_PROGRESS
    t.started_at = datetime.utcnow()
    t.executed_by = current.username
    db.commit()
    return api_response(message="已开始执行")


@router.post("/{tid}/records")
def submit_record(
    tid: int, payload: RecordSubmit,
    db: Session = Depends(get_db), current: User = Depends(require_inspector),
):
    """提交一个测点的检查结果。若异常自动生成缺陷工单，并联回 record.defect_id。"""
    t = db.query(InspectionTask).filter(InspectionTask.id == tid).first()
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status not in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
        raise HTTPException(400, f"任务状态 {t.status.value}，不可录入")

    point = (
        db.query(InspectionPoint)
        .options(joinedload(InspectionPoint.equipment))
        .filter(InspectionPoint.id == payload.point_id, InspectionPoint.route_id == t.route_id)
        .first()
    )
    if not point:
        raise HTTPException(400, "测点不属于本任务路线")
    if db.query(InspectionRecord).filter(
        InspectionRecord.task_id == tid, InspectionRecord.point_id == payload.point_id
    ).first():
        raise HTTPException(400, "该测点已录入过")

    # 任务变为进行中
    if t.status == TaskStatus.PENDING:
        t.status = TaskStatus.IN_PROGRESS
        t.started_at = datetime.utcnow()
        t.executed_by = current.username

    record = InspectionRecord(
        task_id=tid,
        point_id=payload.point_id,
        status=payload.status,
        readings=payload.readings,
        finding=payload.finding,
        photo_url=payload.photo_url,
        recorded_by=current.username,
    )
    db.add(record)
    db.flush()

    # 异常 → 自动生成缺陷
    if payload.status in (PointStatus.ABNORMAL, PointStatus.SEVERE):
        eq = point.equipment
        severity = _decide_severity(eq, payload.status)
        next_seq = (
            db.query(func.count(Defect.id))
            .filter(func.date(Defect.created_at) == datetime.utcnow().date())
            .scalar() or 0
        ) + 1
        title = f"[点检] {eq.name} - {payload.finding or '发现异常'}"[:200]
        defect = Defect(
            defect_no=generate_defect_no(next_seq),
            equipment_id=eq.id,
            source=DefectSource.INSPECTION,
            severity=severity,
            status=DefectStatus.NEW,
            title=title,
            description=payload.finding,
            photo_url=payload.photo_url,
            reported_by=current.username,
            sla_deadline=_sla_deadline(severity),
        )
        db.add(defect)
        db.flush()
        mark_pending(db, defect)
        record.defect_id = defect.id
        t.abnormal_count = (t.abnormal_count or 0) + 1
        # SEVERE + 运行设备 → 转检修
        if payload.status == PointStatus.SEVERE and eq.status == EquipmentStatus.RUNNING:
            eq.status = EquipmentStatus.MAINTENANCE
        # 健康度衰减
        decay = 15 if severity == DefectSeverity.CRITICAL else (8 if severity == DefectSeverity.MAJOR else 3)
        eq.health_score = max(0, (eq.health_score or 100) - decay)
        _critical_sync_target = defect if should_sync(defect) else None
    else:
        _critical_sync_target = None

    # 路线全部录完 → 任务完成
    total_points = len(t.route.points or [])
    recorded = db.query(func.count(InspectionRecord.id)).filter(InspectionRecord.task_id == tid).scalar() or 0
    if recorded >= total_points:
        t.status = TaskStatus.COMPLETED
        t.completed_at = datetime.utcnow()

    db.commit()
    if _critical_sync_target is not None:
        emit_defect_critical(_critical_sync_target)
        ok = push_one(db, _critical_sync_target)   # 失败不阻塞，调度器重试
        if ok:
            emit_safety_synced(_critical_sync_target.defect_no, _critical_sync_target.safety_hazard_no)
        else:
            emit_safety_failed(_critical_sync_target.defect_no, _critical_sync_target.safety_sync_error)
    db.refresh(record)
    return api_response(message="已录入", data=_record_to_dict(record))


@router.post("/sweep-missed")
def sweep_missed(db: Session = Depends(get_db), _: User = Depends(require_write)):
    """扫一遍超时未完成任务，置为 MISSED（开放给外部 cron 调用）"""
    cutoff = datetime.utcnow() - timedelta(hours=settings.TASK_MISSED_AFTER_HOURS)
    q = db.query(InspectionTask).filter(
        InspectionTask.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
        InspectionTask.scheduled_at < cutoff,
    )
    rows = q.all()
    for t in rows:
        t.status = TaskStatus.MISSED
    db.commit()
    return api_response(message=f"已标记 {len(rows)} 个漏检任务", data={"missed": len(rows)})
