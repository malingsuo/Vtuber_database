"""預測模組：分層統計估需求 + 報童模型算建議訂量。

兩層架構（設計定案）：
1. 需求估計層——目前用分層統計：以「該藝人 × 該品項」的歷史為主，
   樣本不足時往「該品項全藝人平均 × 藝人熱度係數」退階。
   完售的觀測是需求下限（真實需求 ≥ 售出量），以 SOLD_OUT_UPLIFT 上修。
   之後資料量夠時，這一層可換成時間序列（預購曲線外推），決策層不用動。
2. 決策層——報童模型（Newsvendor）：
   關鍵比率 CR = (p−c)/(p−s)，最適訂量 Q* = μ + σ·Φ⁻¹(CR)。
   期望利潤 E[π] = (p−c)·Q − (p−s)·E[(Q−D)⁺]，D 以常態近似。
   另對報價紀錄的每個實際報價點（數量 × 單價）各算期望利潤，取最大。
"""

import statistics
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from scipy.stats import norm
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import schemas
from app.deps import get_company_id, get_db
from app.models import (
    Artist,
    Event,
    InventoryMovement,
    ItemType,
    MovementType,
    Product,
    ProductVariant,
    Quote,
    Vendor,
)

router = APIRouter(prefix="/forecast", tags=["預測"])

SALE_TYPES = (MovementType.SALE.value, MovementType.SALE_RETURN.value)

SOLD_OUT_UPLIFT = 1.2   # 完售觀測的需求上修倍率
BLEND_K = 2             # 分層混合時，品項層先驗的等效樣本數
SIGMA_FLOOR = 0.25      # 波動下限 = μ 的 25%（小樣本防止過度自信）


def _observations(
    db: Session, cid: int, artist_id: int | None, item_type_id: int | None
) -> list[dict]:
    """每筆 = 某活動 × 某藝人 ×（指定品項）的產量與銷量。"""
    prod_stmt = (
        select(
            Product.event_id,
            Product.artist_id,
            Event.name,
            Event.start_date,
            func.sum(ProductVariant.production_qty).label("production"),
        )
        .join(ProductVariant, ProductVariant.product_id == Product.id)
        .join(Event, Product.event_id == Event.id)
        .where(Product.company_id == cid, Product.is_bundle.is_(False))
        .group_by(Product.event_id, Product.artist_id, Event.name, Event.start_date)
    )
    sold_stmt = (
        select(
            Product.event_id,
            Product.artist_id,
            func.sum(
                case(
                    (
                        InventoryMovement.movement_type.in_(SALE_TYPES),
                        -InventoryMovement.quantity_delta,
                    ),
                    else_=0,
                )
            ).label("sold"),
        )
        .join(ProductVariant, ProductVariant.product_id == Product.id)
        .join(InventoryMovement, InventoryMovement.variant_id == ProductVariant.id)
        .where(Product.company_id == cid, Product.is_bundle.is_(False))
        .group_by(Product.event_id, Product.artist_id)
    )
    if artist_id is not None:
        prod_stmt = prod_stmt.where(Product.artist_id == artist_id)
        sold_stmt = sold_stmt.where(Product.artist_id == artist_id)
    if item_type_id is not None:
        prod_stmt = prod_stmt.where(Product.item_type_id == item_type_id)
        sold_stmt = sold_stmt.where(Product.item_type_id == item_type_id)

    sold_map = {
        (r.event_id, r.artist_id): int(r.sold) for r in db.execute(sold_stmt).all()
    }
    out = []
    for r in db.execute(prod_stmt).all():
        production = int(r.production)
        if production == 0:
            continue
        sold = sold_map.get((r.event_id, r.artist_id), 0)
        sold_out = sold >= production
        out.append(
            {
                "event_name": r.name,
                "event_date": r.start_date,
                "production": production,
                "sold": sold,
                "sold_out": sold_out,
                "demand_est": round(production * SOLD_OUT_UPLIFT) if sold_out else sold,
            }
        )
    out.sort(key=lambda x: x["event_date"], reverse=True)
    return out


