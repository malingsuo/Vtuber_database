from collections.abc import Generator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import decode_token
from app.db import SessionLocal
from app.models import Company, User, UserRole


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "請先登入")
    payload = decode_token(header.removeprefix("Bearer "))
    if payload is None:
        raise HTTPException(401, "登入已過期，請重新登入")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(401, "帳號不存在或已停用")
    company = db.get(Company, user.company_id)
    if company is None or not company.is_active:
        raise HTTPException(403, "貴公司的服務已停用，請聯絡平台管理員")
    return user


def authorize(request: Request, user: User = Depends(get_current_user)) -> User:
    """掛在所有業務路由上：唯讀角色擋掉任何寫入。"""
    if request.method != "GET" and user.role == UserRole.VIEWER.value:
        raise HTTPException(403, "唯讀帳號不能修改資料")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in (UserRole.ADMIN.value, UserRole.SUPERADMIN.value):
        raise HTTPException(403, "此操作僅限管理者")
    return user


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.SUPERADMIN.value:
        raise HTTPException(403, "此操作僅限總管理員")
    return user


def get_company_id(user: User = Depends(get_current_user)) -> int:
    """資料隔離的核心：company_id 一律來自登入者，不再是固定值。"""
    return user.company_id
