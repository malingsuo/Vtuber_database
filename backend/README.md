# VTuber 週邊管理系統 — 後端

FastAPI + SQLAlchemy + Alembic + PostgreSQL（開發初期暫用 SQLite）。
依賴管理使用 Poetry。

## 常用指令

| 指令 | 作用 |
|---|---|
| `poetry install` | 依 pyproject.toml / poetry.lock 安裝所有依賴（換機器時用） |
| `poetry add <套件>` | 新增依賴並更新鎖定檔 |
| `poetry run <指令>` | 在專案虛擬環境內執行指令 |
| `poetry run alembic upgrade head` | 把資料庫升級到最新結構 |
| `poetry run alembic revision --autogenerate -m "說明"` | 改了 models 後自動產生 migration |
| `poetry run python -m app.seed` | 灌入模擬資料（資料庫須為空） |

## 資料庫切換

預設用 SQLite（`backend/dev.db`），零安裝即可開發。
PostgreSQL 就緒後，建立 `backend/.env`：

```
DATABASE_URL=postgresql+psycopg://vtuber:vtuber@localhost:5432/vtuber_db
```

再跑一次 `poetry run alembic upgrade head` 與 `poetry run python -m app.seed` 即可。

## 結構

```
app/
  config.py   # 設定（讀 .env）
  db.py       # 資料庫連線與 Session
  models.py   # 15 張資料表定義（v2）
  seed.py     # 模擬資料產生器
migrations/   # Alembic 資料庫版本紀錄
```
