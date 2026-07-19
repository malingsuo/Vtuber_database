# VTuber 週邊管理系統

給 VTuber／藝人經紀公司用的週邊商品管理系統：銷售紀錄、庫存與預購圈存、
毛利/淨利報表、訂量與售價預測（報童模型）。多公司隔離的 SaaS 架構。

- 後端：FastAPI + SQLAlchemy + Alembic + PostgreSQL（`backend/`，Poetry 管依賴）
- 前端：Vue 3 + Element Plus（`frontend/`）
- 預測：numpy/scipy 確定性統計計算，無任何 LLM

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
