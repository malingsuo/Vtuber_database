"""資料表定義 v2 — 14 張業務表 + companies。

值域用 Python 常數而非資料庫原生 enum，讓 migration 在 SQLite 與 PostgreSQL
之間可攜；新增值域項目時不需要改資料庫結構。
"""

import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ArtistStatus(str, enum.Enum):
    ACTIVE = "active"        # 活動中
    GRADUATED = "graduated"  # 畢業


class EventType(str, enum.Enum):
    ONSITE = "onsite"  # 場販
    ONLINE = "online"  # 通販
    MIXED = "mixed"    # 混合


class PreorderStatus(str, enum.Enum):
    RESERVED = "reserved"    # 圈存中
    SHIPPED = "shipped"      # 已出貨
    CANCELLED = "cancelled"  # 已取消


class MovementType(str, enum.Enum):
    INBOUND = "inbound"          # 入庫（+）
    SALE = "sale"                # 銷售（−）
    SALE_RETURN = "sale_return"  # 銷售退回（+）
    PR_GIFT = "pr_gift"          # 轉公關品（−）
    SCRAP = "scrap"              # 報廢（−）
    ADJUSTMENT = "adjustment"    # 盤點調整（±）


class SalesChannel(str, enum.Enum):
    PREORDER = "preorder"  # 預購
    ONSITE = "onsite"      # 現場
    ONLINE = "online"      # 通販


class RecordSource(str, enum.Enum):
    MANUAL = "manual"  # 手動輸入
    EXCEL = "excel"    # Excel 匯入
    API = "api"        # 外部系統（發票/POS）


class UserRole(str, enum.Enum):
    ADMIN = "admin"    # 管理者
    EDITOR = "editor"  # 輸入者
    VIEWER = "viewer"  # 唯讀


class ExpenseCategory(str, enum.Enum):
    BOOTH = "booth"        # 攤位費
    SHIPPING = "shipping"  # 運費
    LABOR = "labor"        # 人力
    OTHER = "other"        # 其他


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class CompanyMixin:
    """多公司資料隔離：本機版永遠是同一個 company_id，介面上不顯示。"""

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True, nullable=False
    )


class Artist(CompanyMixin, TimestampMixin, Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default=ArtistStatus.ACTIVE.value)
    notes: Mapped[str | None] = mapped_column(Text)

    metrics: Mapped[list["ArtistMetric"]] = relationship(back_populates="artist")


class ArtistMetric(CompanyMixin, TimestampMixin, Base):
    """藝人熱度時間序列：訂閱數/追隨者數等，活動前後各記一筆。"""

    __tablename__ = "artist_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    artist_id: Mapped[int] = mapped_column(ForeignKey("artists.id"), index=True)
    record_date: Mapped[date] = mapped_column(Date)
    platform: Mapped[str] = mapped_column(String(30))  # YouTube / Twitch / X …
    metric_type: Mapped[str] = mapped_column(String(30), default="subscribers")
    value: Mapped[int] = mapped_column(Integer)

    artist: Mapped["Artist"] = relationship(back_populates="metrics")


class Event(CompanyMixin, TimestampMixin, Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date, index=True)  # 年份由此推得
    end_date: Mapped[date] = mapped_column(Date)
    event_type: Mapped[str] = mapped_column(String(20), default=EventType.ONSITE.value)
    preorder_start: Mapped[date | None] = mapped_column(Date)
    preorder_end: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    products: Mapped[list["Product"]] = relationship(back_populates="event")


class ItemType(CompanyMixin, TimestampMixin, Base):
    __tablename__ = "item_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))  # 壓克力立牌、吧唧、T-shirt…
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("company_id", "name"),)


