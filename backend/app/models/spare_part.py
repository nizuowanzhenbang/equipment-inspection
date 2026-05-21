"""备品备件 + 出入库流水模型"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from app.database import Base


class StockMovementType(str, enum.Enum):
    IN = "IN"           # 入库（采购/调拨入）
    OUT = "OUT"         # 出库（检修领用）
    ADJUST = "ADJUST"   # 盘点调整


class SparePart(Base):
    __tablename__ = "spare_parts"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False, comment="物料编号 SP-NNNN")
    name = Column(String(100), nullable=False)
    spec = Column(String(200), nullable=True, comment="规格型号")
    unit = Column(String(20), default="件", nullable=False)
    category = Column(String(50), nullable=True, comment="分类：轴承/密封件/电子件/油料/工具...")

    stock_qty = Column(Numeric(10, 2), default=0, comment="当前库存数量")
    min_qty = Column(Numeric(10, 2), default=0, comment="安全库存（低于即预警）")
    unit_price = Column(Numeric(10, 2), default=0, comment="单价（元）")

    location = Column(String(100), nullable=True, comment="存放位置（仓位）")
    supplier = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    movements = relationship("StockMovement", back_populates="spare_part", cascade="all, delete-orphan")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    spare_part_id = Column(Integer, ForeignKey("spare_parts.id"), nullable=False, index=True)
    movement_type = Column(Enum(StockMovementType), nullable=False, index=True)
    qty = Column(Numeric(10, 2), nullable=False, comment="数量（OUT 用正数）")

    defect_id = Column(Integer, ForeignKey("defects.id"), nullable=True, index=True, comment="关联缺陷（领用场景）")
    work_ticket_id = Column(Integer, ForeignKey("work_tickets.id"), nullable=True, index=True)

    operator = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    spare_part = relationship("SparePart", back_populates="movements")
