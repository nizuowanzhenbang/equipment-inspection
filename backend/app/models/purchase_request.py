"""备件采购申请单（v3.0）

低库存自动/手动生成，SUPERVISOR 审批通过后可推送至 fuel-procurement 系统作为采购计划。
"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from app.database import Base


class PRStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SENT = "SENT"          # 已推送外部采购系统
    RECEIVED = "RECEIVED"  # 入库完成
    CANCELLED = "CANCELLED"


class PRSource(str, enum.Enum):
    AUTO_LOW_STOCK = "AUTO_LOW_STOCK"   # 自动：低库存触发
    MANUAL = "MANUAL"                   # 手工


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"

    id = Column(Integer, primary_key=True, index=True)
    pr_no = Column(String(50), unique=True, index=True, nullable=False, comment="PR-YYYYMMDD-NNNN")

    spare_part_id = Column(Integer, ForeignKey("spare_parts.id"), nullable=False, index=True)
    qty = Column(Numeric(10, 2), nullable=False, comment="申请采购数量")
    estimated_amount = Column(Numeric(12, 2), default=0, comment="预估金额 = qty × unit_price")
    urgency = Column(String(20), default="NORMAL", comment="NORMAL / URGENT")
    reason = Column(Text, nullable=True)

    source = Column(Enum(PRSource), default=PRSource.MANUAL, nullable=False)
    status = Column(Enum(PRStatus), default=PRStatus.DRAFT, nullable=False, index=True)

    applicant = Column(String(50), nullable=True)
    approver = Column(String(50), nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejected_reason = Column(Text, nullable=True)

    # 与外部 fuel-procurement 系统对接
    external_order_no = Column(String(100), nullable=True, index=True, comment="对端订单号 PO-...")
    sent_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, nullable=True)
    received_qty = Column(Numeric(10, 2), default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    spare_part = relationship("SparePart")
