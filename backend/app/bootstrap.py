"""正式環境初始化：建立平台總部與總管理員帳號（只在空資料庫執行）。

用法（在雲端主機上）：
    docker compose exec backend python -m app.bootstrap
會用環境變數 SUPERADMIN_PASSWORD 當密碼；沒設就用參數或報錯。
"""

import os
import sys

from sqlalchemy import func, select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import Company, User, UserRole


def main() -> None:
    password = os.environ.get("SUPERADMIN_PASSWORD") or (
        sys.argv[1] if len(sys.argv) > 1 else None
    )
    if not password or len(password) < 8:
        raise SystemExit(
            "請提供至少 8 碼的總管理員密碼："
            "設環境變數 SUPERADMIN_PASSWORD，或 python -m app.bootstrap <密碼>"
        )

    session = SessionLocal()
    if session.scalar(select(func.count()).select_from(Company)):
        raise SystemExit("資料庫已有資料，略過初始化（此工具只在全新環境使用）")

    platform = Company(name="平台總部")
    session.add(platform)
    session.flush()
    session.add(
        User(
            company_id=platform.id,
            username="superadmin",
            password_hash=hash_password(password),
            display_name="總管理員",
            role=UserRole.SUPERADMIN.value,
        )
    )
    session.commit()
    print("初始化完成：帳號 superadmin。登入後到「設定 → 公司管理」開通第一家公司。")


if __name__ == "__main__":
    main()
