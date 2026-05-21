"""备品备件 schemas"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field

from app.models.spare_part import StockMovementType


class SparePartCreate(BaseModel):
    name: str
    spec: Optional[str] = None
    unit: str = "件"
    category: Optional[str] = None
    stock_qty: Decimal = Field(default=Decimal("0"))
    min_qty: Decimal = Field(default=Decimal("0"))
    unit_price: Decimal = Field(default=Decimal("0"))
    location: Optional[str] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None


class SparePartUpdate(BaseModel):
    name: Optional[str] = None
    spec: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    min_qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    location: Optional[str] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None


class SparePartResponse(BaseModel):
    id: int
    code: str
    name: str
    spec: Optional[str]
    unit: str
    category: Optional[str]
    stock_qty: Decimal
    min_qty: Decimal
    unit_price: Decimal
    location: Optional[str]
    supplier: Optional[str]
    notes: Optional[str]
    low_stock: bool = False
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MovementCreate(BaseModel):
    movement_type: StockMovementType
    qty: Decimal
    defect_id: Optional[int] = None
    work_ticket_id: Optional[int] = None
    notes: Optional[str] = None


class MovementResponse(BaseModel):
    id: int
    spare_part_id: int
    spare_part_code: Optional[str] = None
    spare_part_name: Optional[str] = None
    movement_type: StockMovementType
    qty: Decimal
    defect_id: Optional[int]
    work_ticket_id: Optional[int]
    operator: Optional[str]
    notes: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
