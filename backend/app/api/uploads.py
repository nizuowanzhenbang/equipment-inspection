"""文件上传：本地 disk 存储，返回可访问的 URL"""
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import require_write
from app.config import settings
from app.models.user import User
from app.utils.helpers import api_response

router = APIRouter(prefix="/api/uploads", tags=["文件上传"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}
MAX_BYTES = 5 * 1024 * 1024     # 5MB


def _safe_filename(orig: str) -> str:
    base = re.sub(r"[^\w.\-]", "_", orig or "")
    if not base:
        base = "file"
    return base[-80:]


@router.post("")
async def upload(file: UploadFile = File(...), current: User = Depends(require_write)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"不支持的文件类型 {ext}，仅允许 {sorted(ALLOWED_EXT)}")

    body = await file.read()
    if len(body) > MAX_BYTES:
        raise HTTPException(400, f"文件过大（{len(body)} 字节，上限 {MAX_BYTES}）")

    today = datetime.utcnow().strftime("%Y%m%d")
    base_dir = Path(settings.UPLOAD_DIR) / today
    base_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(file.filename or "file")
    name = f"{uuid.uuid4().hex[:10]}_{safe}"
    target = base_dir / name
    with open(target, "wb") as f:
        f.write(body)

    # 对外 URL：/uploads/YYYYMMDD/filename
    url = f"/uploads/{today}/{name}"
    return api_response(
        message="上传成功",
        data={
            "url": url,
            "filename": file.filename,
            "size": len(body),
            "uploaded_by": current.username,
        },
    )
