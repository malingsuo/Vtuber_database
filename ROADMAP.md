# 開發路線圖（ROADMAP）

> 現況：10 個里程碑全數完成——記帳、庫存/預購圈存、報表、報童預測、三級權限、多公司雲端部署、Excel 匯入匯出。
> 本文件規劃下一階段。閱讀前先看 `HANDOFF.md`（架構防線、已知缺口、AI 開發公約）——**那六條絕對約束適用於本路線圖的所有工作**。

## 總原則（做任何一項前重讀一次）

1. 需求估計層可以換，**報童決策層（`forecast.py: _expected_profit`、CR 公式）不可動**。
2. 攤分、圖表、警示都是**讀取時計算**，不新增任何「算出來的欄位」進資料庫。
3. 新端點一律走既有規範：`get_company_id` 隔離 + `authorize` 權限閘。

---

## Phase 0：收尾 ✅（2026-07-20 完成）

HANDOFF.md 標記的待處理項，已全部修補（詳見 HANDOFF.md 修補狀態列）：

| 項目 | 位置 | 做法 |
|---|---|---|
| 漏洞 B：商品跨公司引用 | `products.py: _check_fk` | 補驗 `vendor_id`、`restock_source_id` 的公司歸屬（create 與 update 都要過） |
| 漏洞 C：登入暴力破解 | `main.py` 或 nginx | slowapi 每 IP 5 次/分，或 `nginx.conf` 加 `limit_req` |
| 預購出貨退回 | `preorders.py` | 新增 `POST /preorders/{id}/unship`：同一交易內「刪出貨異動＋狀態改回 reserved」，取代直接刪異動造成的帳約脫鉤 |

---

## Phase 1：套組營收攤分 ✅（2026-07-20 完成，攤分前後總營收檢核通過）

**目標**：報表能回答「套組的錢實際是誰（哪位藝人/哪種品項）賺的」。

- **動哪裡**：`backend/app/routers/reports.py`（主要）、`app/schemas.py`（回傳格式加欄位）、`frontend/src/views/ReportView.vue`（開關）。**不動任何資料表**——攤分是報表口徑，不是要儲存的事實（存了會在內容物改價時變髒資料）。
- **API**：`GET /reports/events/{id}?allocate_bundles=true`（預設 false）。兩種口徑並存，方便對帳。
- **演算法**：
  1. 撈活動內套組的 `bundle_items` → 每個套組規格對應 [(內容物規格, 件數/套)]。
  2. 內容物權重 = 單售定價 × 件數 ÷ Σ(定價 × 件數)；**Σ=0（內容全是贈品）退化為平均分攤**。
  3. 套組銷售異動的營收 × 權重 → 加回內容物**所屬商品**，再彙總到內容物的藝人/品項列（注意：跟著內容物的 `artist_id` 走，資料模型允許跨藝人套組）。
  4. 攤分後套組自身列標示「已攤分」並歸零，避免重複計算。
- **驗收等式（必寫成測試）**：攤分前後的活動總營收一分不差。
- **後續連動**：攤分穩定後，`forecast.py: _observations` 可把攤回的銷量計入品項需求（目前 `is_bundle=False` 直接排除套組），讓「徽章被套組帶走的量」不再從需求估計中消失。

## Phase 2：預購累積曲線的時間序列預測（3～5 天）

**目標**：預購窗開了幾天，就能外推最終需求——在下訂生產前看到需求，這是全系統價值最高的預測。

- **動哪裡**：新檔 `backend/app/forecast_ts.py`（估計邏輯）、`app/routers/forecast.py`（加端點）、`app/schemas.py`、`frontend/src/views/ForecastView.vue`（來源開關）。**不需要新資料表**——`preorders(created_date, quantity, status)` 就是曲線原始點，`events.preorder_start/end` 是窗，`cancelled` 給取消率。**決策層零改動**：時間序列只是產出另一組 (μ, σ) 餵同一個報童模型——當初分兩層的設計此刻兌現。
- **API**：`GET /forecast/preorder-projection?variant_id=`（規格級）與 `?product_id=`（彙總）。回傳對齊既有 `DemandEstimate`（含 `basis` 中文說明），外加曲線點列給前端畫圖。
- **演算法**（可解釋優先，不上黑盒）：
  1. 該規格的預購按日累積（扣 cancelled；取消率另計）。
  2. **形狀函數外推**：把公司歷史每場的累積曲線正規化到 [0,1]×[0,1]，平均成 F(t)；目前進度 c(t) ⇒ 預測終值 = c(t)/F(t)。預購曲線典型是「開頭衝、中間平、截止前翹」的 S 形，這方法直接吃掉這個形狀。
  3. σ = 歷史各場「在同一時間點外推」的誤差離散度；淨需求 = 終值 × (1 − 歷史取消率)。
  4. 樣本 <3 場有預購窗的活動 → 退化為線性外推並在 `basis` 註明（沿用小樣本退階的既有慣例）。
