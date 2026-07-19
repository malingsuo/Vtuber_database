#!/bin/sh
# 每次啟動先把資料庫升到最新結構，再開伺服器
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
