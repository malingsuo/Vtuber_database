"""API 輸入/輸出格式（Pydantic schemas）。

命名慣例：XxxCreate = 建立時的輸入、XxxUpdate = 更新輸入（欄位皆選填）、
XxxOut = 回傳格式。
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── 藝人 ──

class ArtistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    status: Literal["active", "graduated"] = "active"
    notes: str | None = None


class ArtistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: Literal["active", "graduated"] | None = None
    notes: str | None = None


class ArtistOut(ORMBase):
    id: int
    name: str
    status: str
    notes: str | None


# ── 活動 ──

class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start_date: date
    end_date: date
    event_type: Literal["onsite", "online", "mixed"] = "onsite"
    preorder_start: date | None = None
    preorder_end: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def check_dates(self) -> "EventCreate":
        if self.end_date < self.start_date:
            raise ValueError("結束日不能早於開始日")
        if (self.preorder_start is None) != (self.preorder_end is None):
            raise ValueError("預購起訖日要同時填或同時不填")
        if self.preorder_start and self.preorder_end < self.preorder_start:
            raise ValueError("預購截止日不能早於預購開始日")
        return self


class EventUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    event_type: Literal["onsite", "online", "mixed"] | None = None
    preorder_start: date | None = None
    preorder_end: date | None = None
    notes: str | None = None


class EventOut(ORMBase):
    id: int
    name: str
    start_date: date
    end_date: date
    event_type: str
    preorder_start: date | None
    preorder_end: date | None
    notes: str | None


# ── 品項類別 / 廠商 ──

class ItemTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    notes: str | None = None


class ItemTypeOut(ORMBase):
    id: int
    name: str
    notes: str | None


class VendorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    contact_info: str | None = None
    notes: str | None = None


class VendorOut(ORMBase):
    id: int
    name: str
    contact_info: str | None
    notes: str | None


# ── 商品與規格 ──

class VariantCreate(BaseModel):
    variant_name: str = Field(default="單一規格", max_length=50)
    production_qty: int = Field(default=0, ge=0)
    cost_amount: Decimal = Field(default=Decimal("0"), ge=0)  # 原幣金額
    cost_currency: str = Field(default="TWD", max_length=3)
    exchange_rate: Decimal = Field(default=Decimal("1"), gt=0)  # 實付匯率
    notes: str | None = None
    # cost_twd 由後端計算（原幣 × 匯率），不接受前端傳入


class VariantOut(ORMBase):
    id: int
    variant_name: str
    production_qty: int
    cost_amount: Decimal
    cost_currency: str
    exchange_rate: Decimal
    cost_twd: Decimal
    notes: str | None


class BundleItemIn(BaseModel):
    variant_id: int  # 內容物的規格 id
    quantity: int = Field(default=1, ge=1)


class BundleItemOut(ORMBase):
    id: int
    variant_id: int
    quantity: int


class ProductCreate(BaseModel):
    event_id: int
    artist_id: int
    item_type_id: int | None = None  # 套組不填；單品必填
    name: str = Field(min_length=1, max_length=200)
    price_twd: Decimal = Field(ge=0)  # 贈品填 0
    is_bundle: bool = False
    vendor_id: int | None = None
    contact_person: str | None = Field(default=None, max_length=100)
    restock_source_id: int | None = None  # 再販時指向前一次生產的商品
    notes: str | None = None
    variants: list[VariantCreate] = Field(default_factory=lambda: [VariantCreate()])
    bundle_items: list[BundleItemIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_bundle(self) -> "ProductCreate":
        if self.is_bundle:
            if not self.bundle_items:
                raise ValueError("套組必須指定內容物 bundle_items")
            self.item_type_id = None  # 套組一律不掛品項類別
        else:
            if self.bundle_items:
                raise ValueError("非套組不可帶 bundle_items")
            if self.item_type_id is None:
                raise ValueError("單品必須指定品項類別")
        if not self.variants:
            raise ValueError("至少要有一個規格")
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    price_twd: Decimal | None = Field(default=None, ge=0)
    vendor_id: int | None = None
    contact_person: str | None = None
    restock_source_id: int | None = None
    notes: str | None = None


class ProductOut(ORMBase):
    id: int
    event_id: int
    artist_id: int
    item_type_id: int | None
    name: str
    price_twd: Decimal
    is_bundle: bool
    vendor_id: int | None
    contact_person: str | None
    restock_source_id: int | None
    notes: str | None
    variants: list[VariantOut]
    bundle_items: list[BundleItemOut]


# ── 庫存異動 ──

class MovementCreate(BaseModel):
    variant_id: int
    movement_type: Literal[
        "inbound", "sale", "sale_return", "pr_gift", "scrap", "adjustment"
    ]
    quantity: int  # 正數；盤點調整可正（盤盈）可負（盤虧）
    movement_date: date
    channel: Literal["preorder", "onsite", "online"] | None = None  # 銷售型必填
    sale_price_twd: Decimal | None = None  # 不填用商品定價
    sold_out_today: bool | None = None
    recipient: str | None = None  # 轉公關必填
    purpose: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def check(self) -> "MovementCreate":
        if self.movement_type == "adjustment":
            if self.quantity == 0:
                raise ValueError("盤點調整數量不可為 0")
        elif self.quantity <= 0:
            raise ValueError("數量必須為正數")
        if self.movement_type == "sale" and self.channel is None:
            raise ValueError("銷售必須指定通路")
        if self.movement_type == "pr_gift" and not self.recipient:
            raise ValueError("轉公關品請填寫對象")
        return self


class MovementOut(ORMBase):
    id: int
    variant_id: int
    movement_type: str
    quantity_delta: int
    movement_date: date
    channel: str | None
    sale_price_twd: Decimal | None
    sold_out_today: bool | None
    recipient: str | None
    purpose: str | None
    source: str
    notes: str | None


class StockOut(BaseModel):
    variant_id: int
    physical: int   # 實體庫存（流水帳加總）
    reserved: int   # 圈存量（未出貨的預購）
    available: int  # 可售 = 實體 − 圈存


class DailySaleItem(BaseModel):
    variant_id: int
    quantity: int = Field(gt=0)
    sale_price_twd: Decimal | None = None
    sold_out_today: bool = False


class DailySalesCreate(BaseModel):
    """逐日銷售輸入：收攤後一次填整場的當日銷量。"""

    movement_date: date
    channel: Literal["onsite", "online"]
    items: list[DailySaleItem] = Field(min_length=1)


# ── 預購 ──

class PreorderCreate(BaseModel):
    variant_id: int
    quantity: int = Field(gt=0)
    created_date: date
    notes: str | None = None


class PreorderOut(ORMBase):
    id: int
    variant_id: int
    quantity: int
    created_date: date
    status: str
    status_changed_date: date | None
    notes: str | None


class PreorderShip(BaseModel):
    ship_date: date
    sale_price_twd: Decimal | None = None


class PreorderCancel(BaseModel):
    cancel_date: date


class PreorderShipAll(BaseModel):
    variant_id: int
    ship_date: date
    sale_price_twd: Decimal | None = None


# ── 查詢流程：活動總覽（依藝人分組 + 銷售統計）──

class VariantStats(BaseModel):
    id: int
    variant_name: str
    production_qty: int
    cost_twd: Decimal
    sold_qty: int       # 淨售出（銷售 − 銷售退回）
    stock_qty: int      # 目前實體庫存（流水帳加總）
    reserved_qty: int   # 圈存量（未出貨的預購）
    available_qty: int  # 可售 = 實體 − 圈存
    revenue_twd: Decimal


class BundleContent(BaseModel):
    name: str  # 「商品名（規格）」
    quantity: int


class ProductWithStats(BaseModel):
    id: int
    item_type_id: int | None
    name: str
    price_twd: Decimal
    is_bundle: bool
    variants: list[VariantStats]
    bundle_contents: list[BundleContent] = []  # 套組才有值，給前端懸浮顯示


class ArtistBlock(BaseModel):
    artist: ArtistOut
    products: list[ProductWithStats]


class EventOverview(BaseModel):
    event: EventOut
    artists: list[ArtistBlock]
