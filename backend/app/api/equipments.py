"""设备台账 API"""
import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

try:
    import segno  # 纯 Python，轻量
except ImportError:  # noqa: BLE001
    segno = None

from app.api.deps import get_db, get_current_user, require_write
from app.models.equipment import Equipment, EquipmentSystem, Criticality, EquipmentStatus
from app.models.defect import Defect, DefectStatus
from app.models.task import InspectionRecord, PointStatus
from app.models.route import InspectionPoint
from app.models.ticket import WorkTicket, WorkTicketStatus
from app.models.spare_part import StockMovement, StockMovementType, SparePart
from app.models.user import User
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate, EquipmentResponse
from app.utils.helpers import api_response, paginate_response, generate_equipment_code

router = APIRouter(prefix="/api/equipments", tags=["设备台账"])


def _to_dict(e: Equipment) -> dict:
    return EquipmentResponse.model_validate(e).model_dump(mode="json")


@router.get("")
def list_equipments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    equipment_system: Optional[EquipmentSystem] = None,
    criticality: Optional[Criticality] = None,
    status: Optional[EquipmentStatus] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Equipment)
    if equipment_system:
        q = q.filter(Equipment.equipment_system == equipment_system)
    if criticality:
        q = q.filter(Equipment.criticality == criticality)
    if status:
        q = q.filter(Equipment.status == status)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter((Equipment.name.like(like)) | (Equipment.code.like(like)))

    total = q.count()
    rows = q.order_by(Equipment.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [_to_dict(r) for r in rows]
    return api_response(data=paginate_response(items, total, page, page_size))


@router.post("")
def create_equipment(payload: EquipmentCreate, db: Session = Depends(get_db), _: User = Depends(require_write)):
    next_seq = (
        db.query(func.count(Equipment.id))
        .filter(Equipment.equipment_system == payload.equipment_system)
        .scalar() or 0
    ) + 1
    code = generate_equipment_code(payload.equipment_system.value, next_seq)
    eq = Equipment(
        code=code,
        qr_code=f"EQ::{code}",
        **payload.model_dump(),
    )
    db.add(eq)
    db.commit()
    db.refresh(eq)
    return api_response(message="设备已登记", data=_to_dict(eq))


@router.get("/{eid}/qr.svg")
def equipment_qr(eid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """返回设备 QR 码 SVG，内容为 `EQ::CODE`，可被 MobileScan 直接识别"""
    if segno is None:
        raise HTTPException(500, "服务器未安装 segno，请 pip install segno")
    e = db.query(Equipment).filter(Equipment.id == eid).first()
    if not e:
        raise HTTPException(404, "设备不存在")
    qr = segno.make(e.qr_code or f"EQ::{e.code}", error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=8, border=2, dark="#000", light="#fff")
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


@router.get("/by-code/{code}")
def get_by_code(code: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """根据设备编号查（用于 QR 扫码：QR 内容 "EQ::CODE"）"""
    raw = code.strip()
    if raw.startswith("EQ::"):
        raw = raw[4:]
    e = db.query(Equipment).filter(Equipment.code == raw).first()
    if not e:
        raise HTTPException(404, f"未找到设备 {raw}")
    return api_response(data=_to_dict(e))


@router.get("/{eid}")
def get_equipment(eid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    e = db.query(Equipment).filter(Equipment.id == eid).first()
    if not e:
        raise HTTPException(404, "设备不存在")
    return api_response(data=_to_dict(e))


@router.put("/{eid}")
def update_equipment(
    eid: int, payload: EquipmentUpdate,
    db: Session = Depends(get_db), _: User = Depends(require_write),
):
    e = db.query(Equipment).filter(Equipment.id == eid).first()
    if not e:
        raise HTTPException(404, "设备不存在")
    for f, v in payload.model_dump(exclude_unset=True).items():
        setattr(e, f, v)
    db.commit()
    db.refresh(e)
    return api_response(message="已更新", data=_to_dict(e))


@router.post("/{eid}/maintenance")
def to_maintenance(eid: int, db: Session = Depends(get_db), _: User = Depends(require_write)):
    e = db.query(Equipment).filter(Equipment.id == eid).first()
    if not e:
        raise HTTPException(404, "设备不存在")
    if e.status == EquipmentStatus.DECOMMISSIONED:
        raise HTTPException(400, "已退役设备不能转检修")
    e.status = EquipmentStatus.MAINTENANCE
    db.commit()
    return api_response(message=f"{e.code} 已转入检修状态")


@router.post("/{eid}/restore")
def restore(eid: int, db: Session = Depends(get_db), _: User = Depends(require_write)):
    e = db.query(Equipment).filter(Equipment.id == eid).first()
    if not e:
        raise HTTPException(404, "设备不存在")
    if e.status not in (EquipmentStatus.MAINTENANCE, EquipmentStatus.STANDBY):
        raise HTTPException(400, "仅检修/备用状态可恢复")
    e.status = EquipmentStatus.RUNNING
    db.commit()
    return api_response(message=f"{e.code} 已恢复运行")


@router.get("/{eid}/profile")
def equipment_profile(eid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """设备 360 全景：基本信息 + 近 90 天点检 / 缺陷 / 工作票 / 备件领用"""
    e = db.query(Equipment).filter(Equipment.id == eid).first()
    if not e:
        raise HTTPException(404, "设备不存在")
    since = datetime.utcnow() - timedelta(days=90)

    # 近期点检记录（通过测点反查）
    point_ids = [p.id for p in e.points]
    recent_records = []
    if point_ids:
        recs = (
            db.query(InspectionRecord)
            .filter(InspectionRecord.point_id.in_(point_ids),
                    InspectionRecord.recorded_at >= since)
            .order_by(InspectionRecord.recorded_at.desc())
            .limit(20)
            .all()
        )
        recent_records = [
            {
                "id": r.id,
                "point_id": r.point_id,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "finding": r.finding,
                "recorded_by": r.recorded_by,
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
                "defect_id": r.defect_id,
            }
            for r in recs
        ]
    record_stats = {
        "total": 0, "normal": 0, "abnormal": 0, "severe": 0,
    }
    if point_ids:
        rows = (
            db.query(InspectionRecord.status, func.count(InspectionRecord.id))
            .filter(InspectionRecord.point_id.in_(point_ids), InspectionRecord.recorded_at >= since)
            .group_by(InspectionRecord.status)
            .all()
        )
        for s, n in rows:
            key = (s.value if hasattr(s, "value") else s).lower()
            record_stats[key] = n
            record_stats["total"] += n

    # 缺陷
    open_statuses = [DefectStatus.NEW, DefectStatus.ASSIGNED, DefectStatus.IN_REPAIR, DefectStatus.REPAIRED, DefectStatus.OVERDUE]
    defects = (
        db.query(Defect)
        .filter(Defect.equipment_id == eid, Defect.created_at >= since)
        .order_by(Defect.created_at.desc())
        .limit(20)
        .all()
    )
    open_count = (
        db.query(func.count(Defect.id))
        .filter(Defect.equipment_id == eid, Defect.status.in_(open_statuses))
        .scalar() or 0
    )
    defect_list = [
        {
            "id": d.id, "defect_no": d.defect_no, "title": d.title,
            "severity": d.severity.value if hasattr(d.severity, "value") else d.severity,
            "status": d.status.value if hasattr(d.status, "value") else d.status,
            "reported_at": d.reported_at.isoformat() if d.reported_at else None,
            "closed_at": d.closed_at.isoformat() if d.closed_at else None,
        }
        for d in defects
    ]

    # 工作票
    tickets = (
        db.query(WorkTicket)
        .filter(WorkTicket.equipment_id == eid)
        .order_by(WorkTicket.created_at.desc())
        .limit(20)
        .all()
    )
    open_tickets = [t for t in tickets if t.status in (WorkTicketStatus.ISSUED, WorkTicketStatus.IN_WORK, WorkTicketStatus.SUBMITTED)]
    ticket_list = [
        {
            "id": t.id, "ticket_no": t.ticket_no, "work_content": t.work_content,
            "ticket_type": t.ticket_type.value if hasattr(t.ticket_type, "value") else t.ticket_type,
            "status": t.status.value if hasattr(t.status, "value") else t.status,
            "principal": t.principal,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tickets
    ]

    # 备件领用（OUT，通过 defect_id 或 work_ticket_id 反查与本设备相关）
    defect_ids = [d.id for d in db.query(Defect.id).filter(Defect.equipment_id == eid).all()]
    ticket_ids = [t.id for t in tickets]
    spare_usage = []
    if defect_ids or ticket_ids:
        movements = (
            db.query(StockMovement)
            .options(joinedload(StockMovement.spare_part))
            .filter(
                StockMovement.movement_type == StockMovementType.OUT,
                ((StockMovement.defect_id.in_(defect_ids) if defect_ids else False) |
                 (StockMovement.work_ticket_id.in_(ticket_ids) if ticket_ids else False)),
            )
            .order_by(StockMovement.created_at.desc())
            .limit(20)
            .all()
        )
        spare_usage = [
            {
                "id": m.id, "spare_part_code": m.spare_part.code if m.spare_part else None,
                "spare_part_name": m.spare_part.name if m.spare_part else None,
                "qty": float(m.qty), "operator": m.operator,
                "defect_id": m.defect_id, "work_ticket_id": m.work_ticket_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "notes": m.notes,
            }
            for m in movements
        ]

    return api_response(data={
        "equipment": _to_dict(e),
        "record_stats": record_stats,
        "recent_records": recent_records,
        "open_defect_count": open_count,
        "recent_defects": defect_list,
        "open_ticket_count": len(open_tickets),
        "recent_tickets": ticket_list,
        "spare_usage": spare_usage,
    })
