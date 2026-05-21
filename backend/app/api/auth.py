"""认证 API"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_password, create_access_token, get_current_user
from app.models.user import User
from app.schemas.user import Token, UserResponse
from app.utils.helpers import api_response

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(403, "账户已禁用")
    return {"access_token": create_access_token(user.username), "token_type": "bearer"}


@router.get("/me")
def me(current: User = Depends(get_current_user)):
    return api_response(data=UserResponse.model_validate(current).model_dump())
