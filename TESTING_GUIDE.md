# 核心手動測試劇本（TESTING_GUIDE）

> 對象：接手的工程師或 AI。照本文件從上到下走一遍（約 40 分鐘），即可驗證系統所有核心邏輯與歷史上修過的每一個坑。
> 慣例：`$T` 代表登入取得的 JWT；UI 步驟以「頁面 → 動作」表示；每步都附【預期】。

## 0. 環境準備

```bash
docker start vtuber-pg                      # PostgreSQL（若未啟動）
cd backend  && poetry run uvicorn app.main:app --reload --port 8000   # 終端機 1
cd frontend && npm run dev                                            # 終端機 2
# 瀏覽器開 http://localhost:5173
```

| 帳號 | 密碼 | 角色 |
|---|---|---|
| superadmin | super123 | 總管理員（平台總部） |
| admin | admin123 | 示範娛樂・管理者 |
| editor | editor123 | 示範娛樂・輸入者 |
| viewer | viewer123 | 示範娛樂・唯讀 |

API 測試先取 token（**注意登入限流 5 次/分**，別在測第 4 節前把額度打光）：

```bash
T=$(curl -s -X POST localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
```

**整庫重灌**（測完想回到乾淨種子資料時；⚠️ 銷毀所有資料）：

```bash
docker exec vtuber-pg psql -U vtuber -d vtuber_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
cd backend && poetry run alembic upgrade head && poetry run python -m app.seed
```

**migration 相容性檢查**（每次新增或修改 migration 後跑；雲端版用 PostgreSQL、桌面版用 SQLite，兩邊都得能升級）：

```bash
cd backend && rm -f /tmp/mig_check.db && (
  export DATABASE_URL=sqlite:////tmp/mig_check.db     # 只在這個子 shell 內生效
  poetry run alembic upgrade head && poetry run alembic downgrade base \
    && poetry run alembic upgrade head && poetry run alembic check
)
```

【預期】全新 SQLite 從頭升到最新 → 降回空庫 → 再升回來，全程無錯誤，最後印 `No new upgrade operations detected.`（model 與 migration 一致）。SQLite 的 `ALTER TABLE` 只能加欄位、改名、刪欄位，其餘變更必須包在 `op.batch_alter_table` 裡，約束也必須具名。

---

## 1. E2E 完整進銷存生命週期

一條龍走完「建藝人 → 建活動 → 商品 → 報價 → 入庫 → 套組 → 預購圈存 → 出貨 → 現場銷售 → 報表」。

| # | 操作 | 【預期】 |
|---|---|---|
| 1 | API 建藝人：`curl -H "Authorization: Bearer $T" -X POST localhost:8000/api/artists -H 'Content-Type: application/json' -d '{"name":"E2E測試藝人"}'` | 201，回傳含 id（藝人無獨立管理頁，用 API 或 http://localhost:8000/docs） |
| 2 | UI 登入 admin →「新建活動」：名稱「E2E測試場」、日期未來一週、類型混合、**填預購期間** | 綠色成功提示，自動跳進活動頁（空的） |
| 3 | 活動頁「為其他藝人新增商品」選 E2E測試藝人 → 新增：品項壓克力立牌、售價 400、規格製作量 100、成本 30 CNY 匯率 4.5、**不勾**「貨已到」 | 商品出現；成本欄 **135**（30×4.5）；庫存/可售 **0**（貨還在廠商端） |
| 4 | 「資料維護 → 報價紀錄」：品項壓克力立牌、數量 100、單價 30、CNY、匯率 4.5 → 記錄報價 | 清單出現一筆，台幣單價 NT$135 |
| 5 | 回活動頁點商品列 → 抽屜「入庫」100、今日日期 → 寫入 | 三數字變 **100 / 0 / 100**；統計列「製作量 100｜累計入庫 100」 |
| 6 | 同藝人再新增商品：徽章、售價 100、製作量 50、**勾**「貨已到，自動入庫」 | 成功訊息含「並依製作量完成入庫」；該列庫存直接 **50** |
| 7 | 再新增商品：開「這是套組」開關 → 品項下拉消失 → 名稱「E2E套組」、售價 450、套組份數 20、內容物勾立牌×1＋徽章×1 | 商品列出現綠色「套組」標籤；滑鼠懸浮標籤顯示兩個內容物 |
| 8 | 點立牌列 → 抽屜預購區：新增預購 3 件 | 三數字變 **100 / 3 / 97**；表格「圈存」欄 3（橘色） |
| 9 | 抽屜按「出貨」 | 「已出貨並扣庫存」；三數字 **97 / 0 / 97**；異動歷史多一筆「銷售 −3｜預購｜單價 NT$400」 |
| 10 | 活動頁「逐日銷售輸入」：通路現場、立牌填 40、徽章填 50 並勾「當天完售」→ 寫入 | 立牌售出 43（3 預購＋40）庫存 57；徽章售出 50 **庫存 0 顯示紅色** |
| 11 | 「報表 → 活動報表」選 E2E測試場 | 營收 = 3×400＋40×400＋50×100 = **NT$22,200**；毛利、銷售率有數字；依藝人/依品項各一列 |
| 12 | 報表頁新增開支：攤位費 5,000 | 淨利立即減 5,000（淨利 = 毛利 − 開支 − 公關成本） |
| 13 | 「預測」頁：E2E測試藝人 × 壓克力立牌、售價 400、成本 135 | 出建議訂量與期望利潤；歷史觀測含 E2E測試場這筆；報價點比較含步驟 4 那個點 |
| 14 | 「資料維護 → Excel」按「匯出 Excel」 | 下載檔含四張工作表，商品銷售明細裡找得到 E2E 的三個商品 |

