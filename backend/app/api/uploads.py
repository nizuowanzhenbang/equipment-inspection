"""文件上传：本地 disk / S3 / MinIO / OSS，统一通过 storage 抽象层"""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import require_write
from app.config import settings
from app.models.user import User
from app.utils.helpers import api_response
from app.utils.storage import get_storage

router = APIRouter(prefix="/api/uploads", tags=["文件上传"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}


def _safe_filename(orig: str) -> str:
    base = re.sub(r"[^\w.\-]", "_", orig or "")
    if not base:
        base = "file"
    return base[-80:]


def _max_bytes() -> int:
    return max(1, settings.UPLOAD_MAX_MB) * 1024 * 1024


@router.post("")
async def upload(file: UploadFile = File(...), current: User = Depends(require_write)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"不支持的文件类型 {ext}，仅允许 {sorted(ALLOWED_EXT)}")

    body = await file.read()
    if len(body) > _max_bytes():
        raise HTTPException(400, f"文件过大（{len(body)} 字节，上限 {_max_bytes()}）")

    safe = _safe_filename(file.filename or "file")
    storage = get_storage()
    info = storage.save(body, safe, content_type=file.content_type or "")
    return api_response(
        message="上传成功",
        data={
            "url": info["url"],
            "key": info["key"],
            "backend": info["backend"],
            "filename": file.filename,
            "size": info["size"],
            "uploaded_by": current.username,
        },
    )


@router.get("/presign")
def presign(key: str, current: User = Depends(require_write)):
    """对 S3 对象签发新的临时 URL（本地后端返回 /uploads/{key}）"""
    storage = get_storage()
    url = storage.presign(key)
    if not url:
        url = f"/uploads/{key}"
    return api_response(data={"key": key, "url": url, "backend": storage.name})
