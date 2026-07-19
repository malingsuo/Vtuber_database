from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.deps import get_company_id, get_db
from app.models import (
    Artist,
    BundleItem,
    Event,
    InventoryMovement,
    ItemType,
    Preorder,
    Product,
    ProductVariant,
)

router = APIRouter(prefix="/products", tags=["商品"])


def _load(db: Session, cid: int, product_id: int) -> Product:
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.company_id == cid)
        .options(
            selectinload(Product.variants),
            selectinload(Product.bundle_items),
        )
    )
    if product is None:
        raise HTTPException(404, "找不到這個商品")
    return product


def _check_fk(db: Session, cid: int, body: schemas.ProductCreate) -> None:
    """確認關聯對象都存在且屬於同一公司，錯誤訊息比資料庫外鍵錯誤友善。"""
    checks = [
        (Event, body.event_id, "活動"),
        (Artist, body.artist_id, "藝人"),
    ]
    if body.item_type_id is not None:
        checks.append((ItemType, body.item_type_id, "品項類別"))
    for model, ref_id, label in checks:
        if not db.scalar(
            select(model.id).where(model.id == ref_id, model.company_id == cid)
        ):
            raise HTTPException(422, f"找不到指定的{label}（id={ref_id}）")


@router.get("", response_model=list[schemas.ProductOut])
def list_products(
    event_id: int | None = None,
    artist_id: int | None = None,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    stmt = (
        select(Product)
        .where(Product.company_id == cid)
        .options(
            selectinload(Product.variants), selectinload(Product.bundle_items)
        )
        .order_by(Product.id)
    )
    if event_id is not None:
        stmt = stmt.where(Product.event_id == event_id)
    if artist_id is not None:
        stmt = stmt.where(Product.artist_id == artist_id)
    return db.scalars(stmt).all()


@router.post("", response_model=schemas.ProductOut, status_code=201)
def create_product(
    body: schemas.ProductCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    """新建流程的核心：一次建立商品＋規格（＋套組內容物）。"""
    _check_fk(db, cid, body)

    product = Product(
        company_id=cid,
        **body.model_dump(exclude={"variants", "bundle_items"}),
    )
    db.add(product)
    db.flush()

    for v in body.variants:
        cost_twd = (v.cost_amount * v.exchange_rate).quantize(Decimal("0.01"))
        db.add(
            ProductVariant(
                company_id=cid,
                product_id=product.id,
                cost_twd=cost_twd,
                **v.model_dump(),
            )
        )

    for item in body.bundle_items:
        target = db.scalar(
            select(ProductVariant).where(
                ProductVariant.id == item.variant_id,
                ProductVariant.company_id == cid,
            )
        )
        if target is None:
            db.rollback()
            raise HTTPException(422, f"套組內容物規格不存在（id={item.variant_id}）")
        db.add(
            BundleItem(
                company_id=cid,
                bundle_product_id=product.id,
                variant_id=item.variant_id,
                quantity=item.quantity,
            )
        )

    db.commit()
    return _load(db, cid, product.id)


@router.get("/{product_id}", response_model=schemas.ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    return _load(db, cid, product_id)


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    """刪除商品（含其規格與套組內容設定）。

    帳務保護：規格已有庫存異動或預購紀錄就不能刪——那些是歷史帳，
    刪了帳就對不起來。被其他套組收錄的商品也不能刪。
    """
    product = _load(db, cid, product_id)
    variant_ids = [v.id for v in product.variants]

    if variant_ids:
        if db.scalar(
            select(InventoryMovement.id)
            .where(InventoryMovement.variant_id.in_(variant_ids))
            .limit(1)
        ):
            raise HTTPException(409, "這個商品已有庫存/銷售紀錄，不能刪除")
        if db.scalar(
            select(Preorder.id).where(Preorder.variant_id.in_(variant_ids)).limit(1)
        ):
            raise HTTPException(409, "這個商品已有預購紀錄，不能刪除")
        if db.scalar(
            select(BundleItem.id)
            .where(BundleItem.variant_id.in_(variant_ids))
            .limit(1)
        ):
            raise HTTPException(409, "這個商品被套組收錄為內容物，請先刪除或修改該套組")

    for item in product.bundle_items:
        db.delete(item)
    for variant in product.variants:
        db.delete(variant)
    db.delete(product)
    db.commit()


@router.put("/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    body: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    product = _load(db, cid, product_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    db.commit()
    return _load(db, cid, product_id)