---

## 2. 多租戶隔離邊界

| # | 操作 | 【預期】 |
|---|---|---|
| 1 | superadmin 登入 →「設定 → 公司管理」開通「隔離測試公司」，小管理員帳號 `isotest`／密碼自訂 | 成功；公司列表多一列，帳號數 1 |
| 2 | 登出 → isotest 登入 → 查詢活動、報表、資料維護逐頁看 | **全部空白**：年份下拉無選項、品項清單只有… 注意：新公司**連預設品項都沒有**，一切從零 |
| 3 | isotest 建一位藝人「B社藝人」（API 或商品流程） | 成功，只有自己看得到 |
| 4 | 換回 admin 登入 → 查藝人清單 | **沒有** B社藝人；示範娛樂資料原封不動 |
| 5 | 用 admin 的 token 直接探測 B 公司資源 id：`curl -H "Authorization: Bearer $T" localhost:8000/api/artists/{B藝人id}` | **404**（不是 403——連「存在與否」都探測不到） |
| 6 | isotest 打 `GET /api/admin/companies` | **403**「此操作僅限總管理員」 |
| 7 | isotest 到「設定」建自己公司的帳號、試圖選角色 | 角色選單**沒有**總管理員選項 |
| 8 | superadmin 把「隔離測試公司」開關關閉（停用） | 確認框警告；isotest **當下**再打任何 API → 403「貴公司的服務已停用」；重新登入也被擋 |
| 9 | superadmin 試圖停用「平台總部」 | **409**「不能停用平台自己的公司」 |

---

## 3. 報童預測模型邊界值

全部用 API 打（UI 也可，行為一致）。基底：`localhost:8000/api/forecast?artist_id=1&item_type_id=2`（星野銀河 × 壓克力立牌，種子資料有歷史）。

| # | 參數 | 【預期】 |
|---|---|---|
| 1 | `price=450&cost=150` 正常值 | 200：μ±σ、樣本數與依據說明、CR≈0.667、建議訂量、報價點比較（可觀察「訂 500 期望利潤反而低於訂 300」的滯銷效應） |
| 2 | `price=100&cost=150`（成本＞售價） | 200 但 `warning`「賣一個賠一個」，建議訂量 null |
| 3 | `price=450&cost=0` | **422**「單位成本必須大於 0」（修補前是 500 崩潰） |
| 4 | `price=450&cost=150&salvage=450`（殘值≥售價） | **422**「殘值必須低於售價」（修補前除以零） |
| 5 | `price=450&cost=0.01`（極端低成本） | 200：CR 被保險絲鎖在 **0.999**，建議訂量為有限數字 |
| 6 | `price=450`（不給成本） | 200：CR/建議訂量為 null，但報價點比較照常輸出 |
| 7 | 建一個全新品項（設定頁），拿它查 `price=100` | **409**「這個品項還沒有任何歷史銷售資料」 |
| 8 | 新藝人（無任何歷史）× 壓克力立牌 | 200：依據顯示「用品項平均 × 熱度係數」——退階機制工作中 |

