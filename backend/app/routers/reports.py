"""報表：毛利、銷售率、淨利。

口徑說明（給未來的維護者）：
- 售出/營收：銷售異動淨額（銷售 − 銷售退回），營收用實際成交價
- 銷貨成本：售出數 × 該規格單位成本（台幣）
- 公關成本：轉公關件數 × 單位成本，計入檔期費用（不重複建帳）
- 淨利 = 毛利 − 檔期開支 − 公關成本
- 套組獨立成列（品項歸「套組」），營收不攤回內容物——攤分屬後期優化
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, extract, func, select
from sqlalchemy.orm import Session

from app import schemas
from app.deps import get_company_id, get_db
from app.models import (
    Artist,
    Event,
    Expense,
    InventoryMovement,
    ItemType,
    MovementType,
    Product,
    ProductVariant,
)

router = APIRouter(prefix="/reports", tags=["報表"])

SALE_TYPES = (MovementType.SALE.value, MovementType.SALE_RETURN.value)


def _variant_stats(db: Session, variant_ids: list[int]) -> dict:
    """{variant_id: (售出, 營收, 公關件數)}，一次查完。"""
    if not variant_ids:
        return {}
    rows = db.execute(
        select(
            InventoryMovement.variant_id,
            func.sum(
                case(
                    (
                        InventoryMovement.movement_type.in_(SALE_TYPES),
                        -InventoryMovement.quantity_delta,
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        InventoryMovement.movement_type.in_(SALE_TYPES),
                        -InventoryMovement.quantity_delta
                        * func.coalesce(InventoryMovement.sale_price_twd, 0),
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        InventoryMovement.movement_type
                        == MovementType.PR_GIFT.value,
                        -InventoryMovement.quantity_delta,
                    ),
                    else_=0,
                )
            ),
        )
        .where(InventoryMovement.variant_id.in_(variant_ids))
        .group_by(InventoryMovement.variant_id)
    ).all()
    return {r[0]: (int(r[1]), Decimal(r[2] or 0), int(r[3])) for r in rows}


def _product_variant_rows(db: Session, cid: int, event_id: int | None, year: int | None):
    """撈出範圍內所有規格與其商品/藝人/品項資訊。"""
    stmt = (
        select(
            ProductVariant.id,
            ProductVariant.production_qty,
            ProductVariant.cost_twd,
            Product.artist_id,
            Artist.name.label("artist_name"),
            Product.item_type_id,
            ItemType.name.label("item_type_name"),
            Product.is_bundle,
            Product.event_id,
        )
        .join(Product, ProductVariant.product_id == Product.id)
        .join(Artist, Product.artist_id == Artist.id)
        .outerjoin(ItemType, Product.item_type_id == ItemType.id)
        .join(Event, Product.event_id == Event.id)
        .where(Product.company_id == cid)
    )
    if event_id is not None:
        stmt = stmt.where(Product.event_id == event_id)
    if year is not None:
        stmt = stmt.where(extract("year", Event.start_date) == year)
    return db.execute(stmt).all()


def _sum_rows(rows, stats, key_fn, name_fn):
    """把規格列依 key 彙總成 ReportRow。"""
    acc: dict = {}
    for r in rows:
        sold, revenue, _pr = stats.get(r.id, (0, Decimal(0), 0))
        key = key_fn(r)
        if key not in acc:
            acc[key] = {
                "id": key,
                "name": name_fn(r),
                "production": 0,
                "sold": 0,
                "revenue": Decimal(0),
                "cogs": Decimal(0),
            }
        a = acc[key]
        a["production"] += r.production_qty
        a["sold"] += sold
        a["revenue"] += revenue
        a["cogs"] += Decimal(r.cost_twd) * sold
    out = []
    for a in acc.values():
        out.append(
            schemas.ReportRow(
                id=a["id"],
                name=a["name"],
                production=a["production"],
                sold=a["sold"],
                revenue=a["revenue"],
                cogs=a["cogs"],
                gross=a["revenue"] - a["cogs"],
                sell_through=a["sold"] / a["production"] if a["production"] else 0.0,
            )
        )
    out.sort(key=lambda x: x.revenue, reverse=True)
    return out


@router.get("/events/{event_id}", response_model=schemas.EventReport)
def event_report(
    event_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    event = db.scalar(
        select(Event).where(Event.id == event_id, Event.company_id == cid)
    )
    if event is None:
        raise HTTPException(404, "找不到這場活動")

    rows = _product_variant_rows(db, cid, event_id, None)
    stats = _variant_stats(db, [r.id for r in rows])

    production = sum(r.production_qty for r in rows)
    sold = sum(stats.get(r.id, (0, Decimal(0), 0))[0] for r in rows)
    revenue = sum((stats.get(r.id, (0, Decimal(0), 0))[1] for r in rows), Decimal(0))
    cogs = sum(
        (Decimal(r.cost_twd) * stats.get(r.id, (0, Decimal(0), 0))[0] for r in rows),
        Decimal(0),
    )
    pr_qty = sum(stats.get(r.id, (0, Decimal(0), 0))[2] for r in rows)
    pr_cost = sum(
        (Decimal(r.cost_twd) * stats.get(r.id, (0, Decimal(0), 0))[2] for r in rows),
        Decimal(0),
    )

    expenses = db.scalars(
        select(Expense).where(Expense.company_id == cid, Expense.event_id == event_id)
    ).all()
    expenses_total = sum((Decimal(e.amount_twd) for e in expenses), Decimal(0))
    gross = revenue - cogs

    return schemas.EventReport(
        event=schemas.EventOut.model_validate(event),
        production=production,
        sold=sold,
        sell_through=sold / production if production else 0.0,
        revenue=revenue,
        cogs=cogs,
        gross=gross,
        pr_qty=pr_qty,
        pr_cost=pr_cost,
        expenses=[schemas.ExpenseOut.model_validate(e) for e in expenses],
        expenses_total=expenses_total,
        net=gross - expenses_total - pr_cost,
        by_artist=_sum_rows(
            rows, stats, lambda r: r.artist_id, lambda r: r.artist_name
        ),
        by_item_type=_sum_rows(
            rows,
            stats,
            lambda r: r.item_type_id,  # 套組為 None，自然聚成一列
            lambda r: r.item_type_name or "套組",
        ),
    )


@router.get("/artists", response_model=list[schemas.SummaryRow])
def artists_summary(
    year: int | None = None,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    rows = _product_variant_rows(db, cid, None, year)
    stats = _variant_stats(db, [r.id for r in rows])
    return _summary(rows, stats, lambda r: (r.artist_id, r.artist_name))


@router.get("/item-types", response_model=list[schemas.SummaryRow])
def item_types_summary(
    year: int | None = None,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    rows = _product_variant_rows(db, cid, None, year)
    stats = _variant_stats(db, [r.id for r in rows])
    return _summary(
        rows, stats, lambda r: (r.item_type_id or 0, r.item_type_name or "套組")
    )


def _summary(rows, stats, key_fn):
    acc: dict = {}
    for r in rows:
        sold, revenue, _pr = stats.get(r.id, (0, Decimal(0), 0))
        key, name = key_fn(r)
        if key not in acc:
            acc[key] = {
                "id": key,
                "name": name,
                "events": set(),
                "production": 0,
                "sold": 0,
                "revenue": Decimal(0),
                "cogs": Decimal(0),
            }
        a = acc[key]
        a["events"].add(r.event_id)
        a["production"] += r.production_qty
        a["sold"] += sold
        a["revenue"] += revenue
        a["cogs"] += Decimal(r.cost_twd) * sold
    out = [
        schemas.SummaryRow(
            id=a["id"],
            name=a["name"],
            event_count=len(a["events"]),
            production=a["production"],
            sold=a["sold"],
            revenue=a["revenue"],
            cogs=a["cogs"],
            gross=a["revenue"] - a["cogs"],
            sell_through=a["sold"] / a["production"] if a["production"] else 0.0,
        )
        for a in acc.values()
    ]
    out.sort(key=lambda x: x.revenue, reverse=True)
    return out
