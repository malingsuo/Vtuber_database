"""模擬資料產生器：灌入合理分布的假資料供開發與展示。

用法： poetry run python -m app.seed
固定亂數種子，每次產生的資料相同；資料庫已有資料時拒絕執行以免重複灌入。
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import (
    Artist,
    ArtistMetric,
    ArtistStatus,
    BundleItem,
    Company,
    EventType,
    Event,
    Expense,
    ExpenseCategory,
    InventoryMovement,
    ItemType,
    MovementType,
    Preorder,
    PreorderStatus,
    Product,
    ProductVariant,
    Quote,
    RecordSource,
    SalesChannel,
    User,
    UserRole,
    Vendor,
)

rng = random.Random(42)

# 品項 → (價格帶下限, 上限, 製作量下限, 上限)；海報是贈品，售價 0
ITEM_SPECS = {
    "飯友": (200, 300, 100, 300),
    "壓克力立牌": (300, 500, 100, 400),
    "徽章": (80, 120, 200, 600),
    "海報": (0, 0, 200, 500),
    "T-shirt": (700, 900, 30, 100),
    "外套": (2000, 2500, 20, 60),
    "掛軸": (800, 1200, 50, 150),
    "明信片": (50, 80, 300, 800),
    "娃娃": (900, 1200, 80, 200),
    "御守": (300, 400, 100, 300),
}

ARTIST_NAMES = [
    "星野銀河", "月見兔兔", "白鳥雪奈", "貓宮小鈴",
    "焰羽炎華", "深海鯨音", "楓語千秋", "霧島朔夜",
]

VENDORS = [
    ("廣州百製文創", "CNY", Decimal("4.45")),
    ("深圳快印週邊", "CNY", Decimal("4.50")),
    ("台北原創印務", "TWD", Decimal("1")),
]

EVENTS = [
    # (名稱, 開始日, 天數, 類型, 有無預購)
    ("2024 開臺週年慶通販", date(2024, 3, 1), 14, EventType.ONLINE, True),
    ("FF42 場販", date(2024, 4, 27), 2, EventType.ONSITE, False),
    ("2024 夏日祭場販", date(2024, 7, 20), 2, EventType.ONSITE, False),
    ("2024 冬季新品混合檔", date(2024, 12, 14), 10, EventType.MIXED, True),
    ("2025 春季通販", date(2025, 3, 8), 14, EventType.ONLINE, True),
    ("FF44 場販", date(2025, 5, 3), 2, EventType.ONSITE, False),
    ("2025 三週年混合檔", date(2025, 9, 6), 10, EventType.MIXED, True),
    ("2025 冬Comi場販", date(2025, 12, 20), 2, EventType.ONSITE, False),
    ("2026 春季通販", date(2026, 3, 14), 14, EventType.ONLINE, True),
    ("2026 夏日祭場販", date(2026, 7, 11), 2, EventType.ONSITE, False),
]


def money(low: int, high: int, step: int = 10) -> Decimal:
    """在價格帶內取一個湊整的價格。"""
    if high <= low:
        return Decimal(low)
    return Decimal(rng.randrange(low, high + 1, step) if high - low >= step else low)


def main() -> None:
    session = SessionLocal()

    if session.scalar(select(func.count()).select_from(Company)):
        raise SystemExit("資料庫已有資料，拒絕重複灌入。要重灌請先刪除 dev.db 再跑 migration。")

    # 平台總部：總管理員所屬，只管公司開通，不放業務資料
    platform = Company(name="平台總部")
    session.add(platform)
    session.flush()
    session.add(
        User(
            company_id=platform.id,
            username="superadmin",
            password_hash=hash_password("super123"),
            display_name="總管理員",
            role=UserRole.SUPERADMIN.value,
        )
    )

    company = Company(name="示範娛樂")
    session.add(company)
    session.flush()
    cid = company.id

    admin = User(
        company_id=cid,
        username="admin",
        password_hash=hash_password("admin123"),
        display_name="管理員",
        role=UserRole.ADMIN.value,
    )
    session.add(admin)
    session.add(User(company_id=cid, username="editor",
                     password_hash=hash_password("editor123"),
                     display_name="輸入員", role=UserRole.EDITOR.value))
    session.add(User(company_id=cid, username="viewer",
                     password_hash=hash_password("viewer123"),
                     display_name="唯讀帳號", role=UserRole.VIEWER.value))

    artists = [
        Artist(
            company_id=cid,
            name=name,
            status=ArtistStatus.GRADUATED.value if name == "霧島朔夜" else ArtistStatus.ACTIVE.value,
        )
        for name in ARTIST_NAMES
    ]
    session.add_all(artists)

    item_types = {
        name: ItemType(company_id=cid, name=name) for name in ITEM_SPECS
    }
    session.add_all(item_types.values())

    vendors = [
        Vendor(company_id=cid, name=name, notes=f"報價幣別 {cur}")
        for name, cur, _ in VENDORS
    ]
    session.add_all(vendors)
    session.flush()

    # 藝人熱度：每月一筆 YouTube 訂閱數，各自成長軌跡
    for artist in artists:
        base = rng.randrange(30_000, 300_000, 5_000)
        growth = rng.uniform(0.01, 0.06)  # 月成長率
        d = date(2024, 1, 1)
        value = base
        while d <= date(2026, 7, 1):
            session.add(
                ArtistMetric(
                    company_id=cid,
                    artist_id=artist.id,
                    record_date=d,
                    platform="YouTube",
                    metric_type="subscribers",
                    value=int(value),
                )
            )
            value *= 1 + rng.gauss(growth, growth / 3)
            d = (d.replace(day=1) + timedelta(days=32)).replace(day=1)

    # 報價紀錄：每品項 2~3 家廠商、數量越大單價越低
    for it_name, it in item_types.items():
        base_cost = Decimal(ITEM_SPECS[it_name][1] or 60) * Decimal("0.35")
        for vendor, (v_name, cur, rate) in zip(vendors, VENDORS):
            if rng.random() < 0.3:
                continue
            for qty in (100, 300, 500):
                unit_twd = base_cost * Decimal(str(1 - 0.08 * (qty // 200)))
                unit_orig = (unit_twd / rate).quantize(Decimal("0.01"))
                session.add(
                    Quote(
                        company_id=cid,
                        item_type_id=it.id,
                        vendor_id=vendor.id,
                        quantity=qty,
                        unit_price=unit_orig,
                        currency=cur,
                        exchange_rate=rate,
                        unit_price_twd=(unit_orig * rate).quantize(Decimal("0.01")),
                        quote_date=date(2024, rng.randint(1, 12), rng.randint(1, 28)),
                    )
                )

    total_products = 0
    for ev_name, start, days, ev_type, has_preorder in EVENTS:
        end = start + timedelta(days=days - 1)
        event = Event(
            company_id=cid,
            name=ev_name,
            start_date=start,
            end_date=end,
            event_type=ev_type.value,
            preorder_start=start - timedelta(days=21) if has_preorder else None,
            preorder_end=start - timedelta(days=7) if has_preorder else None,
        )
        session.add(event)
        session.flush()

        # 檔期開支
        if ev_type in (EventType.ONSITE, EventType.MIXED):
            session.add(Expense(company_id=cid, event_id=event.id,
                                category=ExpenseCategory.BOOTH.value,
                                amount_twd=Decimal(rng.randrange(15_000, 40_000, 1_000))))
            session.add(Expense(company_id=cid, event_id=event.id,
                                category=ExpenseCategory.LABOR.value,
                                amount_twd=Decimal(rng.randrange(5_000, 20_000, 1_000))))
        session.add(Expense(company_id=cid, event_id=event.id,
                            category=ExpenseCategory.SHIPPING.value,
                            amount_twd=Decimal(rng.randrange(3_000, 10_000, 500))))

        # 每場活動 3~6 位藝人參加，畢業藝人只出現在 2024 場次
        pool = [a for a in artists
                if a.status == ArtistStatus.ACTIVE.value or start.year == 2024]
        joined = rng.sample(pool, rng.randint(3, min(6, len(pool))))

        for artist in joined:
            chosen = rng.sample(list(ITEM_SPECS), rng.randint(2, 4))
            artist_variants: list[ProductVariant] = []
            for it_name in chosen:
                lo, hi, qlo, qhi = ITEM_SPECS[it_name]
                vendor_idx = rng.randrange(len(vendors))
                v_name, cur, rate = VENDORS[vendor_idx]
                price = money(lo, hi)
                product = Product(
                    company_id=cid,
                    event_id=event.id,
                    artist_id=artist.id,
                    item_type_id=item_types[it_name].id,
                    name=f"{artist.name} {it_name}",
                    price_twd=price,
                    vendor_id=vendors[vendor_idx].id,
                )
                session.add(product)
                session.flush()
                total_products += 1

                sizes = ["S", "M", "L"] if it_name in ("T-shirt", "外套") else ["單一規格"]
                for size in sizes:
                    qty = rng.randint(qlo, qhi)
                    # 成本約為售價 30~40%；贈品類用固定小成本
                    cost_twd = (price * Decimal(str(rng.uniform(0.3, 0.4)))
                                if price else Decimal(rng.randrange(15, 31)))
                    cost_orig = (cost_twd / rate).quantize(Decimal("0.01"))
                    variant = ProductVariant(
                        company_id=cid,
                        product_id=product.id,
                        variant_name=size,
                        production_qty=qty,
                        cost_amount=cost_orig,
                        cost_currency=cur,
                        exchange_rate=rate,
                        cost_twd=(cost_orig * rate).quantize(Decimal("0.01")),
                    )
                    session.add(variant)
                    artist_variants.append(variant)
            session.flush()

            # 三成機率為這位藝人出套組（內容物 = 該藝人此場全部單品各 1）
            if len(artist_variants) >= 3 and rng.random() < 0.3:
                singles_total = sum(
                    Decimal(v.product.price_twd) for v in artist_variants
                )
                bundle = Product(
                    company_id=cid,
                    event_id=event.id,
                    artist_id=artist.id,
                    item_type_id=item_types[chosen[0]].id,
                    name=f"{artist.name} 全套組",
                    price_twd=(singles_total * Decimal("0.85")).quantize(Decimal("1")),
                    is_bundle=True,
                )
                session.add(bundle)
                session.flush()
                for v in artist_variants:
                    session.add(BundleItem(company_id=cid,
                                           bundle_product_id=bundle.id,
                                           variant_id=v.id, quantity=1))
                total_products += 1

            # ── 庫存與銷售 ──
            for variant in artist_variants:
                price = Decimal(variant.product.price_twd)
                # 入庫：活動前 7 天
                session.add(InventoryMovement(
                    company_id=cid, variant_id=variant.id,
                    movement_type=MovementType.INBOUND.value,
                    quantity_delta=variant.production_qty,
                    movement_date=start - timedelta(days=7),
                    source=RecordSource.MANUAL.value, created_by=admin.id,
                ))

                sell_through = rng.uniform(0.5, 1.0)
                target_sold = int(variant.production_qty * sell_through)
                sold_so_far = 0

                # 預購（有預購窗的活動）：佔需求 2~4 成，一成取消
                if has_preorder and price > 0:
                    preorder_target = int(target_sold * rng.uniform(0.2, 0.4))
                    window = (event.preorder_end - event.preorder_start).days
                    while preorder_target > 0:
                        q = min(rng.randint(1, 3), preorder_target)
                        cancelled = rng.random() < 0.1
                        session.add(Preorder(
                            company_id=cid, variant_id=variant.id, quantity=q,
                            created_date=event.preorder_start
                            + timedelta(days=rng.randint(0, window)),
                            status=(PreorderStatus.CANCELLED if cancelled
                                    else PreorderStatus.SHIPPED).value,
                            status_changed_date=start,
                        ))
                        if not cancelled:
                            session.add(InventoryMovement(
                                company_id=cid, variant_id=variant.id,
                                movement_type=MovementType.SALE.value,
                                quantity_delta=-q, movement_date=start,
                                channel=SalesChannel.PREORDER.value,
                                sale_price_twd=price,
                                source=RecordSource.MANUAL.value, created_by=admin.id,
                            ))
                            sold_so_far += q
                        preorder_target -= q

                # 場販／通販：剩餘需求攤到活動天數（首日權重最高）
                remaining = target_sold - sold_so_far
                weights = [2 ** -(i * 0.5) for i in range(days)]
                wsum = sum(weights)
                channel = (SalesChannel.ONSITE if ev_type == EventType.ONSITE
                           else SalesChannel.ONLINE)
                for i in range(days):
                    day_qty = round(remaining * weights[i] / wsum)
                    if day_qty <= 0:
                        continue
                    day_qty = min(day_qty, target_sold - sold_so_far)
                    if day_qty <= 0:
                        break
                    sold_so_far += day_qty
                    session.add(InventoryMovement(
                        company_id=cid, variant_id=variant.id,
                        movement_type=MovementType.SALE.value,
                        quantity_delta=-day_qty,
                        movement_date=start + timedelta(days=i),
                        channel=channel.value,
                        sale_price_twd=price if price else None,
                        sold_out_today=(sold_so_far >= variant.production_qty),
                        source=RecordSource.MANUAL.value, created_by=admin.id,
                    ))

                # 公關品：兩成機率送出 2~5 個（不超過剩餘庫存）
                left = variant.production_qty - sold_so_far
                if left > 5 and rng.random() < 0.2:
                    q = rng.randint(2, 5)
                    session.add(InventoryMovement(
                        company_id=cid, variant_id=variant.id,
                        movement_type=MovementType.PR_GIFT.value,
                        quantity_delta=-q, movement_date=end + timedelta(days=3),
                        recipient=rng.choice(["合作繪師", "通路夥伴", "媒體", "友台主播"]),
                        purpose="公關贈送",
                        source=RecordSource.MANUAL.value, created_by=admin.id,
                    ))

    session.commit()

    # ── 摘要 ──
    print("模擬資料灌入完成：")
    for model in (Company, User, Artist, ArtistMetric, Event, ItemType, Vendor,
                  Product, ProductVariant, BundleItem, Preorder,
                  InventoryMovement, Quote, Expense):
        n = session.scalar(select(func.count()).select_from(model))
        print(f"  {model.__tablename__:22s} {n:>6} 筆")

    stock = session.execute(
        select(
            ProductVariant.id,
            func.sum(InventoryMovement.quantity_delta),
        ).join(InventoryMovement).group_by(ProductVariant.id)
    ).all()
    negatives = [row for row in stock if row[1] < 0]
    print(f"\n庫存檢核：{len(stock)} 個規格，負庫存 {len(negatives)} 個（應為 0）")
    session.close()


if __name__ == "__main__":
    main()