---

## 4. 高併發與防呆機制

### 4.1 登入限流（放在所有登入操作之後測！觸發後本機鎖一分鐘）

連打 7 次錯誤密碼：

```bash
for i in 1 2 3 4 5 6 7; do curl -s -o /dev/null -w "第$i次: %{http_code}\n" \
  -X POST localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"wrong"}'; done
```

【預期】同一分鐘內第 6 次起（若稍早有登入過則更早）回 **429**，訊息「嘗試次數過多，請一分鐘後再試」；等 60 秒後恢復。

### 4.2 併發防超賣（悲觀鎖）

```bash
cd backend && poetry run python - <<'EOF'
import json, threading, urllib.request
BASE = "http://localhost:8000/api"
def call(m, p, tk=None, b=None):
    r = urllib.request.Request(BASE+p, method=m); r.add_header("Content-Type","application/json")
    if tk: r.add_header("Authorization", f"Bearer {tk}")
    try:
        with urllib.request.urlopen(r, json.dumps(b).encode() if b else None) as x:
            return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, {}
_, lg = call("POST","/auth/login",b={"username":"admin","password":"admin123"}); tk = lg["token"]
_, pr = call("POST","/products",tk,{"event_id":1,"artist_id":1,"item_type_id":1,
    "name":"併發測試品","price_twd":100,"variants":[{"production_qty":9}]})
vid = pr["variants"][0]["id"]
call("POST","/inventory/movements",tk,{"variant_id":vid,"movement_type":"inbound","quantity":9,"movement_date":"2026-01-01"})
res=[]
def sell():
    s,_=call("POST","/inventory/movements",tk,{"variant_id":vid,"movement_type":"sale",
        "quantity":3,"movement_date":"2026-01-01","channel":"onsite"}); res.append(s)
ts=[threading.Thread(target=sell) for _ in range(6)]
[t.start() for t in ts]; [t.join() for t in ts]
_, st = call("GET", f"/inventory/variants/{vid}/stock", tk)
print(f"成功 {res.count(201)}／被擋 {res.count(409)}，最終庫存 {st['physical']}",
      "✓無超賣" if res.count(201)==3 and st["physical"]==0 else "✗超賣！立即回報")
EOF
```

【預期】`成功 3／被擋 3，最終庫存 0 ✓無超賣`。庫存 9 件搶 18 件需求，**恰好賣完、絕不變負**。

### 4.3 預購狀態流轉（含出貨退回）

在任一有庫存的商品抽屜操作，全程盯三數字（以 實體/圈存/可售 = P/R/A 表示）：

| 步驟 | 【預期】 |
|---|---|
| 新增預購 2 件 | P 不變、R+2、A−2（圈存不動實體） |
| 出貨 | P−2、R−2、A 不變；異動歷史多「銷售｜預購」一筆 |
| 預購區「展開已出貨的預購」→ 該筆「出貨退回」（或 API `POST /api/preorders/{id}/unship`） | 200，狀態回 `reserved`；三數字**精確回到出貨前**；原出貨異動**保留**，劃刪除線並標「已沖銷」，上方多一筆「沖銷 #原id」（+2，日期沿用出貨日，備註「出貨退回：預購 #id」） |
| 再退一次（API） | **409**「只有已出貨的預購可以退回圈存」 |
| 再出貨一次 | 產生新的出貨異動；之後再退回，沖銷的是這筆新的，不會碰到已沖銷的舊紀錄 |
| 取消該預購 | R 釋放，A 加回 |

### 4.4 流水帳只追加：沖銷

流水帳沒有修改也沒有刪除端點，更正一律「沖銷」：新增一筆反向紀錄指向原紀錄（`reverses_movement_id`），原紀錄保留。腳本自建「沖銷測試品」，每一步印 ✓／✗：

