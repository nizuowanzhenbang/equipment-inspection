"""用户管理 API（ADMIN-only）"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin, hash_password
from app.config import settings
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate, UserResponse, PasswordReset
from app.utils.helpers import api_response, paginate_response
from app.utils.audit import log as audit_log

router = APIRouter(prefix="/api/users", tags=["用户管理"])


def _to_dict(u: User) -> dict:
    return UserResponse.model_validate(u).model_dump(mode="json")


def _validate_password(password: str) -> None:
    minimum = 12 if settings.APP_MODE == 'production' else 6
    if len(password) < minimum or len(password.encode('utf-8')) > 72:
        raise HTTPException(400, f"密码至少 {minimum} 位，且 UTF-8 编码不超过 72 字节")


@router.get("")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    role: Optional[UserRole] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter((User.username.like(like)) | (User.full_name.like(like)))
    total = q.count()
    rows = q.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
    return api_response(data=paginate_response([_to_dict(u) for u in rows], total, page, page_size))


@router.post("")
def create_user(payload: UserCreate, db: Session = Depends(get_db), current: User = Depends(require_admin)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(400, f"用户名 {payload.username} 已存在")
    _validate_password(payload.password)
    u = User(
        username=payload.username,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(u)
    db.flush()
    audit_log(db, actor=current.username, action="user.create",
              target_type="User", target_id=u.id, target_no=u.username,
              summary=f"创建用户 {u.username} ({u.role.value})")
    db.commit()
    db.refresh(u)
    return api_response(message="用户已创建", data=_to_dict(u))


@router.put("/{uid}")
def update_user(uid: int, payload: UserUpdate, db: Session = Depends(get_db), current: User = Depends(require_admin)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "用户不存在")
    if u.username == "admin" and payload.role and payload.role != UserRole.ADMIN:
        raise HTTPException(400, "不能降级内置 admin 账户")
    if u.username == current.username and payload.is_active is False:
        raise HTTPException(400, "不能禁用自己")
    if u.id == current.id and payload.role is not None and payload.role != UserRole.ADMIN:
        raise HTTPException(400, "不能降级自己的管理员角色")
    for f, v in payload.model_dump(exclude_unset=True).items():
        setattr(u, f, v)
    db.commit()
    db.refresh(u)
    return api_response(message="已更新", data=_to_dict(u))


@router.post("/{uid}/reset-password")
def reset_password(uid: int, payload: PasswordReset, db: Session = Depends(get_db), current: User = Depends(require_admin)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "用户不存在")
    _validate_password(payload.new_password)
    u.hashed_password = hash_password(payload.new_password)
    audit_log(db, actor=current.username, action="user.reset_password",
              target_type="User", target_id=u.id, target_no=u.username,
              summary=f"重置 {u.username} 的密码")
    db.commit()
    return api_response(message=f"已重置 {u.username} 的密码")


@router.post("/{uid}/toggle-active")
def toggle_active(uid: int, db: Session = Depends(get_db), current: User = Depends(require_admin)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "用户不存在")
    if u.username == current.username:
        raise HTTPException(400, "不能禁用自己")
    if u.username == "admin":
        raise HTTPException(400, "不能禁用内置 admin 账户")
    u.is_active = not u.is_active
    db.commit()
    return api_response(message=f"{'已启用' if u.is_active else '已禁用'}", data={"is_active": u.is_active})
