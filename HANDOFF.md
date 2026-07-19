# 交接文件：系統審查與擴充指引

> 對象：接手維護/擴充的開發者或 AI。
> 產出方式：逐條對照程式碼驗證，所有風險判斷附檔案位置；「已證實」代表在原始碼中確認存在，非推測。
>
> **修補狀態（2026-07-19）**：§1.1 併發競爭（悲觀鎖，含 6 執行緒實測無超賣）、§1.2 報童極端輸入（422 驗證＋CR≤0.999 保險絲）、§2.2 漏洞 A（username 全域唯一，migration `0153d9a7d3b0`）——**均已修補**。漏洞 B（vendor/restock 公司歸屬驗證）、漏洞 C（登入速率限制）、預購出貨異動與預購狀態脫鉤——**仍待處理**。

## 0. 系統快照

- 後端 `backend/`：FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL（開發可退 SQLite）。Poetry 管依賴。
- 前端 `frontend/`：Vue 3 + Element Plus + Vite，`/api` 由 dev proxy 或 nginx 同源代理。
- 部署：根目錄 `docker-compose.yml`（db/backend/frontend），啟動自動跑 migration，`python -m app.bootstrap` 建總管理員。
- 核心不變量：
  1. **庫存永遠是 `inventory_movements.quantity_delta` 的加總**，資料庫沒有「目前庫存」欄位。
  2. **每張業務表都有 `company_id`**，值一律來自登入者（`app/deps.py: get_company_id`）。
  3. **預測分兩層**：需求估計（`forecast.py: _estimate_demand`，可替換）＋ 報童決策（`_expected_profit` 與 CR 公式，不可動）。
- 關鍵檔案地圖：models `app/models.py`｜權限 `app/deps.py`、`app/auth.py`｜庫存 `app/routers/inventory.py`｜預購 `app/routers/preorders.py`｜預測 `app/routers/forecast.py`｜報表 `app/routers/reports.py`｜多公司 `app/routers/admin.py`｜匯入匯出 `app/routers/excel.py`。

---

## 1. 深度體檢（已知邊界與潛在風險）

### 1.1 併發競爭（Race Conditions）——【已證實，全系統無任何行鎖】

全 codebase 沒有任何 `with_for_update`（已 grep 確認）。所有庫存檢查都是「先 SELECT 加總、再 INSERT」的 check-then-act 模式，在 PostgreSQL 預設的 READ COMMITTED 下**會超賣**：

| 場景 | 位置 | 後果 |
|---|---|---|
| 兩個請求同時售出/報廢同規格 | `inventory.py: create_movement`（檢查後才寫入） | 兩者都通過檢查 → 實體庫存變負 |
| 同規格兩筆預購同時出貨 | `preorders.py: ship_preorder` | 同上 |
| 同一筆預購被同時按兩次出貨 | 兩請求都讀到 `reserved` 狀態 | **重複產生銷售異動**、重複扣庫存 |
| 逐日銷售與抽屜操作並發 | `inventory.py: daily_sales` | 同第一種 |

**風險評估**：單機單人＝幾乎不會發生；**雲端多人版＝必然發生**（場販收攤多人同時輸入就是典型情境）。嚴重度：高（帳務錯誤，事後難察覺）。

**修補建議**（一次性小改，約 20 行）：在每個「檢查＋寫入」路徑開頭鎖住規格列，讓同規格的寫入序列化：

```python
# inventory.py get_variant 加參數
def get_variant(db, cid, variant_id, for_update: bool = False):
    stmt = select(ProductVariant).where(...)
    if for_update:
        stmt = stmt.with_for_update()   # SQLite 會無視（開發無妨），Postgres 生效
    ...
```
`create_movement`、`daily_sales`、`ship_preorder`、`ship_all`、`delete_movement` 改用 `for_update=True`；`ship_preorder`/`cancel_preorder` 另外對 Preorder 列本身 `with_for_update()`（防同筆重複出貨）。不要用 SERIALIZABLE 隔離級別（重試邏輯成本更高）。

### 1.2 報童模型極端輸入——【兩個已證實的當機路徑】

位置：`forecast.py` 第 213 行 `critical_ratio = (price - cost) / (price - salvage)`。

