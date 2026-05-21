"""报表与导出 API"""
import csv
import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, case
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_current_user
from app.models.equipment import Equipment, EquipmentStatus
from app.models.defect import Defect, DefectSeverity, DefectStatus
from app.models.user import User
from app.utils.helpers import api_response

router = APIRouter(prefix="/api/reports", tags=["报表与导出"])


def _csv_response(filename: str, headers: list, rows: list[list]) -> StreamingResponse:
    buf = io.StringIO()
    # 写 BOM，Excel 直接打开不乱码
    buf.write("﻿")
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/equipments/export")
def export_equipments(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.query(Equipment).order_by(Equipment.equipment_system, Equipment.code).all()
    headers = ["设备编号", "设备名称", "系统", "等级", "状态", "位置", "型号", "厂家", "投运日期", "健康度", "创建时间"]
    data = [
        [
            e.code, e.name,
            e.equipment_system.value if hasattr(e.equipment_system, "value") else e.equipment_system,
            e.criticality.value if hasattr(e.criticality, "value") else e.criticality,
            e.status.value if hasattr(e.status, "value") else e.status,
            e.location or "", e.model or "", e.manufacturer or "",
            e.install_date.isoformat() if e.install_date else "",
            e.health_score,
            e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else "",
        ]
        for e in rows
    ]
    return _csv_response(f"equipments_{datetime.now():%Y%m%d}.csv", headers, data)


@router.get("/defects/export")
def export_defects(
    start: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="截止日期 YYYY-MM-DD"),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    q = db.query(Defect).options(joinedload(Defect.equipment))
    if start:
        q = q.filter(Defect.created_at >= datetime.fromisoformat(start))
    if end:
        end_dt = datetime.fromisoformat(end) + timedelta(days=1)
        q = q.filter(Defect.created_at < end_dt)
    rows = q.order_by(Defect.created_at.desc()).all()

    headers = [
        "缺陷单号", "设备编号", "设备名称", "来源", "等级", "状态", "标题",
        "上报人", "上报时间", "派工对象", "派工时间", "完成时间", "验收人", "验收时间",
        "处理时长(小时)", "SLA截止", "费用(元)", "联动状态", "隐患单号",
    ]
    data = []
    for d in rows:
        repair_hours = ""
        if d.closed_at and d.reported_at:
            delta = d.closed_at - d.reported_at
            repair_hours = round(delta.total_seconds() / 3600, 1)
        data.append([
            d.defect_no,
            d.equipment.code if d.equipment else "",
            d.equipment.name if d.equipment else "",
            d.source.value if hasattr(d.source, "value") else d.source,
            d.severity.value if hasattr(d.severity, "value") else d.severity,
            d.status.value if hasattr(d.status, "value") else d.status,
            d.title,
            d.reported_by or "",
            d.reported_at.strftime("%Y-%m-%d %H:%M") if d.reported_at else "",
            d.assigned_to or "",
            d.assigned_at.strftime("%Y-%m-%d %H:%M") if d.assigned_at else "",
            d.repair_completed_at.strftime("%Y-%m-%d %H:%M") if d.repair_completed_at else "",
            d.verified_by or "",
            d.verified_at.strftime("%Y-%m-%d %H:%M") if d.verified_at else "",
            repair_hours,
            d.sla_deadline.strftime("%Y-%m-%d %H:%M") if d.sla_deadline else "",
            d.repair_cost or 0,
            d.safety_sync_status or "",
            d.safety_hazard_no or "",
        ])
    return _csv_response(f"defects_{datetime.now():%Y%m%d}.csv", headers, data)


@router.get("/monthly")
def monthly_report(
    months: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    """近 N 个月的月度报表：新增缺陷数 / 关闭数 / 平均处理时长 / 各严重度分布 / SLA 达成率"""
    now = datetime.utcnow()
    out = []
    for i in range(months):
        # i=0 表示当月，依次往前
        ref = now.replace(day=1) - timedelta(days=30 * i)
        month_start = ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)

        new_count = (
            db.query(func.count(Defect.id))
            .filter(Defect.created_at >= month_start, Defect.created_at < next_month)
            .scalar() or 0
        )
        closed_q = db.query(Defect).filter(
            Defect.closed_at.isnot(None),
            Defect.closed_at >= month_start,
            Defect.closed_at < next_month,
        )
        closed_list = closed_q.all()
        closed_count = len(closed_list)
        avg_hours = 0.0
        sla_pass = 0
        if closed_list:
            total_hours = 0.0
            for d in closed_list:
                if d.reported_at and d.closed_at:
                    total_hours += (d.closed_at - d.reported_at).total_seconds() / 3600
                if d.sla_deadline and d.closed_at and d.closed_at <= d.sla_deadline:
                    sla_pass += 1
            avg_hours = round(total_hours / closed_count, 1)
        sla_pass_rate = round(sla_pass * 100 / closed_count, 1) if closed_count else 0.0

        # 各严重度
        sev_rows = (
            db.query(Defect.severity, func.count(Defect.id))
            .filter(Defect.created_at >= month_start, Defect.created_at < next_month)
            .group_by(Defect.severity)
            .all()
        )
        sev_map = {s.value if hasattr(s, "value") else s: n for s, n in sev_rows}

        out.append({
            "month": month_start.strftime("%Y-%m"),
            "new_defects": new_count,
            "closed_defects": closed_count,
            "avg_repair_hours": avg_hours,
            "sla_pass_rate": sla_pass_rate,
            "minor": sev_map.get("MINOR", 0),
            "major": sev_map.get("MAJOR", 0),
            "critical": sev_map.get("CRITICAL", 0),
        })
    out.reverse()
    return api_response(data=out)


@router.get("/equipment-availability")
def equipment_availability(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    """设备可用率：基于当前状态 + 近期检修时长占比的简化口径。

    本版本采用快照口径：可用率 = 1 - (近期 CRITICAL+MAJOR 缺陷处理总时长 / (设备数 * 时间窗口))
    取每台设备按系统分组的平均健康度作为可用率近似指标，附上现有 RUNNING/MAINTENANCE 计数。
    """
    start = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(
            Equipment.equipment_system.label("sys"),
            func.count(Equipment.id).label("total"),
            func.sum(case((Equipment.status == EquipmentStatus.RUNNING, 1), else_=0)).label("running"),
            func.sum(case((Equipment.status == EquipmentStatus.MAINTENANCE, 1), else_=0)).label("maintenance"),
            func.avg(Equipment.health_score).label("avg_health"),
        )
        .group_by(Equipment.equipment_system)
        .all()
    )
    out = []
    for r in rows:
        sys_name = r.sys.value if hasattr(r.sys, "value") else r.sys
        total = r.total or 0
        running = r.running or 0
        avail = round(running * 100 / total, 1) if total else 0.0
        out.append({
            "system": sys_name,
            "equipment_count": total,
            "running": running,
            "maintenance": r.maintenance or 0,
            "availability_rate": avail,
            "avg_health_score": round(float(r.avg_health or 0), 1),
        })
    return api_response(data={"window_days": days, "by_system": out})
