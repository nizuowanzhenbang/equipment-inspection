"""用户模型"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, DateTime, Boolean
from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"             # 设备部主任
    INSPECTOR = "INSPECTOR"     # 点检员
    REPAIRMAN = "REPAIRMAN"     # 维修工
    SUPERVISOR = "SUPERVISOR"   # 设备主管（缺陷验收）
    VIEWER = "VIEWER"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=False, unique=True, index=True)
    full_name = Column(String(50), nullable=True)
    hashed_password = Column(String(200), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.INSPECTOR, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
