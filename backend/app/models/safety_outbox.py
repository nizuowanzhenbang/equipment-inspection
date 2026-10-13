"""与缺陷本地事务一同提交的不可变安全联动消息。"""
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON
from app.database import Base


class SafetyOutbox(Base):
    __tablename__ = 'safety_outbox'
    defect_id = Column(Integer, ForeignKey('defects.id'), primary_key=True, autoincrement=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