```bash
cd backend && poetry run python - <<'EOF'
import json, urllib.request
BASE = "http://localhost:8000/api"
def call(m, p, tk=None, b=None, pw=None):
    r = urllib.request.Request(BASE+p, method=m); r.add_header("Content-Type","application/json")
    if tk: r.add_header("Authorization", f"Bearer {tk}")
    if pw: r.add_header("X-Confirm-Password", pw)
    try:
        with urllib.request.urlopen(r, json.dumps(b).encode() if b is not None else None) as x:
            return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")
ok = True
def check(name, cond, extra=""):
    global ok; ok = ok and bool(cond); print("✓" if cond else "✗", name, extra)
_, lg = call("POST","/auth/login",b={"username":"admin","password":"admin123"}); tk = lg["token"]
_, pr = call("POST","/products",tk,{"event_id":1,"artist_id":1,"item_type_id":1,
    "name":"沖銷測試品","price_twd":100,"variants":[{"production_qty":10}]})
vid = pr["variants"][0]["id"]
def mv(**b): return call("POST","/inventory/movements",tk,{"variant_id":vid,**b})[1]
def stock(): return call("GET",f"/inventory/variants/{vid}/stock",tk)[1]
def ledger(): return {m["id"]: m for m in call("GET",f"/inventory/variants/{vid}/movements",tk)[1]}
def rev(mid, reason="測試沖銷", pw="admin123", token=None):
    return call("POST",f"/inventory/movements/{mid}/reverse",token or tk,{"reason":reason},pw)
def revenue(): return float(call("GET","/reports/events/1",tk)[1]["revenue"])

inb = mv(movement_type="inbound", quantity=10, movement_date="2026-01-01")
scr = mv(movement_type="scrap", quantity=2, movement_date="2026-01-02")
s, r = rev(scr["id"], "報廢數量輸入錯誤"); L = ledger()
check("1 正常沖銷 → 201", s == 201, f"（原 #{scr['id']}，沖銷 #{r.get('id')}）")
check("  沖銷紀錄同類型、同日期、數量相反、完售欄為空",
      r.get("movement_type") == "scrap" and r.get("movement_date") == "2026-01-02"
      and r.get("quantity_delta") == 2 and r.get("sold_out_today") is None)
check("  原紀錄保留並標示被誰沖銷", L[scr["id"]]["reversed_by_id"] == r.get("id"))
check("  實體庫存回到 10", stock()["physical"] == 10)
s, e = rev(scr["id"]); check("2 同一筆沖銷兩次 → 409", s == 409, e.get("detail"))
s, e = rev(r["id"]); check("3 沖銷一筆沖銷紀錄 → 409", s == 409, e.get("detail"))
mv(movement_type="pr_gift", quantity=7, movement_date="2026-01-03", recipient="測試對象")
s, e = rev(inb["id"])
check("4 沖銷會讓庫存變負 → 409", s == 409 and stock()["physical"] == 3, e.get("detail"))

_, po = call("POST","/preorders",tk,{"variant_id":vid,"quantity":2,"created_date":"2026-01-04"})
_, sh = call("POST",f"/preorders/{po['id']}/ship",tk,{"ship_date":"2026-01-05"})
ship_mid = sh["shipment_movement_id"]
check("5 出貨時預購記下自己的出貨異動", ship_mid is not None and stock()["physical"] == 1,
      f"（出貨異動 #{ship_mid}）")
s, e = rev(ship_mid)
check("6 預購出貨直接沖銷 → 409，要求改用出貨退回", s == 409 and stock()["physical"] == 1, e.get("detail"))
s, back = call("POST",f"/preorders/{po['id']}/unship",tk); L = ledger()
pair = [m for m in L.values() if m["reverses_movement_id"] == ship_mid]
check("7 出貨退回 → 200，預購回到圈存", s == 200 and back["status"] == "reserved"
      and back["shipment_movement_id"] is None)
check("  帳上同時看得到原出貨（已沖銷）與沖銷紀錄（日期沿用出貨日）",
      L[ship_mid]["reversed_by_id"] is not None and len(pair) == 1
      and pair[0]["movement_date"] == "2026-01-05",
      f"（原 #{ship_mid}，沖銷 #{pair[0]['id'] if pair else '?'}：{pair[0]['notes'] if pair else ''}）")
st = stock(); check("  實體庫存加回、圈存恢復", st["physical"] == 3 and st["reserved"] == 2)
_, sh2 = call("POST",f"/preorders/{po['id']}/ship",tk,{"ship_date":"2026-01-06"})
check("  再出貨連到新的出貨異動", sh2["shipment_movement_id"] not in (None, ship_mid))

_, ed = call("POST","/auth/login",b={"username":"editor","password":"editor123"})
s, _ = rev(inb["id"], token=ed["token"]); check("8 editor 沖銷 → 403", s == 403)
s, e = rev(inb["id"], pw="wrong"); check("  密碼錯 → 403", s == 403, e.get("detail"))
s, _ = rev(inb["id"], reason="   "); check("  原因空白 → 422", s == 422)
s, _ = call("DELETE",f"/inventory/movements/{inb['id']}",tk)
check("  DELETE 端點已不存在 → 404", s == 404)

r0 = revenue()
sale = mv(movement_type="sale", quantity=1, movement_date="2026-01-07", channel="onsite")
r1 = revenue(); rev(sale["id"], "誤記一筆銷售"); r2 = revenue()
day = [d for d in call("GET","/reports/events/1/daily",tk)[1] if d["date"] == "2026-01-07"]
check("9 沖銷銷售後活動營收精確扣回", r1 - r0 == 100 and r2 == r0, f"（{r0:,.0f} → {r1:,.0f} → {r2:,.0f}）")
check("  逐日報表：當天當通路抵銷為 0", day and all(d["qty"] == 0 for d in day))
print("全部通過 ✓" if ok else "有項目失敗 ✗ 立即回報")
EOF
```