- **前端**：預測頁加「需求來源：歷史統計／預購曲線」切換；曲線圖（見 Phase 3 的圖表基建）疊實際點與外推線。

## Phase 3：報表圖表化（2～3 天）

**目標**：老闆看圖，不看表。

- **技術選型**：ECharts（`echarts` + `vue-echarts`），中文文件齊全、離線打包、和 Element Plus 同生態習慣。`npm install echarts vue-echarts`。
- **動哪裡**：幾乎純前端——`ReportView.vue` 重構＋新增 `frontend/src/components/charts/` 目錄。後端只需補一個資料端點：
  - `GET /reports/events/{id}/daily`：該活動逐日銷量/營收（按通路分組）——資料就在 `inventory_movements.movement_date/channel`，一個 group by 查詢。
- **首批圖表**（先做前四張就有感）：
  | 圖 | 資料來源（既有 API） |
  |---|---|
  | 活動逐日銷售長條（分通路堆疊） | 新的 `/daily` 端點 |
  | 藝人營收占比圓餅 | `/reports/events/{id}` 的 `by_artist` |
  | 品項銷售率橫向長條 | `by_item_type` |
  | 年度營收/毛利趨勢線 | `/reports/artists?year=` 逐年呼叫 |
  | 預購累積曲線（實際＋外推） | Phase 2 的 projection 端點 |
- **注意**：ECharts 整包約 1MB，用按需引入（`echarts/core` + 需要的圖類型），順便解決現有的 bundle 體積警告。

---

## Phase 4：進階功能發想（依商業價值排序）

### 4.1 滯銷庫存警示與再販建議引擎

- **是什麼**：自動盤點全公司庫存，標出「壓了多少錢、放了多久、預估多久賣得完」，並反向建議「這些商品湊得出一場再販/福袋」。
- **商業價值**：週邊業的現金全壓在庫存上。系統已經知道每個規格的庫存、成本、歷史去化速度——把「倉庫裡沉睡的 NT$ 380,000」變成一個紅色數字擺在儀表板上，是老闆最有感的功能；再販建議直接創造營收機會。福袋場景還能回頭吃 Phase 1 的套組機制（滯銷品組福袋＝建一個套組）。
- **技術可行性**：**高，零新表**。`GET /reports/dead-stock`：庫存 × 成本 = 壓貨金額；近 N 天銷量算去化速度；`最後一筆銷售距今` 當滯銷天數。全部是既有資料的查詢。前端一頁排序表＋警示色。約 2 天。

### 4.2 檔期損益模擬器（What-if Planner）

- **是什麼**：辦活動**之前**的沙盤推演：勾選藝人 × 品項組合，系統逐項跑既有的預測模組，加總期望營收/成本，再填入預估攤位費/人力 → 輸出「這場預期淨利 NT$xx，損益兩平需賣 xx 件」。
- **商業價值**：把系統從「事後記帳」推進到「事前決策」——要不要報名 FF？攤位費 4 萬划不划算？帶哪三位藝人的貨？這是經紀公司每一檔期都要吵的問題，現在有數字可吵。這也是對外賣 SaaS 時最好展示的功能。
- **技術可行性**：**高**。核心就是把 `forecast.py` 的單品預測**批次化**：`POST /forecast/simulate` 收 `[{artist_id, item_type_id, price, cost}]` 陣列＋開支預估，迴圈呼叫既有 `_estimate_demand` + 報童層後加總。不動任何現有邏輯，是純粹的組合層。前端一頁互動表單。約 2～3 天。

### 4.3 藝人熱度自動同步（YouTube Data API，選配）

- **是什麼**：不再手動抄訂閱數——藝人設定頁填 YouTube 頻道 ID，系統每天自動抓訂閱數寫進 `artist_metrics`。
- **商業價值**：熱度資料的價值在**連續性**（成長率才是預測係數的原料），手動輸入注定斷斷續續。自動化後「辦活動對訂閱的拉抬效果」「熱度轉折預警」這些分析才變得可能。
- **技術可行性**：**中**——它是全系統第一個外部依賴，所以定位為**選配**（沒填 API key 一切照舊，維持離線可用的原則）。實作：`artists` 表加 `youtube_channel_id` 欄（一次 migration）；`app/sync_metrics.py` 排程任務（容器內 cron 或 APScheduler）呼叫 YouTube Data API v3 `channels.list`（免費配額綽綽有餘），寫入時 `source` 標記自動。注意 YouTube 訂閱數超過 10 萬會四捨五入（如 123,456 顯示 123,000）——存回傳值即可，精度對趨勢分析足夠。約 2 天。

