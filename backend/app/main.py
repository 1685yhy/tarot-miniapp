from contextlib import asynccontextmanager
import logging
import os

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.db.database import create_all
from app.config import settings
from app.api import auth, cards, chat, diary, membership, orders, readings, report, share, tasks, community, admin, notify
from app.api.ws import router as ws_router
from app.api.monitor import router as monitor_router
from app.middleware.metrics import MetricsMiddleware

logger = logging.getLogger(__name__)

# ---- Sentry initialization ----
try:
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            traces_sample_rate=0.1,
            environment="development" if settings.ENABLE_DEV_LOGIN else "production",
        )
        logger.info("Sentry SDK initialized")
    else:
        logger.info("Sentry DSN not set — skipping Sentry initialization")
except Exception:
    logger.exception("Failed to initialize Sentry SDK — continuing without it")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup guard: JWT_SECRET must not be placeholder in production ----
    if settings.JWT_SECRET in ("change-me-in-production", "") and not settings.ENABLE_DEV_LOGIN:
        import sys
        print(
            "FATAL: JWT_SECRET is still the insecure default "
            "'change-me-in-production' and ENABLE_DEV_LOGIN is False.\n"
            "The server refuses to start. Set a strong random JWT_SECRET in "
            "your .env file (e.g. via `openssl rand -hex 32`).\n"
            "If this is a development environment, set ENABLE_DEV_LOGIN=true "
            "in .env to bypass this guard (not for production!).",
            file=sys.stderr,
        )
        sys.exit(1)

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
app.include_router(tasks.router)
app.include_router(orders.router)
app.include_router(membership.router)
app.include_router(readings.router)
app.include_router(report.router)
app.include_router(share.router)
app.include_router(community.router)
app.include_router(notify.router)
app.include_router(monitor_router)
app.include_router(admin.router)
app.include_router(ws_router)

# Admin static files (mount before dev-assets so /static doesn't conflict)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Metrics middleware — must be added after routers so path patterns are resolved
app.add_middleware(MetricsMiddleware)


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


# Develop mode: serve card images from local filesystem
CARDS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dev-assets", "cards_thumb")
if os.path.isdir(CARDS_DIR):
    app.mount("/images/cards", StaticFiles(directory=CARDS_DIR), name="cards")
CARDS_FULL = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dev-assets", "cards_v3")
if os.path.isdir(CARDS_FULL):
    app.mount("/images/cards_full", StaticFiles(directory=CARDS_FULL), name="cards_full")
ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "miniapp", "images", "icons")
if os.path.isdir(ICONS_DIR):
    app.mount("/images/icons", StaticFiles(directory=ICONS_DIR), name="icons")
