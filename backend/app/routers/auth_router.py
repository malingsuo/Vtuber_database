from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.auth import create_token, hash_password, verify_password
from app.deps import get_current_user, get_db, require_admin
from app.models import AuditLog, Company, User
from app.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["登入與使用者"])


@router.post("/login", response_model=schemas.TokenOut)
@limiter.limit("5/minute")  # 防暴力猜密碼；429 訊息見 rate_limit.py
def login(request: Request, body: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "帳號或密碼錯誤")
    if not user.is_active:
        raise HTTPException(403, "帳號已停用，請聯絡管理者")
    company = db.get(Company, user.company_id)
    if company is None or not company.is_active:
        raise HTTPException(403, "貴公司的服務已停用，請聯絡平台管理員")
    db.add(
        AuditLog(
            company_id=user.company_id,
            user_id=user.id,
            action="login",
            table_name="users",
            record_id=user.id,
        )
    )
    db.commit()
    return schemas.TokenOut(
        token=create_token(user), user=schemas.UserOut.model_validate(user)
    )


@router.get("/me", response_model=schemas.UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", status_code=204)
def change_password(
    body: schemas.ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(403, "原密碼錯誤")
    user.password_hash = hash_password(body.new_password)
    db.add(user)
    db.commit()


# ── 使用者管理（僅管理者）──

@router.get("/users", response_model=list[schemas.UserOut])
def list_users(
    admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    return db.scalars(
        select(User).where(User.company_id == admin.company_id).order_by(User.id)
    ).all()


@router.post("/users", response_model=schemas.UserOut, status_code=201)
def create_user(
    body: schemas.UserCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # username 全系統唯一（登入只憑帳號名，見交接文件漏洞 A）
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(409, "帳號名稱已被使用（全系統唯一），請換一個")
    user = User(
        company_id=admin.company_id,
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
    )
    db.add(user)
    db.commit()
    return user


@router.put("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    body: schemas.UserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(User.id == user_id, User.company_id == admin.company_id)
    )
    if user is None:
        raise HTTPException(404, "找不到這個使用者")
    if user.id == admin.id and (
        (body.role is not None and body.role != "admin")
        or body.is_active is False
    ):
        raise HTTPException(409, "不能把自己降級或停用（避免鎖死系統）")
    data = body.model_dump(exclude_unset=True)
    if "password" in data:
        password = data.pop("password")
        if password:
            user.password_hash = hash_password(password)
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    return user