---

## Phase D：桌面版產品化（免費試用 → 付費完整版）

> **商業模式**：GitHub 釋出免費試用版（功能鎖＋資料量上限）→ 用習慣後購買授權檔解鎖完整版。付費版＝完全離線、全功能、Nuitka 編譯的 exe（原始碼不可見）。
> **給接手 AI（Opus）的說明**：D1→D5 嚴格依序執行，每個任務都有〔目標／實作／驗收〕。驗收全部通過才可進下一項。全程遵守 HANDOFF.md 的六條絕對約束。**單一程式碼庫**：桌面版與雲端版共用程式碼，用環境變數 `APP_MODE=desktop|cloud` 區分，禁止 fork 出第二份程式碼。

### D1. 單機執行基礎（不依賴 Docker/Node）

- **目標**：一個資料夾、一個指令，在沒有 Docker、沒有 Node 的電腦上跑起完整系統。
- **實作**：
  1. `app/config.py` 加 `app_mode: str = "cloud"`；desktop 模式下 `database_url` 預設指向**使用者資料夾**的 SQLite：Windows `%APPDATA%/VtuberMerch/app.db`、macOS/Linux `~/.vtuber-merch/app.db`（用 `platformdirs` 套件取路徑，目錄不存在就建立）。**資料庫絕不放程式資料夾**——這是更新不掉資料的前提。
  2. `app/main.py`：desktop 模式下用 `StaticFiles` 供應 `frontend/dist`（掛在 `/`，API 維持 `/api`；SPA fallback 把非 /api 路徑導回 index.html）。
  3. 新增 `app/desktop.py` 啟動器：啟動時自動 `alembic upgrade head` → 若資料庫全空自動建預設管理員（`admin/admin123`，首頁提示改密碼）與預設品項清單 → 起 uvicorn（僅綁 127.0.0.1）→ `webbrowser.open("http://127.0.0.1:8620")`。
  4. 埠固定 8620（避開常見占用），被占用時往上找。
- **驗收（Opus 自查）**：`APP_MODE=desktop poetry run python -m app.desktop` 在**停用 Docker** 的狀態下啟動；瀏覽器打開就是登入頁；建活動→商品→入庫→報表全流程可走；把程式資料夾整個刪掉重解壓，資料（在使用者資料夾）**還在**；TESTING_GUIDE §1 在 desktop 模式全數通過（多租戶 §2 除外——桌面版單公司）。

### D2. 試用版功能鎖與授權機制（先做鎖，再做打包——順序刻意如此，打包要驗證鎖有效）

- **目標**：同一顆程式，無授權檔＝試用版，有合法授權檔＝完整版。
- **授權設計（Ed25519 非對稱簽章，完全離線可驗）**：
  - 授權檔 `license.key`（放資料夾同層或由 UI 匯入）內容：`{"licensee": "購買者名稱", "email": "...", "issued": "YYYY-MM-DD", "edition": "full"}` ＋ 你用**私鑰**對這段 JSON 的簽章，base64 打包。
  - 程式內嵌**公鑰**驗簽（`cryptography` 套件）。私鑰只存在你手上——新增 `tools/issue_license.py`（**不隨產品發布**，放 repo 但打包時排除）給你簽發授權用。
  - 不做機器綁定（離線友善、客服成本低）；授權檔內含購買者姓名即可嚇阻隨意流傳。
- **試用限制（資料量＋功能鎖，不用天數——離線改時鐘就能繞過天數）**：
  - 活動上限 **5 場**、藝人上限 **3 位**（建立第 6/4 個時後端回 402，訊息附購買資訊）。
  - **預測模組**與 **Excel 匯入**整個上鎖（403 + 前端顯示「完整版功能」蒙版）——Excel「匯出」保持開放，使用者的資料永遠拿得走，這是信任底線。
