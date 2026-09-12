"""两票 schemas"""
from datetime import datetime
from typing import Optional, List, Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from app.models.ticket import (
    WorkTicketType, WorkTicketStatus,
    OperationTicketType, OperationTicketStatus,
)


# ---- WorkTicket ----
class WorkTicketCreate(BaseModel):
    ticket_type: WorkTicketType = WorkTicketType.SECOND
    defect_id: Optional[int] = None
    equipment_id: int
    work_content: str
    safety_measures: Optional[List[dict]] = None
    risk_notes: Optional[str] = None
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    principal: Optional[str] = None
    team_members: Optional[List[str]] = None


class WorkTicketUpdate(BaseModel):
    work_content: Optional[str] = None
    safety_measures: Optional[List[dict]] = None
    risk_notes: Optional[str] = None
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    principal: Optional[str] = None
    team_members: Optional[List[str]] = None


class WorkTicketIssue(BaseModel):
    approval_notes: Optional[str] = None
    signature_password: Optional[str] = None    # v3.0 签名再确认密码


class WorkTicketPermit(BaseModel):
    permitter: Optional[str] = None
    notes: Optional[str] = None
    signature_password: Optional[str] = None


class WorkTicketComplete(BaseModel):
    closing_notes: Optional[str] = None
    signature_password: Optional[str] = None


class WorkTicketClose(BaseModel):
    signature_password: Optional[str] = None


class WorkTicketResponse(BaseModel):
    id: int
    ticket_no: str
    ticket_type: WorkTicketType
    defect_id: Optional[int]
    equipment_id: int
    equipment_name: Optional[str] = None
    equipment_code: Optional[str] = None
    defect_no: Optional[str] = None
    work_content: str
    safety_measures: Optional[Any] = None
    risk_notes: Optional[str]
    planned_start: Optional[datetime]
    planned_end: Optional[datetime]
    actual_start: Optional[datetime]
    actual_end: Optional[datetime]
    applicant: Optional[str]
    principal: Optional[str]
    issuer: Optional[str]
    permitter: Optional[str]
    team_members: Optional[Any] = None
    status: WorkTicketStatus
    submitted_at: Optional[datetime]
    issued_at: Optional[datetime]
    permitted_at: Optional[datetime]
    completed_at: Optional[datetime]
    closed_at: Optional[datetime]
    approval_notes: Optional[str]
    closing_notes: Optional[str]
    signatures: Optional[Any] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---- OperationTicket ----
class OperationStep(BaseModel):
    seq: int
    action: str
    expected: Optional[str] = None
    executed_at: Optional[datetime] = None
    executed_by: Optional[str] = None
    result: Optional[str] = None  # PASS / FAIL
    notes: Optional[str] = None


class OperationTicketCreate(BaseModel):
    title: str
    operation_type: OperationTicketType = OperationTicketType.SWITCHING
    work_ticket_id: Optional[int] = None
    equipment_id: Optional[int] = None
    operator: Optional[str] = None
    supervisor: Optional[str] = None
    steps: Optional[List[dict]] = None
    template_id: Optional[int] = None     # 从模板复用 steps（与 steps 二选一）
    notes: Optional[str] = None


class OperationTicketUpdate(BaseModel):
    title: Optional[str] = None
    operator: Optional[str] = None
    supervisor: Optional[str] = None
    steps: Optional[List[dict]] = None
    notes: Optional[str] = None


class StepExecute(BaseModel):
    seq: int = Field(gt=0)
    result: Literal["PASS", "FAIL"]
    notes: Optional[str] = None
    signature_password: Optional[str] = None


class OpReview(BaseModel):
    notes: Optional[str] = None
    signature_password: Optional[str] = None


class OpApprove(BaseModel):
    notes: Optional[str] = None
    signature_password: Optional[str] = None


class OperationTemplateCreate(BaseModel):
    name: str
    operation_type: OperationTicketType = OperationTicketType.SWITCHING
    description: Optional[str] = None
    steps: List[dict]


class OperationTemplateResponse(BaseModel):
    id: int
    name: str
    operation_type: OperationTicketType
    description: Optional[str]
    steps: List[Any]
    use_count: int
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class OperationTicketResponse(BaseModel):
    id: int
    ticket_no: str
    title: str
    operation_type: OperationTicketType
    work_ticket_id: Optional[int]
    equipment_id: Optional[int]
    equipment_name: Optional[str] = None
    operator: Optional[str]
    supervisor: Optional[str]
    approver: Optional[str]
    steps: List[Any]
    status: OperationTicketStatus
    reviewed_at: Optional[datetime]
    approved_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    notes: Optional[str]
    signatures: Optional[Any] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
