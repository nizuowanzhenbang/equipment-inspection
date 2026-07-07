"""文件存储抽象层（v3.0）

- LocalStorage：写到 UPLOAD_DIR，对外 URL `/uploads/...`
- S3Storage：写到 S3/MinIO/阿里云 OSS bucket，对外 URL 走预签名或自定义 CDN

通过 settings.STORAGE_BACKEND 切换。S3 后端在 boto3 未安装时自动降级回 LocalStorage 并打印警告。
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import settings


class StorageBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def save(self, content: bytes, filename: str, content_type: str = "") -> dict:
        """保存文件，返回 {key, url, size, backend}"""
        raise NotImplementedError

    def presign(self, key: str) -> Optional[str]:
        """获取临时访问 URL，本地存储返回 None"""
        return None


class LocalStorage(StorageBackend):
    name = "local"

    def save(self, content: bytes, filename: str, content_type: str = "") -> dict:
        today = datetime.utcnow().strftime("%Y%m%d")
        base_dir = Path(settings.UPLOAD_DIR) / today
        base_dir.mkdir(parents=True, exist_ok=True)
        key = f"{today}/{uuid.uuid4().hex[:10]}_{filename}"
        target = Path(settings.UPLOAD_DIR) / key
        with open(target, "wb") as f:
            f.write(content)
        return {
            "key": key,
            "url": f"/uploads/{key}",
            "size": len(content),
            "backend": self.name,
        }


class S3Storage(StorageBackend):
    name = "s3"

    def __init__(self):
        import boto3  # type: ignore
        from botocore.client import Config  # type: ignore

        self._client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT or None,
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY or None,
            aws_secret_access_key=settings.S3_SECRET_KEY or None,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.S3_FORCE_PATH_STYLE else "auto"},
            ),
        )
        self._bucket = settings.S3_BUCKET
        # 启动尝试建桶（已存在忽略）
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except Exception as exc:
                print(f"[storage] S3 bucket {self._bucket} 不存在且无法创建：{exc}")

    def save(self, content: bytes, filename: str, content_type: str = "") -> dict:
        today = datetime.utcnow().strftime("%Y%m%d")
        key = f"{today}/{uuid.uuid4().hex[:10]}_{filename}"
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self._bucket, Key=key, Body=content, **extra)
        url = self._public_url(key) or self.presign(key) or ""
        return {
            "key": key,
            "url": url,
            "size": len(content),
            "backend": self.name,
        }

    def presign(self, key: str) -> Optional[str]:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=settings.S3_PRESIGN_EXPIRE_SEC,
            )
        except Exception:
            return None

    def _public_url(self, key: str) -> Optional[str]:
        if settings.S3_PUBLIC_URL:
            base = settings.S3_PUBLIC_URL.rstrip("/")
            return f"{base}/{key}"
        return None


_storage: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    global _storage
    if _storage is not None:
        return _storage
    backend = (settings.STORAGE_BACKEND or "local").lower()
    if backend == "s3":
        try:
            _storage = S3Storage()
            print(f"[storage] 使用 S3 后端，bucket={settings.S3_BUCKET}")
        except Exception as exc:
            print(f"[storage] S3 初始化失败，降级 local：{exc}")
            _storage = LocalStorage()
    else:
        _storage = LocalStorage()
    return _storage
