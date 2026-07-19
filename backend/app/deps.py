from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db import SessionLocal

# 本機單公司版：所有資料都掛在種子資料建立的第一家公司底下。
# 多公司版上線時，改成從登入使用者身上取得。
DEFAULT_COMPANY_ID = 1


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_company_id() -> int:
    return DEFAULT_COMPANY_ID
