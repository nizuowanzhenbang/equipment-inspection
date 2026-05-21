"""设备 schemas"""
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models.equipment import EquipmentSystem, Criticality, EquipmentStatus


class EquipmentCreate(BaseModel):
    name: str
    equipment_system: EquipmentSystem
    criticality: Criticality = Criticality.C
    location: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    install_date: Optional[date] = None
    status: EquipmentStatus = EquipmentStatus.RUNNING
    notes: Optional[str] = None


class EquipmentUpdate(BaseModel):
    name: Optional[str] = None
    criticality: Optional[Criticality] = None
    location: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    install_date: Optional[date] = None
    status: Optional[EquipmentStatus] = None
    notes: Optional[str] = None


class EquipmentResponse(BaseModel):
    id: int
    code: str
    name: str
    equipment_system: EquipmentSystem
    criticality: Criticality
    location: Optional[str]
    model: Optional[str]
    manufacturer: Optional[str]
    install_date: Optional[date]
    status: EquipmentStatus
    qr_code: Optional[str]
    health_score: int
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