def _mean_demand(obs: list[dict]) -> float:
    return statistics.mean(o["demand_est"] for o in obs) if obs else 0.0


def _estimate_demand(
    db: Session, cid: int, artist_id: int, item_type_id: int
) -> schemas.DemandEstimate:
    artist_obs = _observations(db, cid, artist_id, item_type_id)
    type_obs = _observations(db, cid, None, item_type_id)
    n_a, n_t = len(artist_obs), len(type_obs)

    # 藝人熱度係數：該藝人單場平均需求（全品項）÷ 全藝人平均
    artist_all = _observations(db, cid, artist_id, None)
    global_all = _observations(db, cid, None, None)
    factor = 1.0
    if artist_all and global_all:
        g = _mean_demand(global_all)
        factor = _mean_demand(artist_all) / g if g > 0 else 1.0

    ests_a = [o["demand_est"] for o in artist_obs]
    ests_t = [o["demand_est"] for o in type_obs]
    type_mu = _mean_demand(type_obs) * factor
    type_sigma = (
        statistics.stdev(ests_t) * factor if n_t >= 2 else type_mu * 0.5
    )

    if n_a >= 4:
        mu = statistics.mean(ests_a)
        sigma = statistics.stdev(ests_a)
        basis = f"以該藝人 × 該品項的 {n_a} 筆歷史為主"
    elif n_a >= 1:
        w = n_a / (n_a + BLEND_K)
        mu = w * statistics.mean(ests_a) + (1 - w) * type_mu
        sigma = max(
            statistics.stdev(ests_a) if n_a >= 2 else 0.0, type_sigma
        )
        basis = (
            f"該藝人 × 該品項僅 {n_a} 筆，混合品項平均"
            f"（全藝人 {n_t} 筆）× 熱度係數 {factor:.2f}"
        )
    elif n_t >= 1:
        mu = type_mu
        sigma = type_sigma
        basis = f"該藝人無此品項紀錄，用品項平均（{n_t} 筆）× 熱度係數 {factor:.2f}"
    else:
        raise HTTPException(409, "這個品項還沒有任何歷史銷售資料，無法估計需求")

    sigma = max(sigma, mu * SIGMA_FLOOR, 1.0)
    return schemas.DemandEstimate(
        mu=round(mu, 1),
        sigma=round(sigma, 1),
        n_artist=n_a,
        n_type=n_t,
        basis=basis,
        observations=[schemas.DemandObservation(**o) for o in artist_obs],
    )


def _expected_profit(
    q: float, mu: float, sigma: float, price: float, cost: float, salvage: float
) -> tuple[float, float]:
    """回傳 (期望利潤, 期望售出)。D ~ Normal(mu, sigma)。"""
    t = (q - mu) / sigma
    expected_overage = sigma * (t * norm.cdf(t) + norm.pdf(t))  # E[(Q−D)⁺]
    expected_sold = q - expected_overage
    profit = (price - cost) * q - (price - salvage) * expected_overage
    return profit, expected_sold


