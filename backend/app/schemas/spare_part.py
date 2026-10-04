"""备品备件 schemas"""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Optional
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.models.spare_part import StockMovementType


MAX_STOCK_QUANTITY = Decimal("99999999.99")


def validate_inventory_precision(value: Decimal) -> Decimal:
    # Inspect the exact digits: Decimal.normalize() may round a long mantissa
    # under the active decimal context before Pydantic counts decimal places.
    _, digits, exponent = value.as_tuple()
    extra_places = -exponent - 2
    if extra_places > 0 and any(digits[-extra_places:]):
        raise ValueError("数量最多支持两位小数")
    return value


InventoryDecimal = Annotated[Decimal, Field(
    ge=0, le=MAX_STOCK_QUANTITY, max_digits=10, decimal_places=2, allow_inf_nan=False,
), AfterValidator(validate_inventory_precision)]


class SparePartCreate(BaseModel):
    name: str
    spec: Optional[str] = None
    unit: str = "件"
    category: Optional[str] = None
    stock_qty: InventoryDecimal = Decimal("0")
    min_qty: InventoryDecimal = Decimal("0")
    unit_price: InventoryDecimal = Decimal("0")
    location: Optional[str] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None


class SparePartUpdate(BaseModel):
    name: Optional[str] = None
    spec: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    min_qty: Optional[InventoryDecimal] = None
    unit_price: Optional[InventoryDecimal] = None
    location: Optional[str] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("min_qty", "unit_price")
    @classmethod
    def reject_null_quantity(cls, value):
        # Omitted fields are untouched; an explicit null is not a quantity.
        if value is None:
            raise ValueError("数量及单价不可为空")
        return value


class SparePartResponse(BaseModel):
    id: int
    code: str
    name: str
    spec: Optional[str]
    unit: str
    category: Optional[str]
    stock_qty: Decimal
    stock_revision: int
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
    qty: InventoryDecimal
    expected_stock_revision: Optional[Annotated[int, Field(strict=True, ge=0, le=2147483647)]] = None
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
