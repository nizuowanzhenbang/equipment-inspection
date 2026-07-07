"""通用工具"""
from datetime import datetime
from typing import Any


def api_response(data: Any = None, message: str = "ok", code: int = 200) -> dict:
    return {"code": code, "message": message, "data": data}


def paginate_response(items: list, total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size else 0,
    }


# 系统代码（用于设备编号前缀）
EQUIPMENT_SYSTEM_CODES = {
    "BOILER": "BL",        # 锅炉
    "TURBINE": "TB",       # 汽轮机
    "GENERATOR": "GN",     # 发电机
    "AUXILIARY": "AX",     # 辅机
    "ELECTRICAL": "EL",    # 电气
    "CHEMICAL": "CH",      # 化学水处理
    "ASH": "AS",           # 除灰除渣
    "DESULFUR": "DS",      # 脱硫脱硝
}


def generate_equipment_code(system: str, seq: int) -> str:
    """设备编号：EQ-{SYS}-NNNN"""
    code = EQUIPMENT_SYSTEM_CODES.get(system, "ZZ")
    return f"EQ-{code}-{seq:04d}"


def generate_route_no(seq: int) -> str:
    return f"RT-{seq:03d}"


def generate_point_no(seq: int) -> str:
    return f"PT-{seq:04d}"


def generate_task_no(seq: int) -> str:
    return f"TK-{datetime.now().strftime('%Y%m%d')}-{seq:04d}"


def generate_defect_no(seq: int) -> str:
    return f"DF-{datetime.now().strftime('%Y%m%d')}-{seq:04d}"


def generate_work_ticket_no(seq: int) -> str:
    return f"WT-{datetime.now().strftime('%Y%m%d')}-{seq:04d}"


def generate_operation_ticket_no(seq: int) -> str:
    return f"OT-{datetime.now().strftime('%Y%m%d')}-{seq:04d}"


def generate_spare_part_code(seq: int) -> str:
    return f"SP-{seq:04d}"


def generate_pr_no(seq: int) -> str:
    return f"PR-{datetime.now().strftime('%Y%m%d')}-{seq:04d}"
