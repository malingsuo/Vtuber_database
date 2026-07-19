from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas
from app.deps import get_company_id, get_db
from app.models import Vendor

router = APIRouter(prefix="/vendors", tags=["廠商"])


@router.get("", response_model=list[schemas.VendorOut])
def list_vendors(
    db: Session = Depends(get_db), cid: int = Depends(get_company_id)
):
    return db.scalars(
        select(Vendor).where(Vendor.company_id == cid).order_by(Vendor.id)
    ).all()


@router.post("", response_model=schemas.VendorOut, status_code=201)
def create_vendor(
    body: schemas.VendorCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    vendor = Vendor(company_id=cid, **body.model_dump())
    db.add(vendor)
    db.commit()
    return vendor


@router.put("/{vendor_id}", response_model=schemas.VendorOut)
def update_vendor(
    vendor_id: int,
    body: schemas.VendorCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    vendor = db.scalar(
        select(Vendor).where(Vendor.id == vendor_id, Vendor.company_id == cid)
    )
    if vendor is None:
        raise HTTPException(404, "找不到這家廠商")
    for key, value in body.model_dump().items():
        setattr(vendor, key, value)
    db.commit()
    return vendor


@router.delete("/{vendor_id}", status_code=204)
def delete_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    vendor = db.scalar(
        select(Vendor).where(Vendor.id == vendor_id, Vendor.company_id == cid)
    )
    if vendor is None:
        raise HTTPException(404, "找不到這家廠商")
    db.delete(vendor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "已有商品或報價關聯這家廠商，不能刪除")
