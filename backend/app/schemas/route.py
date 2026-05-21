"""路线 / 测点 schemas"""
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict

from app.models.route import RouteFrequency


class PointCreate(BaseModel):
    equipment_id: int
    sequence: int = 1
    check_items: List[dict]   # [{name, type, unit?, min?, max?, options?}]
    standard: Optional[str] = None
    notes: Optional[str] = None


class PointResponse(BaseModel):
    id: int
    point_no: str
    route_id: int
    equipment_id: int
    equipment_name: Optional[str] = None
    equipment_code: Optional[str] = None
    sequence: int
    check_items: Any
    standard: Optional[str]
    notes: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RouteCreate(BaseModel):
    name: str
    equipment_system: Optional[str] = None
    frequency: RouteFrequency = RouteFrequency.DAILY
    estimated_duration: int = 60
    notes: Optional[str] = None
    points: List[PointCreate] = []


class RouteUpdate(BaseModel):
    name: Optional[str] = None
    equipment_system: Optional[str] = None
    frequency: Optional[RouteFrequency] = None
    estimated_duration: Optional[int] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class RouteResponse(BaseModel):
    id: int
    route_no: str
    name: str
    equipment_system: Optional[str]
    frequency: RouteFrequency
    estimated_duration: int
    is_active: bool
    notes: Optional[str]
    point_count: int = 0
    points: List[PointResponse] = []
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
