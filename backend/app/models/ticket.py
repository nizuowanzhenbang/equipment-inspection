"""两票模型：工作票 WorkTicket + 操作票 OperationTicket

业务规则简化版：
- 工作票分三类：FIRST（第一种，高压停电）/ SECOND（第二种，低压不停电）/ EMERGENCY（紧急抢修）
- 工作票状态机：DRAFT → SUBMITTED（已提交待签发） → ISSUED（已签发） → IN_WORK（许可开工后实际作业）
   → COMPLETED（工作终结）→ CLOSED（已归档/工作票收回）；任意阶段可 CANCELLED
- 操作票状态机：DRAFT → REVIEWED（审核通过）→ APPROVED（值长批准）→ EXECUTING → COMPLETED；可 CANCELLED
- Defect → WorkTicket：一个缺陷可关联一张工作票；工作票 APPROVED/IN_WORK 期间设备应处于检修态
"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class WorkTicketType(str, enum.Enum):
    FIRST = "FIRST"            # 第一种工作票（高压停电）
    SECOND = "SECOND"          # 第二种工作票（低压不停电）
    EMERGENCY = "EMERGENCY"    # 紧急抢修工作票


class WorkTicketStatus(str, enum.Enum):
    DRAFT = "DRAFT"            # 起草中
    SUBMITTED = "SUBMITTED"    # 已提交，待签发
    ISSUED = "ISSUED"          # 已签发（签发人审核通过）
    IN_WORK = "IN_WORK"        # 许可工作后正在作业
    COMPLETED = "COMPLETED"    # 工作终结
    CLOSED = "CLOSED"          # 已归档
    CANCELLED = "CANCELLED"


class WorkTicket(Base):
    __tablename__ = "work_tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_no = Column(String(50), unique=True, index=True, nullable=False, comment="WT-YYYYMMDD-NNNN")
    ticket_type = Column(Enum(WorkTicketType), default=WorkTicketType.SECOND, nullable=False)

    defect_id = Column(Integer, ForeignKey("defects.id"), nullable=True, index=True, comment="关联的缺陷")
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False, index=True)

    work_content = Column(Text, nullable=False, comment="工作内容/任务说明")
    safety_measures = Column(JSON, nullable=True, comment="安全措施清单：[{seq,measure,checked,checked_by}]")
    risk_notes = Column(Text, nullable=True, comment="危险点分析")

    planned_start = Column(DateTime, nullable=True)
    planned_end = Column(DateTime, nullable=True)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)

    # 角色
    applicant = Column(String(50), nullable=True, comment="申请人/起草人")
    principal = Column(String(50), nullable=True, comment="工作负责人")
    issuer = Column(String(50), nullable=True, comment="签发人（supervisor）")
    permitter = Column(String(50), nullable=True, comment="许可人")
    team_members = Column(JSON, nullable=True, comment="工作班成员 username 列表")

    status = Column(Enum(WorkTicketStatus), default=WorkTicketStatus.DRAFT, nullable=False, index=True)

    submitted_at = Column(DateTime, nullable=True)
    issued_at = Column(DateTime, nullable=True)
    permitted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    approval_notes = Column(Text, nullable=True, comment="签发备注")
    closing_notes = Column(Text, nullable=True, comment="收票备注")

    # v3.0 电子签名（JSON 数组：[{stage, signer, signed_at, sig_hash, ip}]）
    signatures = Column(JSON, nullable=True, comment="签名链：issue/permit/close 等阶段")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    equipment = relationship("Equipment")
    defect = relationship("Defect", foreign_keys=[defect_id])
    operation_tickets = relationship("OperationTicket", back_populates="work_ticket")


class OperationTicketType(str, enum.Enum):
    POWER_OFF = "POWER_OFF"    # 停电
    POWER_ON = "POWER_ON"      # 送电
    SWITCHING = "SWITCHING"    # 倒闸
    OTHER = "OTHER"


class OperationTicketStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"      # 审核通过（监护人）
    APPROVED = "APPROVED"      # 值长批准
    EXECUTING = "EXECUTING"    # 执行中
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class OperationTemplate(Base):
    """操作票模板：保存常用操作序列，新建操作票时一键复用"""
    __tablename__ = "operation_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, comment="模板名称（业务唯一）")
    operation_type = Column(Enum(OperationTicketType), default=OperationTicketType.SWITCHING, nullable=False)
    description = Column(Text, nullable=True)
    steps = Column(JSON, nullable=False, comment="模板步骤 [{seq,action,expected}]")
    use_count = Column(Integer, default=0, comment="被复用次数")
    created_by = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OperationTicket(Base):
    __tablename__ = "operation_tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_no = Column(String(50), unique=True, index=True, nullable=False, comment="OT-YYYYMMDD-NNNN")
    title = Column(String(200), nullable=False)
    operation_type = Column(Enum(OperationTicketType), default=OperationTicketType.SWITCHING, nullable=False)

    work_ticket_id = Column(Integer, ForeignKey("work_tickets.id"), nullable=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=True, index=True)

    operator = Column(String(50), nullable=True, comment="操作员")
    supervisor = Column(String(50), nullable=True, comment="监护人")
    approver = Column(String(50), nullable=True, comment="值长（批准人）")

    steps = Column(JSON, nullable=False, comment="步骤数组 [{seq,action,expected,executed_at,executed_by,result,notes}]")
    status = Column(Enum(OperationTicketStatus), default=OperationTicketStatus.DRAFT, nullable=False, index=True)

    reviewed_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    notes = Column(Text, nullable=True)

    # v3.0 电子签名链
    signatures = Column(JSON, nullable=True, comment="签名链：review/approve/complete 等阶段")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    work_ticket = relationship("WorkTicket", back_populates="operation_tickets")
    equipment = relationship("Equipment")
