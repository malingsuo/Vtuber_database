"""密碼雜湊與 JWT 權杖：登入系統的核心工具。"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings
from app.models import User

ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        # 舊格式（非 bcrypt）的雜湊一律視為不符
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "cid": user.company_id,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.token_expire_hours),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
