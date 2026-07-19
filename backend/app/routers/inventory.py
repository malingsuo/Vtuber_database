from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas
from app.deps import get_company_id, get_db
from app.models import (
    InventoryMovement,
    MovementType,
    Preorder,
    PreorderStatus,
    Product,
    ProductVariant,
    RecordSource,
)

router = APIRouter(prefix="/inventory", tags=["庫存"])

# 各異動類型對庫存的方向；盤點調整由輸入的正負號決定
SIGN = {
    MovementType.INBOUND.value: 1,
    MovementType.SALE.value: -1,
    MovementType.SALE_RETURN.value: 1,
    MovementType.PR_GIFT.value: -1,
    MovementType.SCRAP.value: -1,
}


def get_variant(db: Session, cid: int, variant_id: int) -> ProductVariant:
    variant = db.scalar(
        select(ProductVariant).where(
            ProductVariant.id == variant_id, ProductVariant.company_id == cid
        )
    )
    if variant is None:
        raise HTTPException(404, "找不到這個商品規格")
    return variant


def physical_stock(db: Session, variant_id: int) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)).where(
                InventoryMovement.variant_id == variant_id
            )
        )
    )


def inbound_total(db: Session, variant_id: int) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)).where(
                InventoryMovement.variant_id == variant_id,
                InventoryMovement.movement_type == MovementType.INBOUND.value,
            )
        )
    )


def reserved_qty(db: Session, variant_id: int) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Preorder.quantity), 0)).where(
                Preorder.variant_id == variant_id,
                Preorder.status == PreorderStatus.RESERVED.value,
            )
        )
    )


def default_price(db: Session, variant: ProductVariant) -> Decimal:
    return db.scalar(select(Product.price_twd).where(Product.id == variant.product_id))


@router.get("/variants/{variant_id}/stock", response_model=schemas.StockOut)
def get_stock(
    variant_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    variant = get_variant(db, cid, variant_id)
    physical = physical_stock(db, variant_id)
    reserved = reserved_qty(db, variant_id)
    return schemas.StockOut(
        variant_id=variant_id,
        physical=physical,
        reserved=reserved,
        available=physical - reserved,
        production_qty=variant.production_qty,
        inbound_qty=inbound_total(db, variant_id),
    )


@router.get(
    "/variants/{variant_id}/movements", response_model=list[schemas.MovementOut]
)
def list_movements(
    variant_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    get_variant(db, cid, variant_id)
    return db.scalars(
        select(InventoryMovement)
        .where(InventoryMovement.variant_id == variant_id)
        .order_by(InventoryMovement.movement_date.desc(), InventoryMovement.id.desc())
    ).all()


@router.post("/movements", response_model=schemas.MovementOut, status_code=201)
def create_movement(
    body: schemas.MovementCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    variant = get_variant(db, cid, body.variant_id)

    if body.movement_type == MovementType.ADJUSTMENT.value:
        delta = body.quantity  # 帶正負號
    else:
        delta = SIGN[body.movement_type] * body.quantity

    # 累計入庫超過製作量是異常（廠商多做/補瑕疵品/輸入錯誤），必須留下原因
    if body.movement_type == MovementType.INBOUND.value:
        done = inbound_total(db, body.variant_id)
        excess = done + body.quantity - variant.production_qty
        if excess > 0 and not (body.notes and body.notes.strip()):
            raise HTTPException(
                409,
                f"累計入庫將達 {done + body.quantity}，超過製作量 "
                f"{variant.production_qty} 共 {excess} 件（已入庫 {done}）。"
                f"超量入庫請在備註填寫原因",
            )

    if delta < 0 and physical_stock(db, body.variant_id) + delta < 0:
        raise HTTPException(409, "實體庫存不足，無法扣除這個數量")

    sale_price = body.sale_price_twd
    if body.movement_type == MovementType.SALE.value and sale_price is None:
        sale_price = default_price(db, variant)

    movement = InventoryMovement(
        company_id=cid,
        variant_id=body.variant_id,
        movement_type=body.movement_type,
        quantity_delta=delta,
        movement_date=body.movement_date,
        channel=body.channel,
        sale_price_twd=sale_price,
        sold_out_today=body.sold_out_today,
        recipient=body.recipient,
        purpose=body.purpose,
        source=RecordSource.MANUAL.value,
        notes=body.notes,
    )
    db.add(movement)
    db.commit()
    return movement


@router.delete("/movements/{movement_id}", status_code=204)
def delete_movement(
    movement_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    """刪除一筆異動明細（輸入錯誤的修正手段）。

    TODO 帳號權限里程碑：此操作限管理者，並要求輸入密碼確認。
    """
    movement = db.scalar(
        select(InventoryMovement).where(
            InventoryMovement.id == movement_id,
            InventoryMovement.company_id == cid,
        )
    )
    if movement is None:
        raise HTTPException(404, "找不到這筆異動")
    # 刪掉後實體庫存不可變負（例如那批入庫的貨已被後續銷售用掉）
    if physical_stock(db, movement.variant_id) - movement.quantity_delta < 0:
        raise HTTPException(
            409, "刪除這筆會讓實體庫存變成負數（這批貨已被後續異動用掉），不能刪除"
        )
    db.delete(movement)
    db.commit()


@router.post("/daily-sales", status_code=201)
def daily_sales(
    body: schemas.DailySalesCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    """逐日銷售輸入：一次寫入整場活動的當日銷量（全部成功或全部不寫）。"""
    created = 0
    for item in body.items:
        variant = get_variant(db, cid, item.variant_id)
        if physical_stock(db, item.variant_id) - item.quantity < 0:
            db.rollback()
            raise HTTPException(
                409,
                f"「{variant.product.name}（{variant.variant_name}）」實體庫存不足",
            )
        db.add(
            InventoryMovement(
                company_id=cid,
                variant_id=item.variant_id,
                movement_type=MovementType.SALE.value,
                quantity_delta=-item.quantity,
                movement_date=body.movement_date,
                channel=body.channel,
                sale_price_twd=item.sale_price_twd
                if item.sale_price_twd is not None
                else default_price(db, variant),
                sold_out_today=item.sold_out_today,
                source=RecordSource.MANUAL.value,
            )
        )
        db.flush()  # 讓下一筆的庫存檢查看得到這一筆
        created += 1
    db.commit()
    return {"created": created}
