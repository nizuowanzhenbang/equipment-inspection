"""缺陷工单 schemas"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models.defect import DefectSource, DefectSeverity, DefectStatus


class DefectCreate(BaseModel):
    equipment_id: int
    title: str
    description: Optional[str] = None
    severity: DefectSeverity = DefectSeverity.MINOR
    photo_url: Optional[str] = None


class DefectAssign(BaseModel):
    assigned_to: str
    notes: Optional[str] = None


class DefectRepair(BaseModel):
    repair_notes: str
    repair_cost: int = 0


class DefectVerify(BaseModel):
    pass_: bool = True
    verify_notes: Optional[str] = None


class DefectResponse(BaseModel):
    id: int
    defect_no: str
    equipment_id: int
    equipment_name: Optional[str] = None
    equipment_code: Optional[str] = None
    source: DefectSource
    severity: DefectSeverity
    status: DefectStatus
    title: str
    description: Optional[str]
    photo_url: Optional[str]
    reported_by: Optional[str]
    reported_at: datetime
    assigned_to: Optional[str]
    assigned_at: Optional[datetime]
    repair_started_at: Optional[datetime]
    repair_completed_at: Optional[datetime]
    repair_notes: Optional[str]
    repair_cost: int
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    verify_notes: Optional[str]
    sla_deadline: Optional[datetime]
    closed_at: Optional[datetime]
    safety_sync_status: Optional[str] = None
    safety_hazard_no: Optional[str] = None
    safety_sync_at: Optional[datetime] = None
    safety_sync_attempts: int = 0
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
