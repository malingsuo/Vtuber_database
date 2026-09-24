# VTuber 週邊管理系統

給 VTuber／藝人經紀公司用的週邊商品管理系統：銷售紀錄、庫存與預購圈存、
毛利/淨利報表、訂量與售價預測（報童模型）。多公司隔離的 SaaS 架構。

- 後端：FastAPI + SQLAlchemy + Alembic + PostgreSQL（`backend/`，Poetry 管依賴）
- 前端：Vue 3 + Element Plus（`frontend/`）
- 預測：numpy/scipy 確定性統計計算，無任何 LLM

> **資料說明**：這個 repo 裡的所有資料都是測試資料。`backend/app/seed.py` 產生的藝人、公司、商品與交易紀錄皆為虛構（例如公司「示範娛樂」、藝人「星野銀河」），不含任何真實客戶或營運資料。

## 三分鐘導讀

**一、庫存不存數字，存流水帳**

| 位置 | 內容 |
|---|---|
| [`backend/app/models.py:45`](backend/app/models.py#L45) | `MovementType`：六種帶正負號的異動——入庫（+）、銷售（−）、銷售退回（+）、轉公關品（−）、報廢（−）、盤點調整（±） |
| [`backend/app/models.py:249`](backend/app/models.py#L249) | `InventoryMovement`：只追加的流水帳，`quantity_delta` 帶正負號 |
| [`backend/app/routers/inventory.py:48`](backend/app/routers/inventory.py#L48) | `physical_stock()`：現有庫存永遠由 `sum(quantity_delta)` 算出，沒有可以直接改的庫存欄位 |
| [`backend/app/routers/reports.py:66`](backend/app/routers/reports.py#L66) | 報表把「轉公關品」單獨加總。改用流水帳的起因就是公關品：原本用可變動的計數欄位時，送出去的公關品沒人去更新數字，帳面與實際對不起來，成本也沒進到檔期損益 |

**二、防止並行寫入下的超賣（悲觀鎖）**

| 位置 | 內容 |
|---|---|
| [`backend/app/routers/inventory.py:41`](backend/app/routers/inventory.py#L41) | `get_variant(..., for_update=True)` 內的 `with_for_update()`：`SELECT ... FOR UPDATE` 把「查庫存 → 寫異動」序列化，交易結束自動釋放 |
| [`TESTING_GUIDE.md`](TESTING_GUIDE.md) 第 4.2 節 | 驗證腳本：庫存 9 件，6 個執行緒同時各買 3 件，預期「成功 3／被擋 3，最終庫存 0」，絕不變負 |

**三、所有寫入路徑統一鎖定順序（先鎖規格、再鎖預購），避免死鎖**

| 寫入路徑 | 位置 |
|---|---|
| 單筆輸入異動 | [`inventory.py:125`](backend/app/routers/inventory.py#L125)（`create_movement`） |
| 每日批次銷售 | [`inventory.py:215`](backend/app/routers/inventory.py#L215)（`daily_sales`，逐筆鎖規格） |
| 單筆預購出貨／退回出貨 | [`preorders.py:96`](backend/app/routers/preorders.py#L96)、[`preorders.py:135`](backend/app/routers/preorders.py#L135)：先鎖規格、再鎖預購 |
| 大量出貨 | [`preorders.py:181`](backend/app/routers/preorders.py#L181)（`ship_all`）：先鎖規格，[第 189 行](backend/app/routers/preorders.py#L189)再鎖預購列 |

每條路徑都照同一個順序取鎖，所以兩條路徑同時跑時不會互相持有對方要的鎖而形成循環等待。

## 本機開發

見 [backend/README.md](backend/README.md)。兩個終端機分別：

```bash
cd backend && poetry run uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev   # http://localhost:5173
```

## 正式部署（雲端主機）

需求：Docker 與 Docker Compose。

```bash
cp .env.example .env        # 填入強密碼與隨機 SECRET_KEY（openssl rand -hex 32）
docker compose up -d --build
docker compose exec backend python -m app.bootstrap   # 建立總管理員（僅首次）
```

完成後開瀏覽器連主機的 HTTP_PORT（預設 80），用 `superadmin` 登入 →
「設定 → 公司管理」開通第一家公司並把小管理員帳密交給對方。

### 帳號層級

| 層級 | 誰 | 能做什麼 |
|---|---|---|
| 總管理員 | 平台經營者 | 開通/停用公司；**看不到各公司業務資料** |
| 公司管理者 | 各公司窗口 | 管理自己公司的帳號與全部業務功能 |
| 輸入者／唯讀 | 公司員工 | 輸入資料／僅查看 |

### 維運備忘

- 資料都在 Docker volume `pgdata`；備份：`docker compose exec db pg_dump -U vtuber vtuber_db > backup.sql`
- 升級版本：`git pull && docker compose up -d --build`（migration 會在啟動時自動執行）
- 停用一家公司：設定頁關掉開關即可，該公司所有帳號立即失效，資料保留
