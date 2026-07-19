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
| API 退回：`POST /api/preorders/{id}/unship` | 200，狀態回 `reserved`；三數字**精確回到出貨前**；那筆出貨異動消失 |
| 再退一次 | **409**「只有已出貨的預購可以退回圈存」 |
| 取消該預購 | R 釋放，A 加回 |

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
| R6 | 刪出貨異動造成帳約脫鉤（Phase 0） | §4.3 的退回流程 | 帳與約同交易還原 |
| R7 | Excel 匯入髒資料（里程碑 6） | 上傳一個「售價空白＋實售量＞製作量」的檔 → 檢查 | 逐列列錯、通過 0 列、**一筆都不寫**；「確認匯入」按鈕鎖住 |
| R8 | Excel 重複匯入（里程碑 6） | 同一份正確檔匯入兩次 | 第二次每列被「疑似重複匯入」擋下 |
| R9 | Excel 剩餘量反推（里程碑 6） | 匯入一列只填剩餘量 0 | 實售＝製作量、自動判定完售 |
| R10 | 入庫超過製作量（庫存防呆） | 對已滿額入庫的規格再入庫且備註空白 | 前端強制彈原因輸入框；直接打 API 無備註 → **409** 帶數字明細 |
| R11 | 動用圈存的貨沒提醒（庫存防呆） | 對「圈存>0」的規格轉公關到可售變負 | 先跳警告框（含圈存數與變負後數字），確認才寫入；但**實體**要變負則無條件 409 |
| R12 | 刪明細無門檻（權限） | editor 刪異動明細；admin 刪但密碼亂打 | editor **403** 僅限管理者；密碼錯 **403**「密碼確認失敗」；密碼對才 204 |
| R13 | viewer 越權寫入（權限） | viewer 登入後嘗試任何新增/修改 | 一律 **403**「唯讀帳號不能修改資料」，GET 正常 |
| R14 | 管理者自我鎖死（權限） | admin 在使用者管理對**自己**降級/停用；superadmin 停用平台總部 | 自己的角色/啟用控件反灰；API 打 **409**；平台公司 409 |
| R15 | 停用公司只擋新登入（多租戶） | §2 的 #8 | 舊 token **當下**就 403，不必等過期 |
| R16 | 商品名稱卡在前一個品項（表單） | 新增商品先選飯友再改選立牌；再手動改名後切品項 | 名稱跟著變立牌；手改過的名稱**不被覆蓋** |
| R17 | 套組被迫選品項（表單） | 開「這是套組」開關；另用 API 建單品但不帶 item_type_id | UI 品項下拉消失；API **422**「單品必須指定品項類別」 |
| R18 | 刪除連鎖破壞（資料一致性） | 刪「使用中的品項」、刪「有銷售紀錄的商品」、刪「會讓庫存變負的入庫明細」 | 三者都 **409**，附中文原因 |
| R19 | 商品誤刪（刪除確認） | 主頁設定開啟名稱確認後刪商品，名稱打錯 | 確認框擋住「名稱不符」；打對才刪 |
| R20 | 完售資訊遺失（資料設計） | 逐日銷售勾「當天完售」後到預測頁看該規格歷史 | 觀測列標「完售」且需求估計 = 售出 × 1.2（上修） |

---

## 測試後清理

- §1 產生的「E2E測試場」活動與商品：用活動頁刪除商品（有銷售紀錄的會被 R18 擋下——**這是正確行為**，整場清掉請改用「整庫重灌」）。
- §2 的「隔離測試公司」：superadmin 停用即可（無刪除公司功能，資料保留是設計決策）。
- §4.2 的「併發測試品」：同上，或整庫重灌。
- 最乾淨的做法：整套跑完後執行 §0 的整庫重灌，回到標準種子狀態。