【預期】19 行全部 ✓，最後印 `全部通過 ✓`。重點對照：

| # | 情境 | 【預期】 |
|---|---|---|
| 1 | 誤記報廢 2 件後沖銷 | 201；沖銷紀錄沿用原類型與日期、數量相反、`sold_out_today` 為空；原紀錄仍在並回傳 `reversed_by_id` |
| 2 | 同一筆再沖銷一次 | **409**「已在 #x 沖銷過，同一筆只能沖銷一次」（unique 約束是最後防線） |
| 3 | 沖銷一筆沖銷紀錄 | **409**「本身是沖銷紀錄，不能再沖銷」 |
| 4 | 入庫 10 → 轉公關 7 → 沖銷那筆入庫 | **409**「會讓實體庫存變成負數」，庫存維持 3 |
| 5–7 | 預購出貨後直接沖銷出貨異動；改用出貨退回 | 直接沖銷 **409**，要求改用「出貨退回」；出貨退回 200，帳上同時有原出貨（已沖銷）與沖銷紀錄 |
| 8 | editor 沖銷／密碼錯／原因空白／打舊的 DELETE | 403／403／422／404 |
| 9 | 誤記一筆銷售後沖銷 | 活動營收先 +100 再精確回到原值；逐日報表該日該通路淨額 0（沖銷沿用原日期，不會把銷售挪到今天） |

UI 補驗（admin 登入）：開任一商品抽屜 → 異動歷史每列有 `#id`，操作欄是「沖銷」→ 對話框要求原因與管理者密碼 → 沖銷後原列劃刪除線並標「已沖銷」（滑過顯示「由 #x 沖銷」）、上方多一列「沖銷 #原id」（滑過顯示沖銷時間）；這兩列都不再有「沖銷」按鈕。預購通路的列在對話框裡會提示改用「出貨退回」。

---

## 5. 歷次踩坑對應的迴歸測試

> 這張表是本系統的「疫苗接種紀錄」。**改動任何相關模組後，對應列必須重測**；任何一列失敗代表舊 bug 復發，立即回報。

