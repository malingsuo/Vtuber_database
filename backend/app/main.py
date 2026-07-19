from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import artists, events, item_types, products, vendors

app = FastAPI(
    title="VTuber 週邊管理系統",
    description="週邊商品的銷售紀錄、庫存管理與訂量預測",
    version="0.1.0",
)

# 前端（Vue dev server）跑在 5173 埠；上線部署時再收斂
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (artists.router, events.router, item_types.router,
               vendors.router, products.router):
    app.include_router(router, prefix="/api")


@app.get("/api/health", tags=["系統"])
def health() -> dict:
    return {"status": "ok"}