@router.get("", response_model=schemas.ForecastResult)
def forecast(
    artist_id: int,
    item_type_id: int,
    price: float,
    cost: float | None = None,
    salvage: float = 0,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    if not db.scalar(
        select(Artist.id).where(Artist.id == artist_id, Artist.company_id == cid)
    ):
        raise HTTPException(422, "找不到指定的藝人")
    if not db.scalar(
        select(ItemType.id).where(
            ItemType.id == item_type_id, ItemType.company_id == cid
        )
    ):
        raise HTTPException(422, "找不到指定的品項")
    if price <= 0:
        raise HTTPException(422, "售價必須大於 0")
    # 極端輸入攔截（交接文件 1.2 的兩條當機路徑）：
    # salvage ≥ price → 關鍵比率除以零或變負；cost = 0 → CR=1 → Φ⁻¹(1)=∞
    if salvage >= price:
        raise HTTPException(422, "殘值必須低於售價")
    if cost is not None and cost <= 0:
        raise HTTPException(422, "單位成本必須大於 0（成本未知就留空，仍可看報價點比較）")

    demand = _estimate_demand(db, cid, artist_id, item_type_id)

    # ── 報童模型（要有成本才能算）──
    critical_ratio = recommended_qty = expected_profit = None
    warning = None
    if cost is not None:
        if cost >= price:
            warning = "成本不低於售價，賣一個賠一個——不建議生產，或先調整售價"
        else:
            # 上限保險絲：任何未來路徑都不可把 CR=1 餵給 norm.ppf（會回無限大）
            critical_ratio = min((price - cost) / (price - salvage), 0.999)
            z = float(norm.ppf(critical_ratio))
            recommended_qty = max(0, round(demand.mu + demand.sigma * z))
            expected_profit = round(
                _expected_profit(
                    recommended_qty, demand.mu, demand.sigma, price, cost, salvage
                )[0]
            )

    # ── 報價點比較：在每個實際報價（數量 × 單價）算期望利潤 ──
    quote_rows = db.execute(
        select(Quote.quantity, Quote.unit_price_twd, Vendor.name)
        .outerjoin(Vendor, Quote.vendor_id == Vendor.id)
        .where(Quote.company_id == cid, Quote.item_type_id == item_type_id)
        .order_by(Quote.quantity)
    ).all()
    quote_evals = []
    for q, unit_price, vendor_name in quote_rows:
        unit = float(unit_price)
        if unit >= price:
            continue  # 這個報價點連毛利都是負的，不列
        profit, sold = _expected_profit(
            q, demand.mu, demand.sigma, price, unit, salvage
        )
        quote_evals.append(
            schemas.QuoteEval(
                quantity=q,
                unit_price_twd=unit,
                vendor_name=vendor_name,
                expected_sold=round(sold, 1),
                expected_profit=round(profit),
                is_best=False,
            )
        )
    if quote_evals:
        best = max(quote_evals, key=lambda x: x.expected_profit)
        best.is_best = True

    # ── 建議售價：歷史價格帶 + 成本加成 ──
    prices = [
        float(p)
        for p in db.scalars(
            select(Product.price_twd).where(
                Product.company_id == cid,
                Product.item_type_id == item_type_id,
                Product.price_twd > 0,
                Product.is_bundle.is_(False),  # 套組價格不屬於單品價格帶
            )
        ).all()
    ]
    price_suggestion = None
    if prices or cost is not None:
        hist_low = min(prices) if prices else None
        hist_median = statistics.median(prices) if prices else None
        hist_high = max(prices) if prices else None
        if cost is not None and hist_median is not None:
            # 成本加成（成本佔售價約 35%）與歷史中位數取高者，湊整到 10
            suggested = max(cost / 0.35, hist_median)
            basis = "取「成本 ÷ 35%」與歷史中位數較高者"
        elif hist_median is not None:
            suggested = hist_median
            basis = "無成本資訊，採歷史成交中位數"
        else:
            suggested = cost / 0.35
            basis = "無歷史價格，採成本 ÷ 35%（業界常見成本佔比）"
        price_suggestion = schemas.PriceSuggestion(
            hist_low=hist_low,
            hist_median=hist_median,
            hist_high=hist_high,
            suggested=round(suggested / 10) * 10,
            basis=basis,
        )

    return schemas.ForecastResult(
        demand=demand,
        critical_ratio=round(critical_ratio, 3) if critical_ratio is not None else None,
        recommended_qty=recommended_qty,
        expected_profit=expected_profit,
        warning=warning,
        price=price_suggestion,
        quote_evals=quote_evals,
    )
