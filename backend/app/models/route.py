"""点检路线 + 测点模型"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class RouteFrequency(str, enum.Enum):
    SHIFT = "SHIFT"       # 班次（每 8 小时）
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class InspectionRoute(Base):
    """点检路线：固定顺序遍历多个测点"""
    __tablename__ = "inspection_routes"

    id = Column(Integer, primary_key=True, index=True)
    route_no = Column(String(50), unique=True, index=True, nullable=False, comment="路线编号 RT-NNN")
    name = Column(String(100), nullable=False, comment="路线名称（如：1#机组锅炉一班巡检）")
    equipment_system = Column(String(50), nullable=True, comment="主要覆盖系统")
    frequency = Column(Enum(RouteFrequency), default=RouteFrequency.DAILY, nullable=False, comment="计划频率")
    estimated_duration = Column(Integer, default=60, comment="预计耗时（分钟）")

    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    points = relationship(
        "InspectionPoint",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="InspectionPoint.sequence",
    )


class InspectionPoint(Base):
    """点检测点：路线上的具体检查点"""
    __tablename__ = "inspection_points"

    id = Column(Integer, primary_key=True, index=True)
    point_no = Column(String(50), unique=True, index=True, nullable=False, comment="测点编号 PT-NNNN")
    route_id = Column(Integer, ForeignKey("inspection_routes.id"), nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False, index=True)

    sequence = Column(Integer, default=1, nullable=False, comment="路线内顺序")
    check_items = Column(JSON, nullable=False, comment="检查项数组：[{name,type:NUM/BOOL/SELECT,unit?,min?,max?,options?}]")
    standard = Column(Text, nullable=True, comment="检查标准/合格判据")
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    route = relationship("InspectionRoute", back_populates="points")
    equipment = relationship("Equipment", back_populates="points")
