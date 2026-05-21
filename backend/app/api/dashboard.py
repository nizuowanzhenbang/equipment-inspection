"""Dashboard 看板：点检完成率 / 缺陷分布 / 设备健康榜 / 高发故障设备"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.equipment import Equipment, Criticality, EquipmentStatus
from app.models.task import InspectionTask, TaskStatus
from app.models.defect import Defect, DefectSeverity, DefectStatus
from app.models.ticket import WorkTicket, WorkTicketStatus, OperationTicket, OperationTicketStatus
from app.models.spare_part import SparePart
from app.models.user import User
from app.utils.helpers import api_response

router = APIRouter(prefix="/api/dashboard", tags=["看板"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())

    eq_total = db.query(func.count(Equipment.id)).scalar() or 0
    eq_a = db.query(func.count(Equipment.id)).filter(Equipment.criticality == Criticality.A).scalar() or 0
    eq_running = db.query(func.count(Equipment.id)).filter(Equipment.status == EquipmentStatus.RUNNING).scalar() or 0
    eq_maintenance = db.query(func.count(Equipment.id)).filter(Equipment.status == EquipmentStatus.MAINTENANCE).scalar() or 0

    # 今日任务统计
    today_total = (
        db.query(func.count(InspectionTask.id))
        .filter(InspectionTask.scheduled_at >= today_start)
        .scalar() or 0
    )
    today_done = (
        db.query(func.count(InspectionTask.id))
        .filter(InspectionTask.scheduled_at >= today_start, InspectionTask.status == TaskStatus.COMPLETED)
        .scalar() or 0
    )
    today_missed = (
        db.query(func.count(InspectionTask.id))
        .filter(InspectionTask.scheduled_at >= today_start, InspectionTask.status == TaskStatus.MISSED)
        .scalar() or 0
    )
    completion_rate = round(today_done * 100 / today_total, 1) if today_total else 0.0

    # 缺陷统计
    open_statuses = [DefectStatus.NEW, DefectStatus.ASSIGNED, DefectStatus.IN_REPAIR, DefectStatus.REPAIRED, DefectStatus.OVERDUE]
    open_defects = db.query(func.count(Defect.id)).filter(Defect.status.in_(open_statuses)).scalar() or 0
    critical_open = (
        db.query(func.count(Defect.id))
        .filter(Defect.status.in_(open_statuses), Defect.severity == DefectSeverity.CRITICAL)
        .scalar() or 0
    )
    overdue = db.query(func.count(Defect.id)).filter(Defect.status == DefectStatus.OVERDUE).scalar() or 0

    avg_health = db.query(func.avg(Equipment.health_score)).scalar() or 100

    # v2.2: 两票 + 备件统计
    wt_in_work = db.query(func.count(WorkTicket.id)).filter(
        WorkTicket.status.in_([WorkTicketStatus.ISSUED, WorkTicketStatus.IN_WORK])
    ).scalar() or 0
    wt_pending = db.query(func.count(WorkTicket.id)).filter(
        WorkTicket.status == WorkTicketStatus.SUBMITTED
    ).scalar() or 0
    ot_executing = db.query(func.count(OperationTicket.id)).filter(
        OperationTicket.status == OperationTicketStatus.EXECUTING
    ).scalar() or 0
    low_stock = db.query(func.count(SparePart.id)).filter(SparePart.stock_qty < SparePart.min_qty).scalar() or 0

    return api_response(data={
        "equipment": {
            "total": eq_total,
            "criticality_a": eq_a,
            "running": eq_running,
            "maintenance": eq_maintenance,
        },
        "today_tasks": {
            "total": today_total,
            "completed": today_done,
            "missed": today_missed,
            "completion_rate": completion_rate,
        },
        "defects": {
            "open": open_defects,
            "critical_open": critical_open,
            "overdue": overdue,
        },
        "tickets": {
            "work_in_progress": wt_in_work,
            "work_pending_approval": wt_pending,
            "operation_executing": ot_executing,
        },
        "inventory": {
            "low_stock_items": low_stock,
        },
        "avg_health_score": round(float(avg_health), 1),
    })


@router.get("/defect-trend")
def defect_trend(days: int = 30, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """近 N 天缺陷新增/关闭趋势"""
    start = datetime.utcnow().date() - timedelta(days=days - 1)
    rows = (
        db.query(
            func.date(Defect.created_at).label("d"),
            func.count(Defect.id).label("n"),
        )
        .filter(func.date(Defect.created_at) >= start)
        .group_by(func.date(Defect.created_at))
        .all()
    )
    closed_rows = (
        db.query(
            func.date(Defect.closed_at).label("d"),
            func.count(Defect.id).label("n"),
        )
        .filter(Defect.closed_at.isnot(None), func.date(Defect.closed_at) >= start)
        .group_by(func.date(Defect.closed_at))
        .all()
    )
    new_map = {str(r.d): r.n for r in rows}
    closed_map = {str(r.d): r.n for r in closed_rows}
    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        ds = d.isoformat()
        series.append({"date": ds, "new": new_map.get(ds, 0), "closed": closed_map.get(ds, 0)})
    return api_response(data=series)


@router.get("/system-distribution")
def system_distribution(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """各系统的设备数 + 未关缺陷数"""
    rows = (
        db.query(
            Equipment.equipment_system.label("sys"),
            func.count(Equipment.id).label("eq"),
        )
        .group_by(Equipment.equipment_system)
        .all()
    )
    open_statuses = [DefectStatus.NEW, DefectStatus.ASSIGNED, DefectStatus.IN_REPAIR, DefectStatus.REPAIRED, DefectStatus.OVERDUE]
    defect_rows = (
        db.query(Equipment.equipment_system.label("sys"), func.count(Defect.id).label("dn"))
        .join(Defect, Defect.equipment_id == Equipment.id)
        .filter(Defect.status.in_(open_statuses))
        .group_by(Equipment.equipment_system)
        .all()
    )
    defect_map = {r.sys.value if hasattr(r.sys, "value") else r.sys: r.dn for r in defect_rows}
    out = []
    for r in rows:
        sys_name = r.sys.value if hasattr(r.sys, "value") else r.sys
        out.append({"system": sys_name, "equipment_count": r.eq, "open_defects": defect_map.get(sys_name, 0)})
    return api_response(data=out)


@router.get("/top-faulty-equipments")
def top_faulty(limit: int = 5, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """近 30 天缺陷数 TOP N 设备"""
    start = datetime.utcnow() - timedelta(days=30)
    rows = (
        db.query(
            Equipment.id, Equipment.code, Equipment.name,
            Equipment.criticality, Equipment.health_score,
            func.count(Defect.id).label("n"),
        )
        .join(Defect, Defect.equipment_id == Equipment.id)
        .filter(Defect.created_at >= start)
        .group_by(Equipment.id)
        .order_by(func.count(Defect.id).desc())
        .limit(limit)
        .all()
    )
    return api_response(data=[
        {
            "equipment_id": r.id, "code": r.code, "name": r.name,
            "criticality": r.criticality.value if hasattr(r.criticality, "value") else r.criticality,
            "health_score": r.health_score, "defect_count_30d": r.n,
        }
        for r in rows
    ])


@router.get("/equipment-health-ranking")
def health_ranking(limit: int = 10, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """设备健康度倒序榜（关键设备优先看）"""
    rows = (
        db.query(Equipment)
        .order_by(
            case((Equipment.criticality == Criticality.A, 0), (Equipment.criticality == Criticality.B, 1), else_=2),
            Equipment.health_score.asc(),
        )
        .limit(limit)
        .all()
    )
    return api_response(data=[
        {
            "id": e.id, "code": e.code, "name": e.name,
            "criticality": e.criticality.value if hasattr(e.criticality, "value") else e.criticality,
            "status": e.status.value if hasattr(e.status, "value") else e.status,
            "health_score": e.health_score,
        }
        for e in rows
    ])
