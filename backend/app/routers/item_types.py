from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas
from app.deps import get_company_id, get_db
from app.models import ItemType

router = APIRouter(prefix="/item-types", tags=["品項類別"])


@router.get("", response_model=list[schemas.ItemTypeOut])
def list_item_types(
    db: Session = Depends(get_db), cid: int = Depends(get_company_id)
):
    return db.scalars(
        select(ItemType).where(ItemType.company_id == cid).order_by(ItemType.id)
    ).all()


@router.post("", response_model=schemas.ItemTypeOut, status_code=201)
def create_item_type(
    body: schemas.ItemTypeCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    item_type = ItemType(company_id=cid, **body.model_dump())
    db.add(item_type)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "同名品項類別已存在")
    return item_type


@router.put("/{item_type_id}", response_model=schemas.ItemTypeOut)
def update_item_type(
    item_type_id: int,
    body: schemas.ItemTypeCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    item_type = db.scalar(
        select(ItemType).where(ItemType.id == item_type_id, ItemType.company_id == cid)
    )
    if item_type is None:
        raise HTTPException(404, "找不到這個品項類別")
    for key, value in body.model_dump().items():
        setattr(item_type, key, value)
    db.commit()
    return item_type


@router.delete("/{item_type_id}", status_code=204)
def delete_item_type(
    item_type_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    item_type = db.scalar(
        select(ItemType).where(ItemType.id == item_type_id, ItemType.company_id == cid)
    )
    if item_type is None:
        raise HTTPException(404, "找不到這個品項類別")
    db.delete(item_type)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "已有商品使用這個品項類別，不能刪除")