| # | 當年的坑（對應 commit 主題） | 測試步驟 | 【預期】 |
|---|---|---|---|
| R1 | 跨公司同名帳號鎖死登入（安全修補：username 全域唯一） | superadmin 開新公司，小管理員帳號填 `admin` | **409**「帳號名稱已被使用（全系統唯一）」 |
| R2 | 併發超賣（安全修補：悲觀鎖） | 跑 §4.2 腳本 | 恰好賣完、庫存 0、無負數 |
| R3 | 報童 cost=0 / salvage≥price 崩潰（安全修補） | §3 的 #3、#4 | 都是 **422**，不是 500 |
| R4 | 商品指向別家廠商/商品（Phase 0 漏洞 B） | 建商品帶 `"vendor_id":9999`；再用 PUT 對既有商品塞 `"restock_source_id":9999` | 兩路徑都 **422**「找不到指定的…」 |
| R5 | 登入暴力破解（Phase 0 漏洞 C） | §4.1 | 第 6 次起 429 |
| R6 | 刪出貨異動造成帳約脫鉤（Phase 0） | §4.3 的退回流程；§4.4 的 #5–7 | 帳與約同交易還原；原出貨異動保留並被沖銷；直接沖銷預購出貨 **409** |
| R7 | Excel 匯入髒資料（里程碑 6） | 上傳一個「售價空白＋實售量＞製作量」的檔 → 檢查 | 逐列列錯、通過 0 列、**一筆都不寫**；「確認匯入」按鈕鎖住 |
| R8 | Excel 重複匯入（里程碑 6） | 同一份正確檔匯入兩次 | 第二次每列被「疑似重複匯入」擋下 |
| R9 | Excel 剩餘量反推（里程碑 6） | 匯入一列只填剩餘量 0 | 實售＝製作量、自動判定完售 |
| R10 | 入庫超過製作量（庫存防呆） | 對已滿額入庫的規格再入庫且備註空白 | 前端強制彈原因輸入框；直接打 API 無備註 → **409** 帶數字明細 |
| R11 | 動用圈存的貨沒提醒（庫存防呆） | 對「圈存>0」的規格轉公關到可售變負 | 先跳警告框（含圈存數與變負後數字），確認才寫入；但**實體**要變負則無條件 409 |
| R12 | 動帳無門檻（權限；原為刪明細，現為沖銷） | editor 沖銷異動；admin 沖銷但密碼亂打 | editor **403** 僅限管理者；密碼錯 **403**「密碼確認失敗，未執行沖銷」；密碼對才 201 |
| R13 | viewer 越權寫入（權限） | viewer 登入後嘗試任何新增/修改 | 一律 **403**「唯讀帳號不能修改資料」，GET 正常 |
| R14 | 管理者自我鎖死（權限） | admin 在使用者管理對**自己**降級/停用；superadmin 停用平台總部 | 自己的角色/啟用控件反灰；API 打 **409**；平台公司 409 |
| R15 | 停用公司只擋新登入（多租戶） | §2 的 #8 | 舊 token **當下**就 403，不必等過期 |
| R16 | 商品名稱卡在前一個品項（表單） | 新增商品先選飯友再改選立牌；再手動改名後切品項 | 名稱跟著變立牌；手改過的名稱**不被覆蓋** |
| R17 | 套組被迫選品項（表單） | 開「這是套組」開關；另用 API 建單品但不帶 item_type_id | UI 品項下拉消失；API **422**「單品必須指定品項類別」 |
| R18 | 刪除連鎖破壞（資料一致性） | 刪「使用中的品項」、刪「有銷售紀錄的商品」、沖銷「會讓庫存變負的入庫明細」 | 三者都 **409**，附中文原因 |
| R19 | 商品誤刪（刪除確認） | 主頁設定開啟名稱確認後刪商品，名稱打錯 | 確認框擋住「名稱不符」；打對才刪 |
| R20 | 完售資訊遺失（資料設計） | 逐日銷售勾「當天完售」後到預測頁看該規格歷史 | 觀測列標「完售」且需求估計 = 售出 × 1.2（上修） |
| R21 | 流水帳被刪改（只追加） | §4.4 全跑；`curl -X DELETE -H "Authorization: Bearer $T" localhost:8000/api/inventory/movements/1` | 沒有刪除端點（**404**）；重複沖銷、沖銷沖銷紀錄都 **409**；原紀錄永遠保留 |
| R22 | migration 只能在 PostgreSQL 跑（SQLite 相容） | §0 的 migration 相容性檢查 | 全新 SQLite 升→降→升無錯誤，`alembic check` 無差異 |
| R23 | 銷售退回沒扣營收（報表口徑） | 抽屜選「銷售退回」：先不選通路寫入；再選「通販」、數量 1、退款單價留空寫入；看活動報表與逐日圖表。另用 API 記銷售退回但不帶 `channel` | 出現「通路」「退款單價」欄位；沒選通路前端擋「請選擇退回的通路」；寫入後營收減少「定價 × 1」，逐日圖表退回日的**通販**出現 −1；填了退款單價則只扣該金額；API 不帶通路 **422**「銷售退回必須指定通路」 |

---

## 測試後清理

- §1 產生的「E2E測試場」活動與商品：用活動頁刪除商品（有銷售紀錄的會被 R18 擋下——**這是正確行為**，整場清掉請改用「整庫重灌」）。
- §2 的「隔離測試公司」：superadmin 停用即可（無刪除公司功能，資料保留是設計決策）。
- §4.2 的「併發測試品」、§4.4 的「沖銷測試品」：同上，或整庫重灌。
- 最乾淨的做法：整套跑完後執行 §0 的整庫重灌，回到標準種子狀態。
