from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.auth import decode_token
from app.db import SessionLocal
from app.deps import authorize
from app.models import AuditLog
from app.config import settings
from app.routers import (
    admin,
    artist_metrics,
    artists,
    auth_router,
    events,
    excel,
    expenses,
    forecast,
    inventory,
    item_types,
    preorders,
    products,
    quotes,
    reports,
    vendors,
)

app = FastAPI(
    title="VTuber 週邊管理系統",
    description="週邊商品的銷售紀錄、庫存管理與訂量預測",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def audit_log(request: Request, call_next):
    """操作紀錄 v1：所有成功的寫入操作記一筆（誰、何時、對哪個路徑做了什麼）。"""
    response = await call_next(request)
    if (
        request.method in ("POST", "PUT", "DELETE")
        and request.url.path.startswith("/api")
        and request.url.path != "/api/auth/login"  # 登入另外記
        and response.status_code < 400
    ):
        header = request.headers.get("Authorization", "")
        payload = decode_token(header.removeprefix("Bearer ")) if header.startswith("Bearer ") else None
        if payload:
            db = SessionLocal()
            try:
                db.add(
                    AuditLog(
                        company_id=payload["cid"],
                        user_id=int(payload["sub"]),
                        action=request.method,
                        table_name=request.url.path.removeprefix("/api/"),
                        detail={"status": response.status_code},
                    )
                )
                db.commit()
            finally:
                db.close()
    return response


# 登入路由不設權限；業務路由一律要登入，且唯讀角色擋寫入
app.include_router(auth_router.router, prefix="/api")
app.include_router(admin.router, prefix="/api")  # 內部自帶總管理員檢查
for router in (artists.router, events.router, item_types.router,
               vendors.router, products.router,
               inventory.router, preorders.router,
               expenses.router, reports.router, forecast.router,
               quotes.router, artist_metrics.router, excel.router):
    app.include_router(router, prefix="/api", dependencies=[Depends(authorize)])


@app.get("/api/health", tags=["系統"])
def health() -> dict:
    return {"status": "ok"}
