"""点检任务 / 记录 schemas"""
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict

from app.models.task import TaskStatus, PointStatus


class TaskGenerate(BaseModel):
    route_id: int
    scheduled_at: datetime
    assigned_to: Optional[str] = None


class TaskResponse(BaseModel):
    id: int
    task_no: str
    route_id: int
    route_name: Optional[str] = None
    scheduled_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    assigned_to: Optional[str]
    executed_by: Optional[str]
    status: TaskStatus
    abnormal_count: int
    notes: Optional[str]
    created_at: datetime
    record_count: int = 0
    total_points: int = 0
    model_config = ConfigDict(from_attributes=True)


class RecordSubmit(BaseModel):
    point_id: int
    status: PointStatus
    readings: Optional[dict] = None
    finding: Optional[str] = None
    photo_url: Optional[str] = None


class RecordResponse(BaseModel):
    id: int
    task_id: int
    point_id: int
    point_no: Optional[str] = None
    equipment_name: Optional[str] = None
    status: PointStatus
    readings: Any
    finding: Optional[str]
    photo_url: Optional[str]
    recorded_by: Optional[str]
    recorded_at: datetime
    defect_id: Optional[int]
    model_config = ConfigDict(from_attributes=True)
