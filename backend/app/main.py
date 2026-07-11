from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import create_all
from app.config import settings
from app.api import auth, cards, chat, diary, membership, orders, readings, report, share


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all()
    yield


app = FastAPI(title="塔罗占卜 API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(chat.router)
app.include_router(diary.router)
app.include_router(orders.router)
app.include_router(membership.router)
app.include_router(readings.router)
app.include_router(report.router)
app.include_router(share.router)


@app.get("/health")
async def health():
    # ---- 配置自检 ----
    cfg = settings
    deepseek_status = "ok" if cfg.DEEPSEEK_API_KEY and not cfg.DEEPSEEK_API_KEY.startswith("sk-your") else "missing"
    wechat_status = "ok" if cfg.WECHAT_APP_ID and "your" not in cfg.WECHAT_APP_ID else "missing"
    jwt_secret_raw = cfg.JWT_SECRET.replace("change-me-in-production", "")
    jwt_status = "ok" if len(jwt_secret_raw) >= 32 else ("weak" if jwt_secret_raw else "missing")

    return {
        "status": "ok",
        "service": "塔罗占卜 API",
        "version": "1.0.0",
        "config_status": {
            "deepseek": deepseek_status,
            "wechat": wechat_status,
            "jwt": jwt_status,
        },
    }
