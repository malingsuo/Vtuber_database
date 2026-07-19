from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.deps import get_company_id, get_db
from app.models import ItemType, Quote, Vendor

router = APIRouter(prefix="/quotes", tags=["報價紀錄"])


@router.get("", response_model=list[schemas.QuoteOut])
def list_quotes(
    item_type_id: int | None = None,
    vendor_id: int | None = None,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    stmt = select(Quote).where(Quote.company_id == cid)
    if item_type_id is not None:
        stmt = stmt.where(Quote.item_type_id == item_type_id)
    if vendor_id is not None:
        stmt = stmt.where(Quote.vendor_id == vendor_id)
    return db.scalars(
        stmt.order_by(Quote.quote_date.desc(), Quote.id.desc())
    ).all()


@router.post("", response_model=schemas.QuoteOut, status_code=201)
def create_quote(
    body: schemas.QuoteCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    if not db.scalar(
        select(ItemType.id).where(
            ItemType.id == body.item_type_id, ItemType.company_id == cid
        )
    ):
        raise HTTPException(422, "找不到指定的品項類別")
    if body.vendor_id is not None and not db.scalar(
        select(Vendor.id).where(
            Vendor.id == body.vendor_id, Vendor.company_id == cid
        )
    ):
        raise HTTPException(422, "找不到指定的廠商")
    quote = Quote(
        company_id=cid,
        unit_price_twd=(body.unit_price * body.exchange_rate).quantize(
            Decimal("0.01")
        ),
        **body.model_dump(),
    )
    db.add(quote)
    db.commit()
    return quote


@router.delete("/{quote_id}", status_code=204)
def delete_quote(
    quote_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    quote = db.scalar(
        select(Quote).where(Quote.id == quote_id, Quote.company_id == cid)
    )
    if quote is None:
        raise HTTPException(404, "找不到這筆報價")
    db.delete(quote)
    db.commit()
