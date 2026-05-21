"""点检任务 + 点检记录模型"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"           # 待执行
    IN_PROGRESS = "IN_PROGRESS"   # 进行中
    COMPLETED = "COMPLETED"       # 已完成
    MISSED = "MISSED"             # 漏检（计划时间已过且未完成）
    CANCELLED = "CANCELLED"


class InspectionTask(Base):
    """点检任务：依路线生成的可执行单位"""
    __tablename__ = "inspection_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_no = Column(String(50), unique=True, index=True, nullable=False, comment="任务编号 TK-YYYYMMDD-NNNN")
    route_id = Column(Integer, ForeignKey("inspection_routes.id"), nullable=False, index=True)

    scheduled_at = Column(DateTime, nullable=False, index=True, comment="计划执行时间")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    assigned_to = Column(String(50), nullable=True, comment="指派点检员（username）")
    executed_by = Column(String(50), nullable=True, comment="实际执行人")

    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False, index=True)
    abnormal_count = Column(Integer, default=0, comment="本任务发现的异常测点数")
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    route = relationship("InspectionRoute")
    records = relationship("InspectionRecord", back_populates="task", cascade="all, delete-orphan")


class PointStatus(str, enum.Enum):
    NORMAL = "NORMAL"
    ABNORMAL = "ABNORMAL"   # 异常（一般缺陷）
    SEVERE = "SEVERE"       # 严重异常（重大缺陷）


class InspectionRecord(Base):
    """单个测点的检查记录"""
    __tablename__ = "inspection_records"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("inspection_tasks.id"), nullable=False, index=True)
    point_id = Column(Integer, ForeignKey("inspection_points.id"), nullable=False, index=True)

    status = Column(Enum(PointStatus), default=PointStatus.NORMAL, nullable=False, index=True)
    readings = Column(JSON, nullable=True, comment="检查项读数：{name: value, ...}")
    finding = Column(Text, nullable=True, comment="发现的问题描述")
    photo_url = Column(String(300), nullable=True, comment="现场照片 URL")

    recorded_by = Column(String(50), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    # 异常时联动生成的缺陷
    defect_id = Column(Integer, ForeignKey("defects.id"), nullable=True, index=True)

    task = relationship("InspectionTask", back_populates="records")
    point = relationship("InspectionPoint")
    defect = relationship("Defect", back_populates="source_record", foreign_keys=[defect_id])
