"""点检路线 API"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_current_user, require_write
from app.models.equipment import Equipment
from app.models.route import InspectionRoute, InspectionPoint
from app.models.user import User
from app.schemas.route import RouteCreate, RouteUpdate, RouteResponse, PointCreate, PointResponse
from app.utils.helpers import api_response, paginate_response, generate_route_no, generate_point_no

router = APIRouter(prefix="/api/routes", tags=["点检路线"])


def _point_to_dict(p: InspectionPoint) -> dict:
    data = PointResponse.model_validate(p).model_dump(mode="json")
    if p.equipment:
        data["equipment_name"] = p.equipment.name
        data["equipment_code"] = p.equipment.code
    return data


def _route_to_dict(r: InspectionRoute, with_points: bool = False) -> dict:
    data = RouteResponse.model_validate(r).model_dump(mode="json")
    data["point_count"] = len(r.points or [])
    data["points"] = [_point_to_dict(p) for p in (r.points or [])] if with_points else []
    return data


@router.get("")
def list_routes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(InspectionRoute).options(joinedload(InspectionRoute.points))
    if is_active is not None:
        q = q.filter(InspectionRoute.is_active == is_active)
    total = q.count()
    rows = q.order_by(InspectionRoute.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [_route_to_dict(r) for r in rows]
    return api_response(data=paginate_response(items, total, page, page_size))


@router.post("")
def create_route(payload: RouteCreate, db: Session = Depends(get_db), _: User = Depends(require_write)):
    next_seq = (db.query(func.count(InspectionRoute.id)).scalar() or 0) + 1
    route = InspectionRoute(
        route_no=generate_route_no(next_seq),
        name=payload.name,
        equipment_system=payload.equipment_system,
        frequency=payload.frequency,
        estimated_duration=payload.estimated_duration,
        notes=payload.notes,
    )
    db.add(route)
    db.flush()  # 拿到 route.id

    point_seq_base = (db.query(func.count(InspectionPoint.id)).scalar() or 0)
    for i, pt in enumerate(payload.points, start=1):
        if not db.query(Equipment).filter(Equipment.id == pt.equipment_id).first():
            raise HTTPException(400, f"测点 #{i}：设备 {pt.equipment_id} 不存在")
        p = InspectionPoint(
            point_no=generate_point_no(point_seq_base + i),
            route_id=route.id,
            equipment_id=pt.equipment_id,
            sequence=pt.sequence,
            check_items=pt.check_items,
            standard=pt.standard,
            notes=pt.notes,
        )
        db.add(p)
    db.commit()
    db.refresh(route)
    return api_response(message="路线已创建", data=_route_to_dict(route, with_points=True))


@router.get("/{rid}")
def get_route(rid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    r = (
        db.query(InspectionRoute)
        .options(joinedload(InspectionRoute.points).joinedload(InspectionPoint.equipment))
        .filter(InspectionRoute.id == rid)
        .first()
    )
    if not r:
        raise HTTPException(404, "路线不存在")
    return api_response(data=_route_to_dict(r, with_points=True))


@router.put("/{rid}")
def update_route(rid: int, payload: RouteUpdate, db: Session = Depends(get_db), _: User = Depends(require_write)):
    r = db.query(InspectionRoute).filter(InspectionRoute.id == rid).first()
    if not r:
        raise HTTPException(404, "路线不存在")
    for f, v in payload.model_dump(exclude_unset=True).items():
        setattr(r, f, v)
    db.commit()
    db.refresh(r)
    return api_response(message="已更新", data=_route_to_dict(r))


@router.post("/{rid}/points")
def add_point(rid: int, payload: PointCreate, db: Session = Depends(get_db), _: User = Depends(require_write)):
    r = db.query(InspectionRoute).filter(InspectionRoute.id == rid).first()
    if not r:
        raise HTTPException(404, "路线不存在")
    if not db.query(Equipment).filter(Equipment.id == payload.equipment_id).first():
        raise HTTPException(400, "设备不存在")
    next_seq = (db.query(func.count(InspectionPoint.id)).scalar() or 0) + 1
    p = InspectionPoint(
        point_no=generate_point_no(next_seq),
        route_id=rid,
        **payload.model_dump(),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return api_response(message="测点已添加", data=_point_to_dict(p))


@router.delete("/points/{pid}")
def delete_point(pid: int, db: Session = Depends(get_db), _: User = Depends(require_write)):
    p = db.query(InspectionPoint).filter(InspectionPoint.id == pid).first()
    if not p:
        raise HTTPException(404, "测点不存在")
    db.delete(p)
    db.commit()
    return api_response(message="已删除")
