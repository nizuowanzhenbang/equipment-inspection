"""两票电子签名工具（v3.0）

模拟轻量级 CA：用户在关键流转节点必须再次输入密码，后端校验密码后生成
HMAC-SHA256(secret, f"{ticket_no}|{stage}|{username}|{timestamp}") 作为签名摘要。

不是真正的 CA，但满足"二次确认 + 不可抵赖 + 可审计"的电厂业务要求。
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Optional

from app.api.deps import verify_password
from app.config import settings
from app.models.user import User


def _signing_secret() -> bytes:
    secret = settings.SIGNATURE_SECRET or settings.SECRET_KEY
    return secret.encode("utf-8")


def make_signature(ticket_no: str, stage: str, username: str, ts: Optional[str] = None) -> dict:
    ts = ts or datetime.utcnow().isoformat(timespec="seconds")
    payload = f"{ticket_no}|{stage}|{username}|{ts}"
    digest = hmac.new(_signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "stage": stage,
        "signer": username,
        "signed_at": ts,
        "sig_hash": digest,
    }


def verify_signature(entry: dict, ticket_no: str) -> bool:
    """重算 HMAC 校验签名条目是否被篡改"""
    try:
        expected = make_signature(ticket_no, entry["stage"], entry["signer"], entry["signed_at"])
    except KeyError:
        return False
    return hmac.compare_digest(expected["sig_hash"], entry.get("sig_hash", ""))


def assert_password(user: User, password: Optional[str]) -> None:
    """关键签名节点：必须再次输入密码"""
    if not settings.SIGNATURE_REQUIRE_PASSWORD:
        return
    if not password:
        from fastapi import HTTPException
        raise HTTPException(400, "请输入签名密码")
    if not verify_password(password, user.hashed_password):
        from fastapi import HTTPException
        raise HTTPException(403, "签名密码错误")


def append_signature(existing: Optional[list], entry: dict) -> list:
    chain = list(existing or [])
    chain.append(entry)
    return chain
