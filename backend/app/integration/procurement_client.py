"""与 fuel-procurement 系统对接：备件采购申请单推送

约定：fuel-procurement 端 v3.0 计划暴露 POST {URL}/api/integration/material-requests
- Header: X-Integration-Token: <PROCUREMENT_INTEGRATION_TOKEN>
- 返回 {code:200, data:{order_no:"PO-..."}}

未配置 PROCUREMENT_SYSTEM_URL 时，仅在本系统留存 SENT 状态（mock 模式）。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.purchase_request import PurchaseRequest, PRStatus

logger = logging.getLogger("equipment_inspection.procurement")


def _build_payload(pr: PurchaseRequest) -> dict:
    sp = pr.spare_part
    return {
        "external_no": pr.pr_no,
        "source_system": "equipment-inspection",
        "material_code": sp.code if sp else None,
        "material_name": sp.name if sp else None,
        "spec": sp.spec if sp else None,
        "unit": sp.unit if sp else "件",
        "qty": float(pr.qty or 0),
        "estimated_amount": float(pr.estimated_amount or 0),
        "urgency": pr.urgency,
        "reason": pr.reason or "",
        "applicant": pr.applicant,
        "approver": pr.approver,
        "approved_at": pr.approved_at.isoformat() if pr.approved_at else None,
    }


def push_request(db: Session, pr: PurchaseRequest) -> dict:
    """推送已批准的采购申请到 fuel-procurement，更新本地状态/外部单号

    返回 {ok, external_order_no, message}
    """
    if pr.status != PRStatus.APPROVED:
        return {"ok": False, "message": f"状态 {pr.status.value} 不可推送"}

    if not settings.PROCUREMENT_SYSTEM_URL:
        # mock：直接置 SENT
        pr.status = PRStatus.SENT
        pr.sent_at = datetime.utcnow()
        pr.external_order_no = f"MOCK-{pr.pr_no}"
        db.commit()
        return {"ok": True, "external_order_no": pr.external_order_no, "message": "无外部采购系统，已 mock 标记为 SENT"}

    url = settings.PROCUREMENT_SYSTEM_URL.rstrip("/") + "/api/integration/material-requests"
    headers = {"X-Integration-Token": settings.PROCUREMENT_INTEGRATION_TOKEN}
    try:
        resp = httpx.post(url, json=_build_payload(pr), headers=headers, timeout=settings.PROCUREMENT_TIMEOUT_SEC)
        resp.raise_for_status()
        body = resp.json()
        ext = (body.get("data") or {}).get("order_no") or body.get("order_no")
        pr.status = PRStatus.SENT
        pr.sent_at = datetime.utcnow()
        pr.external_order_no = ext
        db.commit()
        return {"ok": True, "external_order_no": ext, "message": "已推送"}
    except Exception as exc:
        logger.warning("push_request 失败 pr=%s err=%s", pr.pr_no, exc)
        return {"ok": False, "message": f"推送失败：{exc}"}
