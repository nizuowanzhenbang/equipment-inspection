"""审计日志模型：关键写操作落表"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor = Column(String(50), nullable=True, index=True, comment="操作人 username")
    action = Column(String(80), nullable=False, index=True, comment="动作标识，如 defect.create / wt.issue")
    target_type = Column(String(50), nullable=True, index=True, comment="对象类型 Defect/WorkTicket/...")
    target_id = Column(Integer, nullable=True, index=True)
    target_no = Column(String(50), nullable=True, index=True, comment="对象业务编号 (defect_no/ticket_no)")
    summary = Column(String(300), nullable=True, comment="可读摘要")
    extra = Column(JSON, nullable=True, comment="附加结构化字段")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
