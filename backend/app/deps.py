"""FastAPI 依赖：数据库会话与当前登录用户。"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if cred is None or not cred.credentials:
        raise HTTPException(status_code=401, detail="请先登录")
    uid = decode_token(cred.credentials)
    if uid is None:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = db.get(User, uid)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
