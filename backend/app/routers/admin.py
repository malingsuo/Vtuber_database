"""總管理員專用：公司（租戶）的開通與停用。

總管理員只管「公司」層級，看不到各公司的業務資料——
業務 API 全部以登入者的 company_id 過濾，總管理員的 company_id
是平台自己的公司，自然查不到別家的資料。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas
from app.auth import hash_password
from app.deps import get_db, require_superadmin
from app.models import Company, User, UserRole

router = APIRouter(prefix="/admin", tags=["公司管理（總管理員）"])


@router.get("/companies", response_model=list[schemas.CompanyOut])
def list_companies(
    _su: User = Depends(require_superadmin), db: Session = Depends(get_db)
):
    counts = dict(
        db.execute(
            select(User.company_id, func.count()).group_by(User.company_id)
        ).all()
    )
    companies = db.scalars(select(Company).order_by(Company.id)).all()
    return [
        schemas.CompanyOut(
            id=c.id, name=c.name, is_active=c.is_active,
            user_count=counts.get(c.id, 0),
        )
        for c in companies
    ]


@router.post("/companies", response_model=schemas.CompanyOut, status_code=201)
def create_company(
    body: schemas.CompanyCreate,
    _su: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """開通新公司：建立公司＋該公司的第一個小管理員帳號。"""
    if db.scalar(select(Company.id).where(Company.name == body.name)):
        raise HTTPException(409, "同名公司已存在")
    if db.scalar(select(User.id).where(User.username == body.admin_username)):
        raise HTTPException(409, "小管理員帳號名稱已被使用（全系統唯一），請換一個")
    company = Company(name=body.name)
    db.add(company)
    db.flush()
    db.add(
        User(
            company_id=company.id,
            username=body.admin_username,
            password_hash=hash_password(body.admin_password),
            display_name=body.admin_display_name or "管理者",
            role=UserRole.ADMIN.value,
        )
    )
    db.commit()
    return schemas.CompanyOut(
        id=company.id, name=company.name, is_active=company.is_active, user_count=1
    )


@router.put("/companies/{company_id}", response_model=schemas.CompanyOut)
def update_company(
    company_id: int,
    body: schemas.CompanyUpdate,
    su: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "找不到這家公司")
    if company.id == su.company_id and not body.is_active:
        raise HTTPException(409, "不能停用平台自己的公司（會把總管理員鎖在門外）")
    company.is_active = body.is_active
    db.commit()
    user_count = db.scalar(
        select(func.count()).select_from(User).where(User.company_id == company.id)
    )
    return schemas.CompanyOut(
        id=company.id, name=company.name, is_active=company.is_active,
        user_count=user_count,
    )