| 輸入 | 現況 | 結果 |
|---|---|---|
| `cost >= price` | ✅ 已擋（回警告，不計算） | 安全 |
| **`cost = 0`** | ❌ 未擋（`0 >= price` 為假，照算） | CR = 1.0 → `norm.ppf(1.0)` = **inf** → `round(inf)` 直接 **OverflowError 500** |
| **`salvage >= price`** | ❌ 完全沒驗證 salvage | `salvage == price` → **ZeroDivisionError**；`salvage > price` → CR 為負 → `norm.ppf` 回 **NaN** 汙染輸出 |
| 歷史需求全為 0 | ✅ 安全（sigma 有 `max(σ, 0.25μ, 1.0)` 下限，無除零） | μ=0、建議訂 0 |
| 該品項毫無歷史 | ✅ 已擋（409 中文訊息） | 安全 |
| 報價點單價 ≥ 售價 | ✅ 已擋（跳過該點不列） | 安全 |
| 極端報價階距（如 qty=1 或 100 萬） | 數學上無害（期望利潤照算，大單自然算出巨額滯銷損失） | 安全但建議 UI 顯示期望售出佔訂量比例供人判斷 |

**修補建議**（在 forecast() 開頭加三行驗證）：

```python
if salvage >= price:
    raise HTTPException(422, "殘值必須低於售價")
if cost is not None and cost <= 0:
    raise HTTPException(422, "單位成本必須大於 0（未知成本請留空）")
```
另建議保險絲：`critical_ratio = min(critical_ratio, 0.999)`，讓任何未來路徑都不會把 inf 餵給 `norm.ppf`。

### 1.3 資料一致性（刪除防呆現況盤點）

| 操作 | 防護 | 狀態 |
|---|---|---|
| 刪品項：有商品或報價引用 | FK IntegrityError → 409 | ✅ |
| 刪商品：有異動/預購/被套組收錄 | 逐項顯式檢查 → 409 | ✅ |
| 刪藝人/廠商：有引用 | FK → 409 | ✅ |
| 刪報價 | 無任何表引用 quotes，可自由刪 | ✅（設計如此） |
| 刪異動明細：刪後庫存變負 | 顯式檢查 → 409；限管理者＋密碼 | ✅ |
| **刪「預購出貨」產生的銷售異動** | 只有 UI 警告文字，**預購仍停在 shipped** | ⚠️ 已知缺口：帳（異動）與約（預購）脫鉤。建議補「預購退回圈存」端點（把 shipped 改回 reserved 並同時刪出貨異動，同一交易內完成），取代直接刪異動 |
| Excel 併發匯入同檔兩次 | 重複檢查也是 check-then-act | ⚠️ 低風險（同一公司自己撞自己），修補同 1.1 或對 import 加公司級 advisory lock |

---

## 2. 核心架構防線確認

### 2.1 company_id 隔離機制（逐層說明）

1. **來源唯一**：`get_company_id` 依賴 `get_current_user`（JWT → DB 重讀 User），回 `user.company_id`。**cid 不可能來自請求參數**，前端無法指定。
2. **讀取面**：所有 GET 列表查詢都有 `.where(Model.company_id == cid)`；單筆查詢是 `id == x AND company_id == cid`，查不到回 404——別家資源的存在性都探測不到。
3. **寫入面**：建立時 `company_id=cid` 由伺服器塞入（schema 不收這個欄位）；跨表引用（活動/藝人/品項/套組內容物/規格）在寫入前逐一驗證屬於同公司。
4. **刪除面**：DELETE 一律先以 `id + company_id` 撈目標，撈不到 404，不可能刪到別家。
5. **權限閘**：業務路由統一掛 `authorize`（未登入 401、唯讀寫入 403）；每次請求都重查使用者與公司狀態，**停權/停用公司即時生效**（不是等 token 過期）。
6. **角色升級封死**：`UserCreate/UserUpdate` 的 role 是 `Literal["admin","editor","viewer"]`——小管理員**無法**建立或指派 superadmin；`/api/admin/*` 全部 `require_superadmin`；使用者管理查詢都綁 `admin.company_id`，小管理員碰不到總管理員（在別的公司）也碰不到他公司的帳號。

### 2.2 審查發現的真實漏洞（本次新發現，附證據）

**漏洞 A（中高）：登入查詢是全域的，但帳號唯一性是公司級的。**
`auth_router.py:15` `select(User).where(User.username == body.username)` 沒有公司條件，而 `users` 表的唯一約束是 `(company_id, username)`。後果：總管理員幫 B 公司也開一個叫 `admin` 的帳號後，登入永遠只比對到先建立的那個 → **B 公司的 admin 無法登入**（或密碼恰好相同時登入到錯的公司）。
**修補（擇一）**：(a) 把 username 改成全域唯一——migration 改約束＋`create_company`/`create_user` 檢查全域重複（推薦，UX 最簡單）；(b) 登入加「公司代號」欄位。

