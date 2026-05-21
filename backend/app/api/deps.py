"""依赖注入：JWT 鉴权 + 角色校验"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": subject, "exp": expire}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(401, "无效凭证", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user


def require_inspector(current: User = Depends(get_current_user)) -> User:
    """点检相关写操作：ADMIN / INSPECTOR"""
    if current.role in (UserRole.ADMIN, UserRole.INSPECTOR):
        return current
    raise HTTPException(403, "仅点检员或管理员可执行")


def require_repairman(current: User = Depends(get_current_user)) -> User:
    """检修相关写操作：ADMIN / REPAIRMAN"""
    if current.role in (UserRole.ADMIN, UserRole.REPAIRMAN):
        return current
    raise HTTPException(403, "仅维修工或管理员可执行")


def require_supervisor(current: User = Depends(get_current_user)) -> User:
    """验收/工单分派：ADMIN / SUPERVISOR"""
    if current.role in (UserRole.ADMIN, UserRole.SUPERVISOR):
        return current
    raise HTTPException(403, "仅主管或管理员可执行")


def require_write(current: User = Depends(get_current_user)) -> User:
    """泛写权限：除 VIEWER 之外都允许"""
    if current.role == UserRole.VIEWER:
        raise HTTPException(403, "只读账户无权操作")
    return current


def require_admin(current: User = Depends(get_current_user)) -> User:
    """仅 ADMIN 可用：用户管理等高权限场景"""
    if current.role != UserRole.ADMIN:
        raise HTTPException(403, "仅管理员可执行")
    return current