class Vendor(CompanyMixin, TimestampMixin, Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    contact_info: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Product(CompanyMixin, TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    artist_id: Mapped[int] = mapped_column(ForeignKey("artists.id"), index=True)
    # 套組不屬於任何品項類別，故可空；單品必填（由 API 層驗證）
    item_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("item_types.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    price_twd: Mapped[float] = mapped_column(Numeric(12, 2))  # 贈品填 0
    is_bundle: Mapped[bool] = mapped_column(Boolean, default=False)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"))
    contact_person: Mapped[str | None] = mapped_column(String(100))  # 純營運備忘
    restock_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id")
    )  # 再販時指向前一次生產的商品
    notes: Mapped[str | None] = mapped_column(Text)

    event: Mapped["Event"] = relationship(back_populates="products")
    artist: Mapped["Artist"] = relationship()
    item_type: Mapped["ItemType"] = relationship()
    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product")
    bundle_items: Mapped[list["BundleItem"]] = relationship(
        back_populates="bundle_product", foreign_keys="BundleItem.bundle_product_id"
    )


class ProductVariant(CompanyMixin, TimestampMixin, Base):
    """單層規格（S/M/L、色差…）。庫存與銷量都記在這一層。"""

    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    variant_name: Mapped[str] = mapped_column(String(50), default="單一規格")
    production_qty: Mapped[int] = mapped_column(Integer, default=0)
    cost_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)  # 原幣金額
    cost_currency: Mapped[str] = mapped_column(String(3), default="TWD")
    exchange_rate: Mapped[float] = mapped_column(Numeric(10, 4), default=1)  # 實付匯率
    cost_twd: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)

    product: Mapped["Product"] = relationship(back_populates="variants")


class BundleItem(CompanyMixin, TimestampMixin, Base):
    """套組內容物：賣一套時系統對每個內容物各產生一筆庫存異動。"""

    __tablename__ = "bundle_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), index=True
    )
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    bundle_product: Mapped["Product"] = relationship(
        back_populates="bundle_items", foreign_keys=[bundle_product_id]
    )
    variant: Mapped["ProductVariant"] = relationship()


class Preorder(CompanyMixin, TimestampMixin, Base):
    """預購圈存：成立時不動實體庫存；出貨才產生銷售異動；取消則釋放圈存。"""

    __tablename__ = "preorders"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    created_date: Mapped[date] = mapped_column(Date)  # 預購累積曲線的原始資料
    status: Mapped[str] = mapped_column(
        String(20), default=PreorderStatus.RESERVED.value, index=True
    )
    status_changed_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(20), default=RecordSource.MANUAL.value)
    notes: Mapped[str | None] = mapped_column(Text)

    variant: Mapped["ProductVariant"] = relationship()


class InventoryMovement(CompanyMixin, Base):
    """庫存流水帳（系統核心）。目前庫存永遠是 quantity_delta 加總算出來的。"""

    __tablename__ = "inventory_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"), index=True)
    movement_type: Mapped[str] = mapped_column(String(20), index=True)
    quantity_delta: Mapped[int] = mapped_column(Integer)  # 帶正負號：入庫 +、售出 −
    movement_date: Mapped[date] = mapped_column(Date, index=True)
    # 銷售型專用
    channel: Mapped[str | None] = mapped_column(String(20))  # 預購/現場/通販
    sale_price_twd: Mapped[float | None] = mapped_column(Numeric(12, 2))  # 實際成交價
    sold_out_today: Mapped[bool | None] = mapped_column(Boolean)  # 當天是否完售
    # 公關型專用
    recipient: Mapped[str | None] = mapped_column(String(200))  # 對象
    purpose: Mapped[str | None] = mapped_column(String(200))  # 用途
    # 通用
    source: Mapped[str] = mapped_column(String(20), default=RecordSource.MANUAL.value)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    variant: Mapped["ProductVariant"] = relationship()


class Quote(CompanyMixin, TimestampMixin, Base):
    """報價點：每次詢價存一筆，累積後供報童模型在實際報價點上比較期望利潤。"""

    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_type_id: Mapped[int] = mapped_column(ForeignKey("item_types.id"), index=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"))
    quantity: Mapped[int] = mapped_column(Integer)  # 詢價數量
    unit_price: Mapped[float] = mapped_column(Numeric(12, 4))  # 原幣單價
    currency: Mapped[str] = mapped_column(String(3), default="TWD")
    exchange_rate: Mapped[float] = mapped_column(Numeric(10, 4), default=1)
    unit_price_twd: Mapped[float] = mapped_column(Numeric(12, 4))
    quote_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class Expense(CompanyMixin, TimestampMixin, Base):
    """檔期開支：算淨利用。公關品成本不在此重複建帳（報表時從流水帳計入）。"""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    category: Mapped[str] = mapped_column(String(20))
    amount_twd: Mapped[float] = mapped_column(Numeric(12, 2))
    artist_id: Mapped[int | None] = mapped_column(ForeignKey("artists.id"))  # 可歸屬藝人
    notes: Mapped[str | None] = mapped_column(Text)


class User(CompanyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.EDITOR.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("company_id", "username"),)


class AuditLog(CompanyMixin, Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))  # create / update / delete / login…
    table_name: Mapped[str] = mapped_column(String(50))
    record_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
