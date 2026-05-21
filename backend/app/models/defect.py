"""缺陷工单模型"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class DefectSource(str, enum.Enum):
    INSPECTION = "INSPECTION"   # 点检发现
    MANUAL = "MANUAL"           # 手动上报
    ALARM = "ALARM"             # DCS 报警转入（v2）


class DefectSeverity(str, enum.Enum):
    MINOR = "MINOR"         # 一般缺陷
    MAJOR = "MAJOR"         # 重要缺陷
    CRITICAL = "CRITICAL"   # 紧急缺陷（A 级设备 + SEVERE）


class DefectStatus(str, enum.Enum):
    NEW = "NEW"                 # 新建（待派工）
    ASSIGNED = "ASSIGNED"       # 已派工
    IN_REPAIR = "IN_REPAIR"     # 检修中
    REPAIRED = "REPAIRED"       # 已修复（待验收）
    VERIFIED = "VERIFIED"       # 已验收
    CLOSED = "CLOSED"           # 已关闭（含验收 + 归档）
    OVERDUE = "OVERDUE"         # 已超期（系统打标）
    CANCELLED = "CANCELLED"


class Defect(Base):
    __tablename__ = "defects"

    id = Column(Integer, primary_key=True, index=True)
    defect_no = Column(String(50), unique=True, index=True, nullable=False, comment="缺陷单号 DF-YYYYMMDD-NNNN")
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False, index=True)

    source = Column(Enum(DefectSource), default=DefectSource.MANUAL, nullable=False)
    severity = Column(Enum(DefectSeverity), default=DefectSeverity.MINOR, nullable=False, index=True)
    status = Column(Enum(DefectStatus), default=DefectStatus.NEW, nullable=False, index=True)

    title = Column(String(200), nullable=False, comment="标题")
    description = Column(Text, nullable=True, comment="问题描述")
    photo_url = Column(String(300), nullable=True)

    reported_by = Column(String(50), nullable=True, comment="上报人")
    reported_at = Column(DateTime, default=datetime.utcnow)

    assigned_to = Column(String(50), nullable=True, comment="指派维修工")
    assigned_at = Column(DateTime, nullable=True)
    assigned_by = Column(String(50), nullable=True)

    repair_started_at = Column(DateTime, nullable=True)
    repair_completed_at = Column(DateTime, nullable=True)
    repair_notes = Column(Text, nullable=True, comment="检修记录")
    repair_cost = Column(Integer, default=0, comment="检修费用（元）")

    verified_by = Column(String(50), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    verify_notes = Column(Text, nullable=True)

    sla_deadline = Column(DateTime, nullable=True, comment="SLA 截止时间")
    closed_at = Column(DateTime, nullable=True)

    # v2: 与 plant-safety 联动
    safety_sync_status = Column(String(20), nullable=True, comment="联动状态 PENDING/SYNCED/FAILED/SKIPPED")
    safety_hazard_no = Column(String(50), nullable=True, comment="对应隐患单号（plant-safety 返回）")
    safety_sync_at = Column(DateTime, nullable=True)
    safety_sync_error = Column(String(300), nullable=True)
    safety_sync_attempts = Column(Integer, default=0, nullable=False, comment="重试次数")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # v2.2: 关联工作票
    work_tickets = relationship(
        "WorkTicket",
        primaryjoin="Defect.id == foreign(WorkTicket.defect_id)",
        viewonly=True,
    )

    equipment = relationship("Equipment", back_populates="defects")
    source_record = relationship(
        "InspectionRecord",
        back_populates="defect",
        uselist=False,
        foreign_keys="InspectionRecord.defect_id",
    )
