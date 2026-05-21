"""预测性维护：基于近 90 天点检/缺陷数据 + 健康度，估算设备风险

算法（简化版，不是真 ML）：
- defects_90d 权重 0.30：每条缺陷 +10 风险（封顶 50）
- critical_90d 权重 0.25：每条 CRITICAL +20（封顶 60）
- abnormal_records_90d 权重 0.15：每条异常测点 +5（封顶 30）
- (100 - health_score) 权重 0.20：直接折算
- criticality 加成：A 级 +15、B 级 +5、C 级 +0
- 状态加成：MAINTENANCE +10
risk_score = 限制在 [0, 100]
failure_probability ≈ risk_score / 100 但用 sigmoid 平滑

输出 Top N（按 risk_score 倒序），并给出推荐建议。
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.equipment import Equipment, Criticality, EquipmentStatus
from app.models.defect import Defect, DefectSeverity
from app.models.task import InspectionRecord, PointStatus
from app.models.route import InspectionPoint
from app.models.user import User
from app.utils.helpers import api_response

router = APIRouter(prefix="/api/predictive", tags=["预测性维护"])


def _criticality_bonus(c: Criticality) -> int:
    if c == Criticality.A:
        return 15
    if c == Criticality.B:
        return 5
    return 0


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _level(risk_score: float) -> str:
    if risk_score >= 65:
        return "HIGH"
    if risk_score >= 40:
        return "MEDIUM"
    return "LOW"


def _recommend(eq: Equipment, defects_90d: int, critical_90d: int, abnormal_90d: int, risk_score: float) -> str:
    if risk_score >= 80:
        return "建议立即停机检查，优先处置；安排专项检修"
    if risk_score >= 65:
        if critical_90d:
            return "近期出现紧急缺陷，建议 7 日内安排深度检修，加密点检频次"
        return "高风险，建议安排 30 日内检修 + 每日加密点检"
    if risk_score >= 40:
        if defects_90d >= 3:
            return "中等风险，近 90 天缺陷较多，建议复盘根因 + 适度增加润滑/清洁频次"
        return "中等风险，关注重点测点参数趋势"
    if abnormal_90d >= 3:
        return "整体正常，但点检异常偏多，建议核查测点判据是否合理"
    return "运行良好，按现有计划维护"


@router.get("/ranking")
def predictive_ranking(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    since = datetime.utcnow() - timedelta(days=90)

    # 全量设备
    equipments: List[Equipment] = db.query(Equipment).filter(
        Equipment.status != EquipmentStatus.DECOMMISSIONED
    ).all()

    # 缺陷总数（按设备 group）
    defect_rows = (
        db.query(Defect.equipment_id, func.count(Defect.id))
        .filter(Defect.created_at >= since)
        .group_by(Defect.equipment_id)
        .all()
    )
    defect_map = {r[0]: r[1] for r in defect_rows}
    # CRITICAL 单独统计
    critical_rows = (
        db.query(Defect.equipment_id, func.count(Defect.id))
        .filter(Defect.created_at >= since, Defect.severity == DefectSeverity.CRITICAL)
        .group_by(Defect.equipment_id)
        .all()
    )
    critical_map = {r[0]: r[1] for r in critical_rows}

    # 点检异常记录数：通过 InspectionPoint 反查 equipment
    abnormal_rows = (
        db.query(InspectionPoint.equipment_id, func.count(InspectionRecord.id))
        .join(InspectionRecord, InspectionRecord.point_id == InspectionPoint.id)
        .filter(
            InspectionRecord.recorded_at >= since,
            InspectionRecord.status.in_([PointStatus.ABNORMAL, PointStatus.SEVERE]),
        )
        .group_by(InspectionPoint.equipment_id)
        .all()
    )
    abnormal_map = {r[0]: r[1] for r in abnormal_rows}

    items = []
    for eq in equipments:
        defects_90d = defect_map.get(eq.id, 0)
        critical_90d = critical_map.get(eq.id, 0)
        abnormal_90d = abnormal_map.get(eq.id, 0)
        health = eq.health_score if eq.health_score is not None else 100

        base = (
            min(defects_90d * 10, 50) * 0.30 +
            min(critical_90d * 20, 60) * 0.25 +
            min(abnormal_90d * 5, 30) * 0.15 +
            (100 - health) * 0.20
        )
        base += _criticality_bonus(eq.criticality)
        if eq.status == EquipmentStatus.MAINTENANCE:
            base += 10

        risk_score = max(0.0, min(100.0, base))
        # 平滑映射 0-100 → 概率 0-1
        prob = _sigmoid((risk_score - 50) / 12.0)

        items.append({
            "equipment_id": eq.id,
            "code": eq.code,
            "name": eq.name,
            "equipment_system": eq.equipment_system.value if hasattr(eq.equipment_system, "value") else eq.equipment_system,
            "criticality": eq.criticality.value if hasattr(eq.criticality, "value") else eq.criticality,
            "status": eq.status.value if hasattr(eq.status, "value") else eq.status,
            "health_score": health,
            "defects_90d": defects_90d,
            "critical_90d": critical_90d,
            "abnormal_records_90d": abnormal_90d,
            "failure_probability": round(prob, 3),
            "risk_score": round(risk_score, 1),
            "risk_level": _level(risk_score),
            "recommendation": _recommend(eq, defects_90d, critical_90d, abnormal_90d, risk_score),
        })

    items.sort(key=lambda x: x["risk_score"], reverse=True)
    return api_response(data=items[:limit])
