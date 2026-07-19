"""登入限流（交接文件漏洞 C）：每 IP 每分鐘 5 次，防暴力猜密碼。"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded


def client_ip(request: Request) -> str:
    # 正式部署在 nginx 後面，真實 IP 在 X-Real-IP（nginx.conf 已設定）
    return request.headers.get("X-Real-IP") or (
        request.client.host if request.client else "unknown"
    )


limiter = Limiter(key_func=client_ip)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "嘗試次數過多，請一分鐘後再試"},
    )
