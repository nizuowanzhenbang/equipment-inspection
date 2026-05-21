"""设备台账模型"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, DateTime, Text, Date
from sqlalchemy.orm import relationship
from app.database import Base


class EquipmentSystem(str, enum.Enum):
    BOILER = "BOILER"           # 锅炉系统
    TURBINE = "TURBINE"         # 汽轮机系统
    GENERATOR = "GENERATOR"     # 发电机系统
    AUXILIARY = "AUXILIARY"     # 辅机（给水泵/送引风机等）
    ELECTRICAL = "ELECTRICAL"   # 电气
    CHEMICAL = "CHEMICAL"       # 化学水处理
    ASH = "ASH"                 # 除灰除渣
    DESULFUR = "DESULFUR"       # 脱硫脱硝


class Criticality(str, enum.Enum):
    A = "A"   # A 级关键设备（停机即停机组）
    B = "B"   # B 级重要设备（停机降负荷）
    C = "C"   # C 级一般设备


class EquipmentStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    STANDBY = "STANDBY"
    MAINTENANCE = "MAINTENANCE"
    DECOMMISSIONED = "DECOMMISSIONED"


class Equipment(Base):
    __tablename__ = "equipments"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False, comment="设备编号 EQ-XX-NNNN")
    name = Column(String(100), nullable=False, comment="设备名称")
    equipment_system = Column(Enum(EquipmentSystem), nullable=False, index=True, comment="所属系统")
    criticality = Column(Enum(Criticality), default=Criticality.C, nullable=False, index=True, comment="重要性等级")

    location = Column(String(100), nullable=True, comment="安装位置/区域")
    model = Column(String(100), nullable=True, comment="设备型号")
    manufacturer = Column(String(100), nullable=True, comment="生产厂家")
    install_date = Column(Date, nullable=True, comment="投运日期")

    status = Column(Enum(EquipmentStatus), default=EquipmentStatus.RUNNING, nullable=False, index=True)
    qr_code = Column(String(200), nullable=True, comment="二维码内容（设备唯一标识）")

    health_score = Column(Integer, default=100, comment="健康度评分 0-100")

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    points = relationship("InspectionPoint", back_populates="equipment", cascade="all, delete-orphan")
    defects = relationship("Defect", back_populates="equipment", cascade="all, delete-orphan")