**漏洞 B（低）：商品的 `vendor_id`、`restock_source_id` 未驗證公司歸屬。**
`products.py: _check_fk` 只驗活動/藝人/品項（已確認），create/update 可把商品指向**別家公司**的廠商或商品 id。實害有限（讀取面都有隔離，別家資料不會顯示），但汙染了隔離不變量。
**修補**：`_check_fk` 補兩項檢查；`ProductUpdate` 路徑同樣要過檢查。

**漏洞 C（部署面）：登入無速率限制。** 雲端版可被暴力猜密碼。建議上 slowapi（每 IP 每分鐘 5 次）或至少在 nginx 加 `limit_req`。同場加映：bcrypt 只取前 72 bytes（超長密碼截斷，知悉即可）；audit middleware 在 async 路徑用同步 session（高流量時考慮改 background task）。

---

## 3. 未來功能擴充指引

### 3.1 套組營收攤分

**不需要動任何資料表**——攤分是「報表時的計算」，不是要存的事實（存了反而在改內容物定價時變成髒資料）。

- 動哪裡：只動 `reports.py`（以及未來想讓需求估計吃攤分結果時的 `forecast.py`）。
- 演算法：
  1. 撈活動內所有套組的 `bundle_items`（套組規格 id → [(內容物規格, 每套件數)]）。
  2. 權重 = 內容物單售定價 × 件數 ÷ Σ(全部內容物 定價×件數)；**Σ 為 0 時（全贈品內容）退化成平均分攤**。
  3. 套組的銷售異動營收 × 權重，加回內容物所屬商品 → 再彙總到該內容物的藝人/品項列；套組自身列歸零或標示「已攤分」。
  4. 注意：內容物可能跨藝人（資料模型允許），攤分要跟著**內容物**的 artist_id 走，不是套組的。
- API 形狀：`GET /reports/events/{id}?allocate_bundles=true`（預設 false，兩種口徑並存，方便對帳）。
- 驗收：攤分前後「活動總營收」必須一致到分——寫一個等式檢查當測試。

### 3.2 預購累積曲線的時間序列預測

資料早就在了：`preorders(created_date, quantity, status)` 就是逐日累積曲線的原始點，`events.preorder_start/preorder_end` 是窗；`cancelled` 列天然給出取消率。**不需要新資料表。**

- 動哪裡：新增 `app/forecast_ts.py`（估計邏輯）＋ `forecast.py` 加一個端點。**決策層（`_expected_profit`、CR 公式）一行都不要碰**——這是當初分兩層的原因：時間序列只是產出另一組 (μ, σ) 餵進同一個報童模型。
- 實作步驟：
  1. `GET /forecast/preorder-projection?variant_id=`（或 product 級加總）：把該規格的預購按日累積成序列（扣掉 cancelled，另回報取消率）。
  2. 外推：預購窗尚未結束時，用「歷史活動的標準化曲線形狀」外推——把過去每場的累積曲線正規化到 [0,1]×[0,1]，平均得到形狀函數 F(t)；目前進度 c(t) ⇒ 預測終值 = c(t)/F(t)。樣本不足時退化成線性外推，並在回傳的 `basis` 欄寫明方法（沿用現有的可解釋原則）。
  3. σ 取歷史各場「同時間點外推誤差」的離散度；再乘 (1 − 歷史取消率) 得淨需求。
  4. 回傳格式對齊 `schemas.DemandEstimate`，前端預測頁加一個「用預購曲線估需求」開關，其餘 UI 復用。
- 何時啟用：同一公司累積 ≥3 場有預購窗的活動再開，否則形狀函數沒樣本。

---

## 4. AI 接手開發公約（System Constraints）

```
【系統絕對約束——違反任一條即重寫，不接受例外】
1. 所有查詢與寫入必經 get_company_id 過濾，嚴禁跨公司存取或信任前端傳入的 company_id。
2. 業務路由必掛 authorize；管理操作只用 require_admin／require_superadmin，禁止自創權限判斷。
3. 庫存只能由 inventory_movements 加總取得，嚴禁新增庫存欄位或直接改數量。
4. 預測的需求估計層可替換，報童決策層公式與介面不可動。
5. 資料表變更只走 Alembic migration，禁止手改資料庫。
6. 刪除帳務紀錄必須沿用管理者密碼確認機制。
```
