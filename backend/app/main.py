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
    return {"status": "ok"}
