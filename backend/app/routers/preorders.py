from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.deps import get_company_id, get_db
from app.models import (
    InventoryMovement,
    MovementType,
    Preorder,
    PreorderStatus,
    RecordSource,
)
from app.routers.inventory import default_price, get_variant, physical_stock

router = APIRouter(prefix="/preorders", tags=["預購"])


def _get_or_404(
    db: Session, cid: int, preorder_id: int, for_update: bool = False
) -> Preorder:
    stmt = select(Preorder).where(
        Preorder.id == preorder_id, Preorder.company_id == cid
    )
    if for_update:
        # 鎖預購列：防同一筆被並發按兩次出貨而重複扣庫存（交接文件 1.1）
        stmt = stmt.with_for_update()
    preorder = db.scalar(stmt)
    if preorder is None:
        raise HTTPException(404, "找不到這筆預購")
    return preorder


def _ship_one(db: Session, cid: int, preorder: Preorder, body: schemas.PreorderShip):
    """出貨＝改狀態＋產生一筆銷售異動（通路：預購），此時才扣實體庫存。"""
    variant = get_variant(db, cid, preorder.variant_id)
    preorder.status = PreorderStatus.SHIPPED.value
    preorder.status_changed_date = body.ship_date
    db.add(
        InventoryMovement(
            company_id=cid,
            variant_id=preorder.variant_id,
            movement_type=MovementType.SALE.value,
            quantity_delta=-preorder.quantity,
            movement_date=body.ship_date,
            channel="preorder",
            sale_price_twd=body.sale_price_twd
            if body.sale_price_twd is not None
            else default_price(db, variant),
            source=RecordSource.MANUAL.value,
        )
    )


@router.get("", response_model=list[schemas.PreorderOut])
def list_preorders(
    variant_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    stmt = select(Preorder).where(Preorder.company_id == cid)
    if variant_id is not None:
        stmt = stmt.where(Preorder.variant_id == variant_id)
    if status is not None:
        stmt = stmt.where(Preorder.status == status)
    return db.scalars(stmt.order_by(Preorder.created_date.desc(), Preorder.id.desc())).all()


@router.post("", response_model=schemas.PreorderOut, status_code=201)
def create_preorder(
    body: schemas.PreorderCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    get_variant(db, cid, body.variant_id)
    # 預購可以超過目前實體庫存（貨可能還在生產），所以不做庫存檢查
    preorder = Preorder(
        company_id=cid,
        source=RecordSource.MANUAL.value,
        **body.model_dump(),
    )
    db.add(preorder)
    db.commit()
    return preorder


@router.post("/{preorder_id}/ship", response_model=schemas.PreorderOut)
def ship_preorder(
    preorder_id: int,
    body: schemas.PreorderShip,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    preorder = _get_or_404(db, cid, preorder_id)
    # 鎖定順序全系統一致：先鎖規格、再鎖預購（與 ship_all 相同，避免死鎖）
    get_variant(db, cid, preorder.variant_id, for_update=True)
    preorder = _get_or_404(db, cid, preorder_id, for_update=True)
    if preorder.status != PreorderStatus.RESERVED.value:
        raise HTTPException(409, "只有圈存中的預購可以出貨")
    if physical_stock(db, preorder.variant_id) < preorder.quantity:
        raise HTTPException(409, "實體庫存不足，請先入庫再出貨")
    _ship_one(db, cid, preorder, body)
    db.commit()
    return preorder


@router.post("/{preorder_id}/cancel", response_model=schemas.PreorderOut)
def cancel_preorder(
    preorder_id: int,
    body: schemas.PreorderCancel,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    preorder = _get_or_404(db, cid, preorder_id, for_update=True)
    if preorder.status != PreorderStatus.RESERVED.value:
        raise HTTPException(409, "只有圈存中的預購可以取消")
    preorder.status = PreorderStatus.CANCELLED.value
    preorder.status_changed_date = body.cancel_date
    db.commit()
    return preorder


@router.post("/{preorder_id}/unship", response_model=schemas.PreorderOut)
def unship_preorder(
    preorder_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    """出貨退回圈存：帳（出貨異動）與約（預購狀態）在同一交易內一起還原。

    這是「刪除預購出貨異動造成帳約脫鉤」的正規替代做法（交接文件 1.3）。
    """
    preorder = _get_or_404(db, cid, preorder_id)
    # 鎖定順序與全系統一致：先規格、後預購
    get_variant(db, cid, preorder.variant_id, for_update=True)
    preorder = _get_or_404(db, cid, preorder_id, for_update=True)
    if preorder.status != PreorderStatus.SHIPPED.value:
        raise HTTPException(409, "只有已出貨的預購可以退回圈存")

    # 找對應的出貨異動：同規格、預購通路、同數量；優先比對出貨日
    def find_movement(with_date: bool):
        stmt = (
            select(InventoryMovement)
            .where(
                InventoryMovement.company_id == cid,
                InventoryMovement.variant_id == preorder.variant_id,
                InventoryMovement.movement_type == MovementType.SALE.value,
                InventoryMovement.channel == "preorder",
                InventoryMovement.quantity_delta == -preorder.quantity,
            )
            .order_by(InventoryMovement.id.desc())
            .limit(1)
        )
        if with_date and preorder.status_changed_date is not None:
            stmt = stmt.where(
                InventoryMovement.movement_date == preorder.status_changed_date
            )
        return db.scalar(stmt)

    movement = find_movement(with_date=True) or find_movement(with_date=False)
    if movement is None:
        raise HTTPException(
            409, "找不到對應的出貨異動（可能已被刪除），請由管理者手動核帳"
        )

    db.delete(movement)  # 庫存加回來
    preorder.status = PreorderStatus.RESERVED.value  # 圈存恢復
    preorder.status_changed_date = None
    db.commit()  # 同一交易：要嘛全成，要嘛全不動
    return preorder


@router.post("/ship-all", status_code=201)
def ship_all(
    body: schemas.PreorderShipAll,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    """把某規格所有圈存中的預購一次出貨。"""
    get_variant(db, cid, body.variant_id, for_update=True)  # 先鎖規格
    reserved = db.scalars(
        select(Preorder)
        .where(
            Preorder.company_id == cid,
            Preorder.variant_id == body.variant_id,
            Preorder.status == PreorderStatus.RESERVED.value,
        )
        .with_for_update()  # 再鎖預購列
    ).all()
    if not reserved:
        raise HTTPException(409, "這個規格沒有圈存中的預購")
    total = sum(p.quantity for p in reserved)
    if physical_stock(db, body.variant_id) < total:
        raise HTTPException(409, f"實體庫存不足（圈存共 {total} 件），請先入庫")
    ship = schemas.PreorderShip(
        ship_date=body.ship_date, sale_price_twd=body.sale_price_twd
    )
    for preorder in reserved:
        _ship_one(db, cid, preorder, ship)
    db.commit()
    return {"shipped": len(reserved), "total_qty": total}
