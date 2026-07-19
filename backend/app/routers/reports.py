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
    BundleItem,
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
            Product.id.label("product_id"),
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


def _apply_bundle_allocation(db: Session, rows, stats) -> tuple[dict, bool]:
    """套組營收攤分（Phase 1）：把套組的售出/營收按權重加回內容物，套組歸零。

    權重 = 內容物單售定價 × 件數 ÷ Σ(定價 × 件數)；分母為 0（全贈品）平均分攤。
    分攤採「逐項捨入＋餘數塞給最大權重者」，保證加總與原值一分不差。
    回傳 (攤分後的 stats, 是否有套組被攤分)。
    """
    bundle_variants: dict[int, list[int]] = {}  # bundle product_id -> [variant ids]
    for r in rows:
        if r.is_bundle:
            bundle_variants.setdefault(r.product_id, []).append(r.id)
    if not bundle_variants:
        return stats, False

    content_rows = db.execute(
        select(
            BundleItem.bundle_product_id,
            BundleItem.variant_id,
            BundleItem.quantity,
            Product.price_twd,
        )
        .join(ProductVariant, BundleItem.variant_id == ProductVariant.id)
        .join(Product, ProductVariant.product_id == Product.id)
        .where(BundleItem.bundle_product_id.in_(bundle_variants))
    ).all()

    event_variant_ids = {r.id for r in rows}
    # 可變副本：{variant_id: [sold, revenue, pr_qty]}
    new_stats = {vid: [s[0], s[1], s[2]] for vid, s in stats.items()}
    allocated_any = False

    for pid, vids in bundle_variants.items():
        # 只攤給「同活動內」的內容物；跨活動引用（資料模型允許但 UI 不會產生）
        # 的部分保留在套組上，避免營收憑空消失
        items = [
            c for c in content_rows
            if c.bundle_product_id == pid and c.variant_id in event_variant_ids
        ]
        if not items:
            continue

        bundle_sold = sum(new_stats.get(v, [0])[0] for v in vids)
        bundle_rev = sum(
            (new_stats.get(v, [0, Decimal(0)])[1] for v in vids), Decimal(0)
        )
        if bundle_sold == 0 and bundle_rev == 0:
            allocated_any = True  # 沒東西可攤，但口徑上視為已攤分（歸零維持）
            continue

        bases = [Decimal(c.price_twd) * c.quantity for c in items]
        total_base = sum(bases, Decimal(0))
        if total_base > 0:
            weights = [b / total_base for b in bases]
        else:  # 內容物全是贈品 → 平均分攤
            weights = [Decimal(1) / len(items)] * len(items)
        top = max(range(len(items)), key=lambda i: weights[i])

        rev_parts = [(bundle_rev * w).quantize(Decimal("0.01")) for w in weights]
        rev_parts[top] += bundle_rev - sum(rev_parts, Decimal(0))  # 餘數補回
        sold_parts = [int(round(bundle_sold * float(w))) for w in weights]
        sold_parts[top] += bundle_sold - sum(sold_parts)

        for c, rev_i, sold_i in zip(items, rev_parts, sold_parts):
            target = new_stats.setdefault(c.variant_id, [0, Decimal(0), 0])
            target[0] += sold_i
            target[1] += rev_i
        for v in vids:  # 套組自身歸零（公關件數不動，公關成本另計）
            if v in new_stats:
                new_stats[v][0] = 0
                new_stats[v][1] = Decimal(0)
        allocated_any = True

    return {vid: tuple(s) for vid, s in new_stats.items()}, allocated_any


@router.get("/events/{event_id}", response_model=schemas.EventReport)
def event_report(
    event_id: int,
    allocate_bundles: bool = False,
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

    allocated_any = False
    if allocate_bundles:
        revenue_before = sum(
            (stats.get(r.id, (0, Decimal(0), 0))[1] for r in rows), Decimal(0)
        )
        stats, allocated_any = _apply_bundle_allocation(db, rows, stats)
        revenue_after = sum(
            (stats.get(r.id, (0, Decimal(0), 0))[1] for r in rows), Decimal(0)
        )
        # 驗收等式（ROADMAP Phase 1）：攤分不能改變活動總營收，差一分即中止
        if revenue_after != revenue_before:
            raise HTTPException(
                500,
                f"攤分檢核失敗：攤分前 {revenue_before} ≠ 攤分後 {revenue_after}，"
                "已中止回傳，請回報開發者",
            )

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

    by_item_type = _sum_rows(
        rows,
        stats,
        lambda r: r.item_type_id,  # 套組為 None，自然聚成一列
        lambda r: r.item_type_name or "套組",
    )
    if allocated_any:
        for row in by_item_type:
            if row.id is None:  # 「套組」彙總列
                row.allocated = True

    return schemas.EventReport(
        event=schemas.EventOut.model_validate(event),
        allocate_bundles=allocate_bundles,
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
        by_item_type=by_item_type,
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