- **實作**：新增 `app/license.py`（載入/驗簽/回傳 edition）；新增依賴 `require_full_edition`（掛在 forecast 與 excel import 路由）；上限檢查加在 events/artists 的 create；`GET /api/license/status` 回目前版本與限制；前端登入後顯示「試用版｜完整版」徽章與匯入授權檔的入口（設定頁）。
- **驗收**：無授權檔＝建第 6 場活動回 402、預測頁顯示鎖定蒙版；用 `issue_license.py` 簽一張授權、由 UI 匯入 → 全功能解鎖、不用重啟；**手改授權檔任一字元 → 驗簽失敗回試用版**；`cloud` 模式完全不受授權機制影響（SaaS 版永遠全功能）。

### D3. Windows 打包（Nuitka 編譯，原始碼保護）

- **目標**：單一資料夾（onefile 啟動太慢，用 standalone 資料夾＋捷徑）的 Windows 發行包，雙擊 `VtuberMerch.exe` 即用。
- **實作**：
  1. 前端 `npm run build` 產出 dist，一併打包。
  2. Nuitka：`python -m nuitka --standalone --follow-imports app/desktop.py`，`--include-data-dir` 帶入 dist 與 migrations；`tools/` 目錄**必須排除**（簽發私鑰工具不能出貨）。
  3. 寫 `tools/build_desktop.ps1` 一鍵建置腳本；產物用 Inno Setup 或 zip 發布。
  4. `--windows-icon` 與版本資訊；考慮 `--windows-console-mode=disable`。
- **原始碼保護的誠實邊界（寫給老闆看的）**：Nuitka 編譯為機器碼，逆向難度＝一般商業軟體；不存在絕對防破解，目標是「破解成本 > 售價」。授權驗簽在 Nuitka 編譯層內，無法用改設定檔繞過。
- **驗收**：在**乾淨的 Windows（無 Python/Node/Docker）**虛擬機解壓即跑；發行包內用文字編輯器/解包工具**找不到任何 .py 原始碼**；試用限制在打包版中生效；D2 的授權匯入在打包版中生效。

### D4. 保留資料的更新機制（回答「使用者買了之後怎麼更新」）

- **目標**：使用者下載新版覆蓋（或安裝程式自動覆蓋）→ 開啟 → 資料與授權完好、結構自動升級。
- **實作**：
  1. 資料庫與 `license.key` 都在使用者資料夾（D1 已保證）→ 覆蓋程式資料夾**天然不碰資料**。
  2. `app/desktop.py` 啟動流程加固：偵測到資料庫版本落後 → **先自動備份**（複製 `app.db` 為 `app.db.backup-日期`，並輸出一份 Excel 匯出到使用者資料夾）→ 再跑 `alembic upgrade head` → 失敗則還原備份並顯示可讀的錯誤訊息。
  3. 版本號顯示在前端頁尾（讀 `app/version.py`）；`GET /api/system/version` 供未來「檢查更新」用（僅提示，不自動下載——維持離線原則）。
- **驗收（模擬真實升級）**：用舊版建資料 → 換上含新 migration 的新版程式 → 啟動後資料還在、新欄位可用、使用者資料夾出現備份檔；故意放一個會失敗的 migration → 啟動顯示錯誤且原資料庫未被破壞。

### D5. 發布與試用轉付費動線

- GitHub Releases 放試用版 zip（**發行包不含原始碼**；repo 本身若要開源需另行決策——預設**私有 repo，只發 Releases**）。
- README 加「下載試用 → 購買 → 收到 license.key → 設定頁匯入」四步說明；購買管道（表單/信箱）由你決定。
- 驗收：一位非工程背景測試者能在 10 分鐘內完成下載→安裝→建第一筆商品，全程不需要任何指令。

**Phase D 順序與依賴**：D1（單機基礎）→ D2（授權鎖，功能面）→ D3（打包，驗證鎖在編譯版有效）→ D4（更新機制）→ D5（發布）。D1/D2 可在現有開發環境完成；D3 起需要 Windows 環境。與 Phase 1~4 無依賴衝突，可穿插進行，但 **D2 的 402/403 閘要在新功能（如損益模擬器）加入時同步掛上**——新的付費級功能一律進 `require_full_edition` 清單。

---

## 建議順序與里程碑切分

```
Phase 0 收尾（半天）
  → Phase 1 套組攤分（報表正確性優先）
  → Phase 3 圖表化（讓既有數字先變好看，快速有感）
  → Phase 2 預購時間序列（需要多累積幾場預購資料，不急著上）
  → Phase 4.1 滯銷警示 → 4.2 損益模擬器 → 4.3 熱度同步
```

每個 Phase 完成標準：功能實測 + 對應章節從本文件移到 HANDOFF.md 的「系統快照」。
