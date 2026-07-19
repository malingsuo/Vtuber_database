from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, extract, func, select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.deps import get_company_id, get_db
from app.models import (
    Artist,
    BundleItem,
    Event,
    InventoryMovement,
    MovementType,
    Preorder,
    PreorderStatus,
    Product,
    ProductVariant,
)

router = APIRouter(prefix="/events", tags=["活動"])

SALE_TYPES = (MovementType.SALE.value, MovementType.SALE_RETURN.value)


def _get_or_404(db: Session, cid: int, event_id: int) -> Event:
    event = db.scalar(
        select(Event).where(Event.id == event_id, Event.company_id == cid)
    )
    if event is None:
        raise HTTPException(404, "找不到這場活動")
    return event


@router.get("/years", response_model=list[int])
def list_years(db: Session = Depends(get_db), cid: int = Depends(get_company_id)):
    """查詢流程第一步：有活動的年份清單（新到舊）。"""
    years = db.scalars(
        select(extract("year", Event.start_date))
        .where(Event.company_id == cid)
        .distinct()
        .order_by(extract("year", Event.start_date).desc())
    ).all()
    return [int(y) for y in years]


@router.get("", response_model=list[schemas.EventOut])
def list_events(
    year: int | None = None,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    """查詢流程第二步：活動清單，可用 ?year= 過濾（下拉選單連動）。"""
    stmt = select(Event).where(Event.company_id == cid)
    if year is not None:
        stmt = stmt.where(extract("year", Event.start_date) == year)
    return db.scalars(stmt.order_by(Event.start_date.desc())).all()


@router.post("", response_model=schemas.EventOut, status_code=201)
def create_event(
    body: schemas.EventCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    event = Event(company_id=cid, **body.model_dump())
    db.add(event)
    db.commit()
    return event


@router.get("/{event_id}", response_model=schemas.EventOut)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    return _get_or_404(db, cid, event_id)


@router.put("/{event_id}", response_model=schemas.EventOut)
def update_event(
    event_id: int,
    body: schemas.EventUpdate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    event = _get_or_404(db, cid, event_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(event, key, value)
    db.commit()
    return event


@router.get("/{event_id}/overview", response_model=schemas.EventOverview)
def event_overview(
    event_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    """查詢流程第三步：整場活動依藝人分組的商品明細＋銷售統計。"""
    event = _get_or_404(db, cid, event_id)

    products = db.scalars(
        select(Product)
        .where(Product.event_id == event_id, Product.company_id == cid)
        .options(selectinload(Product.variants), selectinload(Product.artist))
        .order_by(Product.artist_id, Product.id)
    ).all()

    variant_ids = [v.id for p in products for v in p.variants]

    # 一次查完所有規格的庫存/銷量/營收，避免 N+1 查詢
    stats: dict[int, tuple[int, int, Decimal]] = {}
    if variant_ids:
        rows = db.execute(
            select(
                InventoryMovement.variant_id,
                func.sum(InventoryMovement.quantity_delta),  # 目前庫存
                func.sum(
                    case(
                        (
                            InventoryMovement.movement_type.in_(SALE_TYPES),
                            -InventoryMovement.quantity_delta,
                        ),
                        else_=0,
                    )
                ),  # 淨售出
                func.sum(
                    case(
                        (
                            InventoryMovement.movement_type.in_(SALE_TYPES),
                            -InventoryMovement.quantity_delta
                            * func.coalesce(InventoryMovement.sale_price_twd, 0),
                        ),
                        else_=0,
                    )
                ),  # 營收
            )
            .where(InventoryMovement.variant_id.in_(variant_ids))
            .group_by(InventoryMovement.variant_id)
        ).all()
        stats = {r[0]: (int(r[1]), int(r[2]), Decimal(r[3] or 0)) for r in rows}

    # 圈存量（未出貨預購）：一次查完
    reserved_map: dict[int, int] = {}
    if variant_ids:
        reserved_rows = db.execute(
            select(Preorder.variant_id, func.sum(Preorder.quantity))
            .where(
                Preorder.variant_id.in_(variant_ids),
                Preorder.status == PreorderStatus.RESERVED.value,
            )
            .group_by(Preorder.variant_id)
        ).all()
        reserved_map = {r[0]: int(r[1]) for r in reserved_rows}

    # 套組內容物：一次查完，組成「商品名（規格）× 數量」
    bundle_ids = [p.id for p in products if p.is_bundle]
    contents_map: dict[int, list[schemas.BundleContent]] = {}
    if bundle_ids:
        content_rows = db.execute(
            select(
                BundleItem.bundle_product_id,
                Product.name,
                ProductVariant.variant_name,
                BundleItem.quantity,
            )
            .join(ProductVariant, BundleItem.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(BundleItem.bundle_product_id.in_(bundle_ids))
        ).all()
        for bid, pname, vname, qty in content_rows:
            contents_map.setdefault(bid, []).append(
                schemas.BundleContent(name=f"{pname}（{vname}）", quantity=qty)
            )

    blocks: list[schemas.ArtistBlock] = []
    current_artist: Artist | None = None
    for product in products:
        if current_artist is None or product.artist_id != current_artist.id:
            current_artist = product.artist
            blocks.append(
                schemas.ArtistBlock(
                    artist=schemas.ArtistOut.model_validate(current_artist),
                    products=[],
                )
            )
        blocks[-1].products.append(
            schemas.ProductWithStats(
                id=product.id,
                item_type_id=product.item_type_id,
                name=product.name,
                price_twd=product.price_twd,
                is_bundle=product.is_bundle,
                bundle_contents=contents_map.get(product.id, []),
                variants=[
                    schemas.VariantStats(
                        id=v.id,
                        variant_name=v.variant_name,
                        production_qty=v.production_qty,
                        cost_twd=v.cost_twd,
                        stock_qty=stats.get(v.id, (0, 0, Decimal(0)))[0],
                        sold_qty=stats.get(v.id, (0, 0, Decimal(0)))[1],
                        reserved_qty=reserved_map.get(v.id, 0),
                        available_qty=stats.get(v.id, (0, 0, Decimal(0)))[0]
                        - reserved_map.get(v.id, 0),
                        revenue_twd=stats.get(v.id, (0, 0, Decimal(0)))[2],
                    )
                    for v in product.variants
                ],
            )
        )

    return schemas.EventOverview(
        event=schemas.EventOut.model_validate(event), artists=blocks
    )
