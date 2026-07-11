# 塔罗占卜微信小程序 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建完整的塔罗占卜微信小程序商业版，包含AI解读引擎、付费会员系统、分享裂变等完整功能

**Architecture:** 微信小程序前端 + Python FastAPI后端 + Claude API AI引擎 + MySQL数据库 + Redis缓存，部署在云服务器

**Tech Stack:** 微信小程序原生框架, Python 3.11+, FastAPI, Claude API, MySQL 8.0, Redis, SQLAlchemy, Pydantic, 微信支付API v3

## Global Constraints

- 所有用户交互文本必须为中文
- 微信小程序包体积 ≤ 2MB（主包）+ 分包
- API响应时间 ≤ 3秒（含AI解读）
- 支持微信一键登录（wx.login）
- 支付走微信支付官方SDK
- 塔罗数据从 E:\tarot-miniapp\data\ 导入数据库
- 项目路径: /mnt/e/tarot-miniapp/

---

## 项目文件结构

```
/mnt/e/tarot-miniapp/
├── backend/                     # Python FastAPI 后端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI入口, CORS, 路由注册
│   │   ├── config.py            # 环境配置(Settings pydantic)
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py          # POST /auth/login (wx.login)
│   │   │   ├── cards.py         # GET /cards, GET /cards/{id}, GET /cards/search
│   │   │   ├── readings.py      # POST /readings/daily, POST /readings/spread/{type}
│   │   │   ├── chat.py          # POST /readings/{id}/chat (AI追问)
│   │   │   ├── orders.py        # POST /orders, POST /orders/callback (微信支付)
│   │   │   ├── membership.py    # GET /membership/status, POST /membership/purchase
│   │   │   ├── diary.py         # CRUD /diary/entries
│   │   │   ├── report.py        # GET /report/annual
│   │   │   └── share.py         # POST /share/track
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py          # User, UserMembership
│   │   │   ├── card.py          # TarotCard (78条记录)
│   │   │   ├── reading.py       # Reading, DrawnCard
│   │   │   ├── order.py         # Order, PaymentRecord
│   │   │   └── diary.py         # DiaryEntry
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── card.py
│   │   │   ├── reading.py
│   │   │   ├── order.py
│   │   │   └── diary.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── ai_engine.py     # Claude API 塔罗解读引擎
│   │   │   ├── tarot.py         # 洗牌、抽牌、牌阵逻辑
│   │   │   ├── payment.py       # 微信支付v3
│   │   │   └── share.py         # 分享裂变追踪
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── database.py      # SQLAlchemy async engine + session
│   │   │   └── seed.py          # 从markdown文件导入78张牌
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── auth.py          # JWT token 生成/验证
│   ├── alembic/                 # 数据库迁移
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_cards.py
│   │   ├── test_readings.py
│   │   ├── test_ai_engine.py
│   │   └── test_payment.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── docker-compose.yml       # MySQL + Redis + App
│
├── miniapp/                     # 微信小程序前端
│   ├── app.js
│   ├── app.json
│   ├── app.wxss
│   ├── project.config.json
│   ├── pages/
│   │   ├── index/               # 首页(每日运势)
│   │   ├── encyclopedia/        # 塔罗百科(牌列表)
│   │   ├── card-detail/         # 单张牌详情
│   │   ├── reading/             # 选择牌阵+洗牌抽牌
│   │   ├── reading-result/      # 抽牌结果+AI解读
│   │   ├── chat/                # AI追问对话
│   │   ├── membership/          # 会员购买页
│   │   ├── profile/             # 个人中心
│   │   ├── diary/               # 塔罗日记
│   │   └── annual-report/       # 年度运势报告
│   ├── components/
│   │   ├── card-flip/           # 翻牌动画组件
│   │   ├── reading-display/     # 解读结果展示组件
│   │   └── pay-modal/           # 支付弹窗组件
│   ├── utils/
│   │   ├── api.js               # 统一API请求封装
│   │   ├── auth.js              # 微信登录管理
│   │   └── storage.js           # 本地存储管理
│   └── styles/
│       └── common.wxss          # 全局样式变量
│
├── data/                        # 已搜集的塔罗数据(已完成)
│   ├── major-arcana.md
│   ├── wands-suit.md
│   ├── cups-suit.md
│   ├── swords-suit.md
│   ├── pentacles-suit.md
│   ├── tarot-spreads.md
│   └── tarot-case-studies.md
│
└── docs/
    └── superpowers/
        ├── specs/2026-07-11-tarot-miniapp-design.md
        └── plans/2026-07-11-tarot-miniapp-plan.md
```

---

## Phase 1: 后端基础架构

### Task 1: 项目骨架 + 配置

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/database.py`

**Interfaces:**
- Produces: `Settings` class (pydantic), `get_db()` async generator, `create_all()` function

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.35
asyncmy==0.2.9
redis==5.1.0
pydantic==2.9.0
pydantic-settings==2.5.0
python-jose[cryptography]==3.3.0
httpx==0.27.0
anthropic==0.34.0
alembic==1.13.0
wechatpayv3==0.4.0
pytest==8.3.0
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Create config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "mysql+asyncmy://tarot:tarot123@localhost:3306/tarot_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Claude API
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # WeChat
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""
    WECHAT_MCH_ID: str = ""
    WECHAT_API_KEY_V3: str = ""

    # Auth
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days

    # Limits
    FREE_DAILY_READINGS: int = 1
    FREE_CHAT_MESSAGES: int = 3

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 3: Create database.py**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=20)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def create_all():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 4: Create main.py**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import create_all
from app.config import settings

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

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run and verify**

```bash
cd /mnt/e/tarot-miniapp/backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# Test: curl http://localhost:8000/health → {"status":"ok"}
```

- [ ] **Step 6: Create docker-compose.yml for MySQL + Redis**

```yaml
version: '3.8'
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root123
      MYSQL_DATABASE: tarot_db
      MYSQL_USER: tarot
      MYSQL_PASSWORD: tarot123
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  mysql_data:
```

---

### Task 2: 数据模型（SQLAlchemy Models）

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/card.py`
- Create: `backend/app/models/reading.py`
- Create: `backend/app/models/order.py`
- Create: `backend/app/models/diary.py`

**Interfaces:**
- Consumes: `Base` from `app.db.database`
- Produces: `User`, `TarotCard`, `Reading`, `DrawnCard`, `Order`, `DiaryEntry` models

- [ ] **Step 1: Create user.py**

```python
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    openid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    unionid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_member: Mapped[bool] = mapped_column(Boolean, default=False)
    member_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    free_readings_today: Mapped[int] = mapped_column(Integer, default=0)
    free_chats_today: Mapped[int] = mapped_column(Integer, default=0)
    last_reading_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    readings: Mapped[list["Reading"]] = relationship(back_populates="user")
    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    diary_entries: Mapped[list["DiaryEntry"]] = relationship(back_populates="user")
```

- [ ] **Step 2: Create card.py**

```python
from sqlalchemy import String, Text, Boolean, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class TarotCard(Base):
    __tablename__ = "tarot_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_zh: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name_en: Mapped[str] = mapped_column(String(64), nullable=False)
    card_number: Mapped[int] = mapped_column(Integer, nullable=False)
    arcana: Mapped[str] = mapped_column(String(16), nullable=False)  # 'major' or 'minor'
    suit: Mapped[str | None] = mapped_column(String(16), nullable=True)  # wands/cups/swords/pentacles
    element: Mapped[str | None] = mapped_column(String(8), nullable=True)
    image_description: Mapped[str] = mapped_column(Text, nullable=False)
    keywords_upright: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array string
    keywords_reversed: Mapped[str] = mapped_column(Text, nullable=False)
    meaning_upright: Mapped[str] = mapped_column(Text, nullable=False)
    meaning_reversed: Mapped[str] = mapped_column(Text, nullable=False)
    love_upright: Mapped[str] = mapped_column(Text, nullable=False)
    love_reversed: Mapped[str] = mapped_column(Text, nullable=False)
    career_upright: Mapped[str] = mapped_column(Text, nullable=False)
    career_reversed: Mapped[str] = mapped_column(Text, nullable=False)
    finance_upright: Mapped[str] = mapped_column(Text, nullable=False)
    finance_reversed: Mapped[str] = mapped_column(Text, nullable=False)
    health_upright: Mapped[str] = mapped_column(Text, nullable=False)
    health_reversed: Mapped[str] = mapped_column(Text, nullable=False)
```

- [ ] **Step 3: Create reading.py**

```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base

class Reading(Base):
    __tablename__ = "readings"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    spread_type: Mapped[str] = mapped_column(String(32), nullable=False)  # daily/triangle/celtic_cross/etc
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    theme: Mapped[str | None] = mapped_column(String(16), nullable=True)  # love/career/finance/general
    interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="readings")
    drawn_cards: Mapped[list["DrawnCard"]] = relationship(back_populates="reading", cascade="all, delete-orphan")
    chat_messages: Mapped[list["ChatMessage"]] = relationship(back_populates="reading", cascade="all, delete-orphan")

class DrawnCard(Base):
    __tablename__ = "drawn_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("readings.id"), nullable=False)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey("tarot_cards.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # 牌阵中的位置
    position_name: Mapped[str] = mapped_column(String(32), nullable=False)
    is_reversed: Mapped[bool] = mapped_column(Boolean, default=False)

    reading: Mapped["Reading"] = relationship(back_populates="drawn_cards")
    card: Mapped["TarotCard"] = relationship()

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("readings.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    reading: Mapped["Reading"] = relationship(back_populates="chat_messages")
```

- [ ] **Step 4: Create order.py**

```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, ForeignKey, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # 微信支付订单号
    product_type: Mapped[str] = mapped_column(String(32), nullable=False)  # single_reading/membership/annual_report
    amount: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/paid/refunded/cancelled
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="orders")
```

- [ ] **Step 5: Create diary.py**

```python
import uuid
from datetime import datetime, date
from sqlalchemy import String, DateTime, Integer, Text, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base

class DiaryEntry(Base):
    __tablename__ = "diary_entries"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    mood: Mapped[str | None] = mapped_column(String(16), nullable=True)
    card_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tarot_cards.id"), nullable=True)
    reflection: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="diary_entries")
    card: Mapped["TarotCard"] = relationship()
```

- [ ] **Step 6: Create models/__init__.py**

```python
from app.models.user import User
from app.models.card import TarotCard
from app.models.reading import Reading, DrawnCard, ChatMessage
from app.models.order import Order
from app.models.diary import DiaryEntry

__all__ = ["User", "TarotCard", "Reading", "DrawnCard", "ChatMessage", "Order", "DiaryEntry"]
```

- [ ] **Step 7: Commit**

---

### Task 3: 塔罗数据导入脚本

**Files:**
- Create: `backend/app/db/seed.py`
- Create: `backend/scripts/import_cards.py`

**Interfaces:**
- Consumes: data/*.md files, TarotCard model, database session
- Produces: 78 rows in tarot_cards table

- [ ] **Step 1: Create seed.py with structured card import logic**

```python
"""从 markdown 数据文件解析并导入78张塔罗牌到数据库"""
import re
import asyncio
from sqlalchemy import select
from app.db.database import async_session
from app.models.card import TarotCard

# 每张牌的解析函数
def parse_card_section(text: str) -> dict:
    """从markdown文本中解析单张牌的字段"""
    data = {}

    # 解析名称
    name_match = re.search(r'##\s*\d+\.\s*(.+?)(?:（|\().*?(?:The\s+)?([A-Za-z\s]+)', text)
    if name_match:
        data['name_zh'] = name_match.group(1).strip()
        data['name_en'] = name_match.group(2).strip()

    # 辅助函数：提取字段取值（匹配"**字段名**：值"或"**字段名**：\n值"格式）
    def extract_field(field_name: str) -> str | None:
        # 单行格式: **字段名**：值
        single = re.search(rf'\*\*{field_name}\*\*[：:]\s*(.+?)(?:\n|$)', text)
        if single:
            return single.group(1).strip()
        # 多行格式: **字段名**：\n值（到下一个**字段**或###为止）
        multi = re.search(rf'\*\*{field_name}\*\*[：:]\s*\n(.+?)(?:\n\*\*|\n###|\Z)', text, re.DOTALL)
        if multi:
            return multi.group(1).strip()
        return None

    # 基本信息
    data['element'] = extract_field('元素') or ''
    data['image_description'] = extract_field('牌面描述') or ''

    # 关键词
    kw_upright = extract_field('关键词')
    data['keywords_upright'] = kw_upright or ''

    # 使用备用方式匹配含有"正位"/"逆位"标记的字段
    data['meaning_upright'] = extract_field('正位牌义') or extract_field('正位含义') or ''
    data['meaning_reversed'] = extract_field('逆位牌义') or extract_field('逆位含义') or ''
    data['love_upright'] = extract_field('感情正位') or ''
    data['love_reversed'] = extract_field('感情逆位') or ''
    data['career_upright'] = extract_field('事业正位') or ''
    data['career_reversed'] = extract_field('事业逆位') or ''
    data['finance_upright'] = extract_field('财运正位') or ''
    data['finance_reversed'] = extract_field('财运逆位') or ''
    data['health_upright'] = extract_field('健康正位') or ''
    data['health_reversed'] = extract_field('健康逆位') or ''

    return data

async def seed_cards():
    """从markdown文件导入所有塔罗牌数据"""
    import os
    from pathlib import Path

    data_dir = Path("/mnt/e/tarot-miniapp/data")
    card_counter = 0

    async with async_session() as session:
        # Check if already seeded
        result = await session.execute(select(TarotCard).limit(1))
        if result.scalar_one_or_none():
            print("塔罗牌数据已存在, 跳过导入")
            return

        # Major Arcana (0-21)
        major_path = data_dir / "major-arcana.md"
        if major_path.exists():
            text = major_path.read_text(encoding='utf-8')
            sections = re.split(r'\n## \d+\.', text)
            for i, section in enumerate(sections[1:], 0):
                section = "## " + section
                card_data = parse_card_section(section)
                card = TarotCard(
                    name_zh=card_data.get('name_zh', ''),
                    name_en=card_data.get('name_en', ''),
                    card_number=i,
                    arcana='major',
                    suit=None,
                    element=card_data.get('element', ''),
                    image_description=card_data.get('image_description', ''),
                    keywords_upright=card_data.get('keywords_upright', ''),
                    keywords_reversed='',
                    meaning_upright=card_data.get('meaning_upright', ''),
                    meaning_reversed=card_data.get('meaning_reversed', ''),
                    love_upright=card_data.get('love_upright', ''),
                    love_reversed=card_data.get('love_reversed', ''),
                    career_upright=card_data.get('career_upright', ''),
                    career_reversed=card_data.get('career_reversed', ''),
                    finance_upright=card_data.get('finance_upright', ''),
                    finance_reversed=card_data.get('finance_reversed', ''),
                    health_upright=card_data.get('health_upright', ''),
                    health_reversed=card_data.get('health_reversed', ''),
                )
                session.add(card)
                card_counter += 1

        # Minor Arcana suits
        suits = [
            ('wands', 'wands-suit.md', '权杖', '火', 22),
            ('cups', 'cups-suit.md', '圣杯', '水', 36),
            ('swords', 'swords-suit.md', '宝剑', '风', 50),
            ('pentacles', 'pentacles-suit.md', '星币', '土', 64),
        ]

        for suit_name, filename, suit_zh, element, start_num in suits:
            path = data_dir / filename
            if not path.exists():
                continue
            text = path.read_text(encoding='utf-8')
            sections = re.split(r'\n##\s+', text)
            num = 0
            for section in sections:
                if not section.strip():
                    continue
                section = "## " + section
                card_data = parse_card_section(section)
                if not card_data.get('name_zh'):
                    continue

                # Determine card number within suit (Ace=1, 2-10, Page=11, Knight=12, Queen=13, King=14)
                # Map from the card's actual number embedded in the section
                num += 1

                card = TarotCard(
                    name_zh=card_data.get('name_zh', ''),
                    name_en=card_data.get('name_en', ''),
                    card_number=start_num + num - 1,
                    arcana='minor',
                    suit=suit_name,
                    element=element,
                    image_description=card_data.get('image_description', ''),
                    keywords_upright=card_data.get('keywords_upright', ''),
                    keywords_reversed='',
                    meaning_upright=card_data.get('meaning_upright', ''),
                    meaning_reversed=card_data.get('meaning_reversed', ''),
                    love_upright=card_data.get('love_upright', ''),
                    love_reversed=card_data.get('love_reversed', ''),
                    career_upright=card_data.get('career_upright', ''),
                    career_reversed=card_data.get('career_reversed', ''),
                    finance_upright=card_data.get('finance_upright', ''),
                    finance_reversed=card_data.get('finance_reversed', ''),
                    health_upright=card_data.get('health_upright', ''),
                    health_reversed=card_data.get('health_reversed', ''),
                )
                session.add(card)
                card_counter += 1

        await session.commit()
        print(f"成功导入 {card_counter} 张塔罗牌")

if __name__ == "__main__":
    asyncio.run(seed_cards())
```

- [ ] **Step 2: Run import script**

```bash
cd /mnt/e/tarot-miniapp/backend
python -m app.db.seed
# Expected: 成功导入 78 张塔罗牌
```

- [ ] **Step 3: Verify by querying database**

```bash
mysql -u tarot -p tarot_db -e "SELECT id, name_zh, arcana, suit FROM tarot_cards ORDER BY card_number;"
# Expected: 78 rows, 22 major + 56 minor
```

- [ ] **Step 4: Commit**

---

### Task 4: 用户认证 API

**Files:**
- Create: `backend/app/utils/__init__.py`
- Create: `backend/app/utils/auth.py`
- Create: `backend/app/schemas/user.py`
- Create: `backend/app/api/auth.py`

**Interfaces:**
- Consumes: `User` model, `settings`, `get_db()`
- Produces: `POST /auth/login` → `{token, user}`, `get_current_user()` dependency

- [ ] **Step 1: Create utils/auth.py**

```python
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.user import User

def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire, "iat": datetime.utcnow()}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的登录凭证")

async def get_current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
) -> User:
    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
```

- [ ] **Step 2: Create schemas/user.py**

```python
from pydantic import BaseModel
from datetime import datetime

class UserLoginRequest(BaseModel):
    code: str  # 微信 wx.login() 返回的 code

class UserResponse(BaseModel):
    id: str
    nickname: str | None
    avatar_url: str | None
    is_member: bool
    member_expires_at: datetime | None
    free_readings_today: int
    free_chats_today: int

    class Config:
        from_attributes = True

class LoginResponse(BaseModel):
    token: str
    user: UserResponse
```

- [ ] **Step 3: Create api/auth.py**

```python
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserLoginRequest, LoginResponse, UserResponse
from app.utils.auth import create_token

router = APIRouter(prefix="/auth", tags=["认证"])

@router.post("/login", response_model=LoginResponse)
async def wx_login(req: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    # 调用微信接口换取 openid
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={
                "appid": settings.WECHAT_APP_ID,
                "secret": settings.WECHAT_APP_SECRET,
                "js_code": req.code,
                "grant_type": "authorization_code",
            }
        )
        wx_data = resp.json()

    openid = wx_data.get("openid")
    if not openid:
        raise HTTPException(status_code=400, detail=f"微信登录失败: {wx_data}")

    # 查找或创建用户
    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    if not user:
        user = User(openid=openid, unionid=wx_data.get("unionid"))
        db.add(user)
        await db.flush()

    token = create_token(user.id)
    return LoginResponse(token=token, user=UserResponse.model_validate(user))
```

- [ ] **Step 4: Register route in main.py** (update main.py)

```python
# Add to main.py after middleware setup:
from app.api import auth

app.include_router(auth.router)
```

- [ ] **Step 5: Test**

```bash
# 需要真实的微信小程序code来测试，开发阶段先mock
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"code": "test_mock_code"}'
# Expected: 400 (微信会返回错误), 但验证api工作正常
```

- [ ] **Step 6: Commit**

---

## Phase 2: 塔罗百科API + 前端页面

### Task 5: 塔罗牌查询API

**Files:**
- Create: `backend/app/schemas/card.py`
- Create: `backend/app/api/cards.py`

**Interfaces:**
- Consumes: `TarotCard` model, `get_db()`
- Produces: `GET /cards` (list+filter), `GET /cards/{id}`, `GET /cards/random` (每日一牌)

- [ ] **Step 1: Create schemas/card.py**

```python
from pydantic import BaseModel

class CardBrief(BaseModel):
    id: int
    name_zh: str
    name_en: str
    card_number: int
    arcana: str
    suit: str | None
    element: str | None

    class Config:
        from_attributes = True

class CardDetail(CardBrief):
    image_description: str
    keywords_upright: str
    keywords_reversed: str
    meaning_upright: str
    meaning_reversed: str
    love_upright: str
    love_reversed: str
    career_upright: str
    career_reversed: str
    finance_upright: str
    finance_reversed: str
    health_upright: str
    health_reversed: str

class CardListResponse(BaseModel):
    total: int
    cards: list[CardBrief]
```

- [ ] **Step 2: Create api/cards.py**

```python
import random
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.card import TarotCard
from app.schemas.card import CardBrief, CardDetail, CardListResponse

router = APIRouter(prefix="/cards", tags=["塔罗百科"])

@router.get("", response_model=CardListResponse)
async def list_cards(
    arcana: str | None = Query(None, description="major 或 minor"),
    suit: str | None = Query(None, description="wands/cups/swords/pentacles"),
    keyword: str | None = Query(None, description="搜索关键词"),
    db: AsyncSession = Depends(get_db),
):
    query = select(TarotCard)
    if arcana:
        query = query.where(TarotCard.arcana == arcana)
    if suit:
        query = query.where(TarotCard.suit == suit)
    if keyword:
        query = query.where(
            (TarotCard.name_zh.contains(keyword)) |
            (TarotCard.name_en.contains(keyword)) |
            (TarotCard.meaning_upright.contains(keyword))
        )

    result = await db.execute(query.order_by(TarotCard.card_number))
    cards = result.scalars().all()
    return CardListResponse(total=len(cards), cards=[CardBrief.model_validate(c) for c in cards])

@router.get("/daily", response_model=CardDetail)
async def daily_card(db: AsyncSession = Depends(get_db)):
    """每日一牌 - 随机抽取一张"""
    result = await db.execute(select(func.count(TarotCard.id)))
    count = result.scalar()
    random_id = random.randint(1, count)
    result = await db.execute(select(TarotCard).where(TarotCard.id == random_id))
    card = result.scalar_one()
    return CardDetail.model_validate(card)

@router.get("/{card_id}", response_model=CardDetail)
async def get_card(card_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TarotCard).where(TarotCard.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="卡牌不存在")
    return CardDetail.model_validate(card)
```

- [ ] **Step 3: Register route in main.py**

```python
from app.api import cards
app.include_router(cards.router)
```

- [ ] **Step 4: Test**

```bash
curl http://localhost:8000/cards?arcana=major | python -m json.tool | head -20
curl http://localhost:8000/cards/daily | python -m json.tool | head -30
curl http://localhost:8000/cards/1 | python -m json.tool | head -30
```

- [ ] **Step 5: Commit**

---

### Task 6: 微信小程序基础框架 + 首页

**Files:**
- Create: `miniapp/app.js`
- Create: `miniapp/app.json`
- Create: `miniapp/app.wxss`
- Create: `miniapp/project.config.json`
- Create: `miniapp/utils/api.js`
- Create: `miniapp/utils/auth.js`
- Create: `miniapp/utils/storage.js`
- Create: `miniapp/pages/index/index.js`
- Create: `miniapp/pages/index/index.wxml`
- Create: `miniapp/pages/index/index.wxss`
- Create: `miniapp/pages/index/index.json`
- Create: `miniapp/styles/common.wxss`

- [ ] **Step 1: Create app.json**

```json
{
  "pages": [
    "pages/index/index",
    "pages/encyclopedia/encyclopedia",
    "pages/card-detail/card-detail",
    "pages/reading/reading",
    "pages/reading-result/reading-result",
    "pages/chat/chat",
    "pages/membership/membership",
    "pages/profile/profile",
    "pages/diary/diary",
    "pages/annual-report/annual-report"
  ],
  "window": {
    "backgroundTextStyle": "dark",
    "navigationBarBackgroundColor": "#1a1a2e",
    "navigationBarTitleText": "塔罗占卜",
    "navigationBarTextStyle": "white",
    "backgroundColor": "#0f0f23"
  },
  "tabBar": {
    "color": "#8888aa",
    "selectedColor": "#c9a96e",
    "backgroundColor": "#1a1a2e",
    "borderStyle": "black",
    "list": [
      {
        "pagePath": "pages/index/index",
        "text": "占卜",
        "iconPath": "images/tab-divine.png",
        "selectedIconPath": "images/tab-divine-active.png"
      },
      {
        "pagePath": "pages/encyclopedia/encyclopedia",
        "text": "百科",
        "iconPath": "images/tab-book.png",
        "selectedIconPath": "images/tab-book-active.png"
      },
      {
        "pagePath": "pages/profile/profile",
        "text": "我的",
        "iconPath": "images/tab-profile.png",
        "selectedIconPath": "images/tab-profile-active.png"
      }
    ]
  },
  "style": "v2",
  "sitemapLocation": "sitemap.json"
}
```

- [ ] **Step 2: Create utils/api.js**

```javascript
const BASE_URL = 'https://your-domain.com'; // 部署时替换

const request = async (url, options = {}) => {
  const token = wx.getStorageSync('token');

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}${url}`,
      method: options.method || 'GET',
      data: options.data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
        ...options.header,
      },
      success: (res) => {
        if (res.statusCode === 401) {
          wx.removeStorageSync('token');
          wx.reLaunch({ url: '/pages/index/index' });
          reject(new Error('登录过期'));
        } else if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(new Error(res.data?.detail || '请求失败'));
        }
      },
      fail: reject,
    });
  });
};

module.exports = { request, BASE_URL };
```

- [ ] **Step 3: Create utils/auth.js**

```javascript
const { request } = require('./api');

const login = async () => {
  return new Promise((resolve, reject) => {
    wx.login({
      success: async (res) => {
        try {
          const data = await request('/auth/login', {
            method: 'POST',
            data: { code: res.code },
          });
          wx.setStorageSync('token', data.token);
          wx.setStorageSync('user', data.user);
          resolve(data.user);
        } catch (err) {
          reject(err);
        }
      },
      fail: reject,
    });
  });
};

const checkLogin = async () => {
  const token = wx.getStorageSync('token');
  if (!token) {
    return await login();
  }
  return wx.getStorageSync('user');
};

module.exports = { login, checkLogin };
```

- [ ] **Step 4: Create app.js**

```javascript
const { checkLogin } = require('./utils/auth');

App({
  onLaunch() {
    checkLogin().catch(() => {
      console.log('登录将在首次API请求时触发');
    });
  },

  globalData: {
    user: null,
    dailyCard: null,
  },
});
```

- [ ] **Step 5: Create common.wxss** (全局样式变量)

```css
/* 塔罗主题色系 */
page {
  --color-bg: #0f0f23;
  --color-bg-card: #1a1a2e;
  --color-gold: #c9a96e;
  --color-gold-light: #e0c78a;
  --color-purple: #7b68ee;
  --color-purple-dark: #4a3f8a;
  --color-text-primary: #e8e8f0;
  --color-text-secondary: #8888aa;
  --color-text-dim: #555577;

  background-color: var(--color-bg);
  color: var(--color-text-primary);
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
}
```

- [ ] **Step 6: Create index page (每日运势首页)**

```html
<!-- pages/index/index.wxml -->
<view class="container">
  <!-- 顶部神秘学氛围区 -->
  <view class="hero">
    <view class="mystic-circle">
      <view class="star-field">
        <text class="star">✦</text>
        <text class="moon">☽</text>
      </view>
    </view>
    <text class="hero-title">塔罗占卜</text>
    <text class="hero-subtitle">揭开命运的面纱</text>
  </view>

  <!-- 每日一牌 -->
  <view class="daily-card" bindtap="drawDailyCard">
    <view class="card-back" wx:if="{{!dailyCard}}">
      <text class="card-back-text">点击抽取今日运势</text>
      <text class="card-back-hint">{{freeCount}}/1 次免费</text>
    </view>
    <view class="card-result" wx:else>
      <text class="card-name">{{dailyCard.name_zh}}</text>
      <text class="card-keywords">{{dailyCard.keywords_upright}}</text>
    </view>
  </view>

  <!-- 牌阵入口 -->
  <view class="spread-section">
    <text class="section-title">选择牌阵</text>
    <view class="spread-grid">
      <view class="spread-item" bindtap="navigateToReading" data-type="triangle">
        <text class="spread-icon">💕</text>
        <text class="spread-name">恋人三角</text>
        <text class="spread-badge">热门</text>
      </view>
      <view class="spread-item" bindtap="navigateToReading" data-type="celtic_cross">
        <text class="spread-icon">✝️</text>
        <text class="spread-name">凯尔特十字</text>
        <text class="spread-desc">最全面</text>
      </view>
      <view class="spread-item" bindtap="navigateToReading" data-type="three_card">
        <text class="spread-icon">🕯️</text>
        <text class="spread-name">三牌占卜</text>
        <text class="spread-desc">过去·现在·未来</text>
      </view>
      <view class="spread-item" bindtap="navigateToReading" data-type="career">
        <text class="spread-icon">💼</text>
        <text class="spread-name">事业牌阵</text>
      </view>
      <view class="spread-item" bindtap="navigateToReading" data-type="finance">
        <text class="spread-icon">💰</text>
        <text class="spread-name">财运牌阵</text>
      </view>
      <view class="spread-item" bindtap="navigateToReading" data-type="decision">
        <text class="spread-icon">🔀</text>
        <text class="spread-name">二择一</text>
      </view>
    </view>
  </view>
</view>
```

```javascript
// pages/index/index.js
const { request } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

Page({
  data: {
    dailyCard: null,
    freeCount: 0,
    user: null,
  },

  async onLoad() {
    const user = await checkLogin();
    this.setData({ user, freeCount: user?.free_readings_today || 0 });
  },

  async drawDailyCard() {
    if (this.data.freeCount >= 1 && !this.data.user?.is_member) {
      wx.showToast({ title: '今日免费次数已用完', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '抽取中...' });
    try {
      const card = await request('/cards/daily');
      this.setData({ dailyCard: card, freeCount: this.data.freeCount + 1 });
      wx.hideLoading();
      // 保存到globalData供详情页使用
      getApp().globalData.dailyCard = card;
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: '抽取失败，请重试', icon: 'none' });
    }
  },

  navigateToReading(e) {
    const type = e.currentTarget.dataset.type;
    if (!this.data.user?.is_member) {
      wx.navigateTo({ url: `/pages/membership/membership?from=reading` });
      return;
    }
    wx.navigateTo({ url: `/pages/reading/reading?type=${type}` });
  },
});
```

- [ ] **Step 7: Commit**

---

## Phase 3: 核心占卜引擎

### Task 7: 塔罗占卜API（抽牌+AI解读）

**Files:**
- Create: `backend/app/services/tarot.py`
- Create: `backend/app/services/ai_engine.py`
- Create: `backend/app/schemas/reading.py`
- Create: `backend/app/api/readings.py`

**Interfaces:**
- Consumes: `TarotCard`, `Reading`, `DrawnCard` models, `get_db()`, `get_current_user()`, `settings`
- Produces: `POST /readings/spread/{type}` (创建解读), `GET /readings/{id}` (获取解读), `GET /readings/history` (历史记录)

- [ ] **Step 1: Create services/tarot.py**

```python
import random
from typing import Tuple

def draw_cards(
    spread_type: str,
    exclude_card_ids: list[int] | None = None
) -> list[dict]:
    """
    根据牌阵类型抽牌，返回 {card_id, position, position_name, is_reversed}
    """
    spread_configs = {
        "daily": {"count": 1, "positions": ["今日运势"]},
        "three_card": {"count": 3, "positions": ["过去", "现在", "未来"]},
        "triangle": {"count": 4, "positions": ["你的状态", "对方状态", "关系现状", "未来发展"]},
        "career": {"count": 5, "positions": ["当前位置", "挑战", "建议", "机遇", "可能结果"]},
        "finance": {"count": 4, "positions": ["财务现状", "收入来源", "支出模式", "财务建议"]},
        "decision": {"count": 5, "positions": ["现状", "选择A", "选择A结果", "选择B", "选择B结果"]},
        "celtic_cross": {
            "count": 10,
            "positions": [
                "核心问题", "阻碍", "过去基础", "近期未来",
                "显意识目标", "潜意识", "建议", "环境影响",
                "希望与恐惧", "最终结果"
            ]
        },
        "life_cross": {"count": 5, "positions": ["你(现在)", "过去", "未来", "助力", "阻力"]},
        "horseshoe": {"count": 7, "positions": ["过去", "现在", "隐藏影响", "障碍", "环境", "建议", "结果"]},
        "year_ahead": {
            "count": 13,
            "positions": [
                "年度主题", "一月", "二月", "三月", "四月",
                "五月", "六月", "七月", "八月", "九月",
                "十月", "十一月", "十二月"
            ]
        },
        "relationship": {"count": 7, "positions": ["你", "对方", "你们的连接", "优势", "挑战", "对方视角", "建议"]},
    }

    config = spread_configs.get(spread_type, {"count": 3, "positions": ["过去", "现在", "未来"]})
    count = config["count"]
    positions = config["positions"]

    # 从78张牌中随机选择（排除已选的）
    available = [i for i in range(1, 79) if i not in (exclude_card_ids or [])]
    selected = random.sample(available, min(count, len(available)))

    return [
        {
            "card_id": card_id,
            "position": i + 1,
            "position_name": positions[i],
            "is_reversed": random.random() < 0.3,  # 30%概率逆位
        }
        for i, card_id in enumerate(selected)
    ]
```

- [ ] **Step 2: Create services/ai_engine.py**

```python
from anthropic import AsyncAnthropic
from app.config import settings

client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """你是一位经验丰富的塔罗占卜师，拥有20年解读经验。你温柔、智慧且富有洞察力。

解读规则：
1. 先说明牌阵中每张牌在对应位置的含义
2. 将牌意与用户的问题/情况紧密联系起来
3. 把多张牌串联成一个完整的故事
4. 既指出积极的方面，也温和地提醒需要注意的问题
5. 最后给出具体的建议和行动指引
6. 使用温暖、神秘但不过分夸张的语气
7. 不要声称能100%预测未来，而是引导用户反思和觉察

禁忌：
- 不预测死亡、严重疾病或法律问题
- 不对用户的重大决定（离婚、辞职等）给出绝对化的建议
- 始终强调用户自己有选择的自由和能力"""

async def generate_reading(
    spread_type: str,
    question: str | None,
    theme: str | None,
    cards_info: list[dict],
) -> str:
    """调用Claude API生成塔罗解读"""

    # 构建牌阵信息
    cards_text = ""
    for c in cards_info:
        direction = "逆位" if c.get("is_reversed") else "正位"
        cards_text += f"""
位置{c['position']} - {c['position_name']}: {c['name_zh']}({c['name_en']}) [{direction}]
- 牌面: {c['image_description'][:100]}...
- {direction}含义: {c[f'meaning_{"reversed" if c.get("is_reversed") else "upright"}'][:200]}...
"""

    user_prompt = f"""请为用户进行塔罗解读。

牌阵类型: {spread_type}
用户问题: {question or "未指定具体问题"}
解读主题: {theme or "综合运势"}

抽取的牌:
{cards_text}

请提供完整的解读，包括：
1. 牌阵总览（整体能量和主题）
2. 逐牌解读（每张牌在对应位置的含义）
3. 综合解读（将所有牌串联成完整故事）
4. 建议与指引（用户可以在现实层面采取的行动）"""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return response.content[0].text
```

- [ ] **Step 3: Create schemas/reading.py**

```python
from pydantic import BaseModel
from datetime import datetime

class CreateReadingRequest(BaseModel):
    spread_type: str  # daily/triangle/celtic_cross/etc
    question: str | None = None
    theme: str | None = None  # love/career/finance/general

class DrawnCardResponse(BaseModel):
    id: int
    card_id: int
    card_name: str
    position: int
    position_name: str
    is_reversed: bool

class ReadingResponse(BaseModel):
    id: str
    spread_type: str
    question: str | None
    theme: str | None
    interpretation: str | None
    is_paid: bool
    created_at: datetime
    drawn_cards: list[DrawnCardResponse]

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Create api/readings.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.user import User
from app.models.card import TarotCard
from app.models.reading import Reading, DrawnCard
from app.schemas.reading import CreateReadingRequest, ReadingResponse
from app.services.tarot import draw_cards
from app.services.ai_engine import generate_reading
from app.utils.auth import get_current_user
from app.config import settings

router = APIRouter(prefix="/readings", tags=["占卜解读"])

@router.post("/spread/{spread_type}", response_model=ReadingResponse)
async def create_reading(
    spread_type: str,
    req: CreateReadingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check free limit for non-members
    if not user.is_member and user.free_readings_today >= settings.FREE_DAILY_READINGS:
        raise HTTPException(status_code=402, detail="今日免费次数已用完，请开通会员")

    # Draw cards
    cards_data = draw_cards(spread_type)

    # Create reading record
    reading = Reading(
        user_id=user.id,
        spread_type=spread_type,
        question=req.question,
        theme=req.theme,
        is_paid=user.is_member or user.free_readings_today >= settings.FREE_DAILY_READINGS,
    )
    db.add(reading)
    await db.flush()

    # Save drawn cards and collect card info for AI
    cards_info = []
    for c in cards_data:
        result = await db.execute(select(TarotCard).where(TarotCard.id == c["card_id"]))
        card = result.scalar_one()

        drawn = DrawnCard(
            reading_id=reading.id,
            card_id=c["card_id"],
            position=c["position"],
            position_name=c["position_name"],
            is_reversed=c["is_reversed"],
        )
        db.add(drawn)

        cards_info.append({
            **c,
            "name_zh": card.name_zh,
            "name_en": card.name_en,
            "image_description": card.image_description,
            "meaning_upright": card.meaning_upright,
            "meaning_reversed": card.meaning_reversed,
            "love_upright": card.love_upright,
            "love_reversed": card.love_reversed,
            "career_upright": card.career_upright,
            "career_reversed": card.career_reversed,
            "finance_upright": card.finance_upright,
            "finance_reversed": card.finance_reversed,
        })

    # Generate AI interpretation
    interpretation = await generate_reading(
        spread_type, req.question, req.theme, cards_info
    )
    reading.interpretation = interpretation

    # Update user's daily count
    user.free_readings_today += 1

    await db.flush()

    # Reload with relationships
    await db.refresh(reading, ["drawn_cards"])

    # Build response
    drawn_cards_resp = []
    for dc in reading.drawn_cards:
        card_result = await db.execute(select(TarotCard).where(TarotCard.id == dc.card_id))
        card = card_result.scalar_one()
        drawn_cards_resp.append({
            "id": dc.id,
            "card_id": dc.card_id,
            "card_name": card.name_zh,
            "position": dc.position,
            "position_name": dc.position_name,
            "is_reversed": dc.is_reversed,
        })

    return ReadingResponse(
        id=reading.id,
        spread_type=reading.spread_type,
        question=reading.question,
        theme=reading.theme,
        interpretation=reading.interpretation,
        is_paid=reading.is_paid,
        created_at=reading.created_at,
        drawn_cards=drawn_cards_resp,
    )
```

- [ ] **Step 5: Register route in main.py, then test**

```bash
# Test with JWT token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login -d '{"code":"test"}' | jq -r '.token')
curl -X POST http://localhost:8000/readings/spread/three_card \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"我的感情运势如何？","theme":"love"}'
# Expected: 完整的AI解读（需要Claude API key）
```

- [ ] **Step 6: Commit**

---

### Task 8: AI追问对话API

**Files:**
- Create: `backend/app/schemas/chat.py`
- Create: `backend/app/api/chat.py`

- [ ] **Step 1: Create api/chat.py**

```python
from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db
from app.models.user import User
from app.models.reading import Reading, ChatMessage
from app.utils.auth import get_current_user

router = APIRouter(prefix="/readings", tags=["AI追问"])

@router.post("/{reading_id}/chat")
async def chat_followup(
    reading_id: str,
    body: dict,  # {"message": "..."}
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check free limit
    if not user.is_member and user.free_chats_today >= settings.FREE_CHAT_MESSAGES:
        raise HTTPException(status_code=402, detail="今日追问次数已用完")

    # Verify reading belongs to user
    result = await db.execute(
        select(Reading)
        .where(Reading.id == reading_id, Reading.user_id == user.id)
        .options(selectinload(Reading.chat_messages))
    )
    reading = result.scalar_one_or_none()
    if not reading:
        raise HTTPException(status_code=404, detail="解读记录不存在")

    # Save user message
    user_msg = ChatMessage(reading_id=reading_id, role="user", content=body["message"])
    db.add(user_msg)

    # Build conversation history for Claude
    messages = []
    for msg in reading.chat_messages:
        messages.append({"role": msg.role, "content": msg.content})

    # Add context about the original reading
    system_prompt = f"""你是一个温柔睿智的塔罗导师。用户刚才的解读结果是：
{reading.interpretation[:500]}

请基于这个解读，继续和用户深入探讨他们的问题。保持连续性和一致性。"""

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    ai_reply = response.content[0].text

    # Save AI response
    ai_msg = ChatMessage(reading_id=reading_id, role="assistant", content=ai_reply)
    db.add(ai_msg)

    user.free_chats_today += 1

    return {
        "reply": ai_reply,
        "remaining_free": max(0, settings.FREE_CHAT_MESSAGES - user.free_chats_today),
    }
```

- [ ] **Step 2: Commit**

---

## Phase 4: 支付与会员系统

### Task 9: 微信支付 + 订单API

**Files:**
- Create: `backend/app/schemas/order.py`
- Create: `backend/app/api/orders.py`
- Create: `backend/app/api/membership.py`
- Create: `backend/app/services/payment.py`

**Interfaces:**
- Consumes: `Order`, `User` models, WeChat Pay API v3
- Produces: `POST /orders` (创建订单+支付参数), `POST /orders/callback` (支付回调), `GET /membership/status`, `POST /membership/purchase`

- [ ] **Step 1: Create services/payment.py**

```python
import hashlib
import time
import uuid
from wechatpayv3 import WeChatPay, WeChatPayType
from app.config import settings

# 商品配置
PRODUCTS = {
    "single_reading": {"name": "单次深度占卜", "price": 9.90},
    "membership_monthly": {"name": "月度会员", "price": 29.90},
    "membership_yearly": {"name": "年度会员", "price": 198.00},
    "membership_lifetime": {"name": "永久会员", "price": 298.00},
    "annual_report": {"name": "年度运势报告", "price": 29.90},
}

def create_order_params(openid: str, product_type: str) -> dict:
    """生成微信支付JSAPI下单参数"""
    product = PRODUCTS.get(product_type)
    if not product:
        raise ValueError(f"未知商品类型: {product_type}")

    order_no = f"TAROT{int(time.time())}{uuid.uuid4().hex[:6].upper()}"

    wxpay = WeChatPay(
        wechatpay_type=WeChatPayType.JSAPI,
        mchid=settings.WECHAT_MCH_ID,
        apiv3_key=settings.WECHAT_API_KEY_V3,
        # cert需要在服务器上配置
    )

    # 实际支付的请求参数（这里返回简化的参数供前端调用wx.requestPayment）
    return {
        "order_no": order_no,
        "amount": product["price"],
        "product_name": product["name"],
        "product_type": product_type,
        # 前端需要的信息:
        # appId, timeStamp, nonceStr, package, signType, paySign
    }
```

- [ ] **Step 2: Create api/orders.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.models.order import Order
from app.services.payment import create_order_params, PRODUCTS
from app.utils.auth import get_current_user

router = APIRouter(prefix="/orders", tags=["支付订单"])

@router.post("")
async def create_order(
    body: dict,  # {"product_type": "membership_lifetime"}
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product_type = body["product_type"]
    product = PRODUCTS.get(product_type)
    if not product:
        raise HTTPException(status_code=400, detail="无效的商品类型")

    # Create order in database
    order = Order(
        user_id=user.id,
        order_no=f"TAROT_{user.id[:8]}_{int(__import__('time').time())}",
        product_type=product_type,
        amount=product["price"],
        status="pending",
    )
    db.add(order)
    await db.flush()

    return {
        "order_id": order.id,
        "order_no": order.order_no,
        "amount": order.amount,
        "product_name": product["name"],
    }

@router.post("/callback")
async def payment_callback(body: dict, db: AsyncSession = Depends(get_db)):
    """微信支付回调通知"""
    # 微信支付回调会发送加密的支付结果
    # 实际需要解密和验签，这里简化处理
    from sqlalchemy import select

    order_no = body.get("out_trade_no")
    result = await db.execute(select(Order).where(Order.order_no == order_no))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    order.status = "paid"
    order.paid_at = __import__('datetime').datetime.utcnow()

    # 根据商品类型处理
    from datetime import timedelta
    from sqlalchemy import select as sel

    user_result = await db.execute(sel(User).where(User.id == order.user_id))
    user = user_result.scalar_one()

    if order.product_type == "single_reading":
        pass  # 单次解读在创建reading时已处理
    elif order.product_type == "membership_monthly":
        from datetime import datetime
        now = datetime.utcnow()
        if user.member_expires_at and user.member_expires_at > now:
            user.member_expires_at = user.member_expires_at + timedelta(days=30)
        else:
            user.member_expires_at = now + timedelta(days=30)
        user.is_member = True
    elif order.product_type == "membership_yearly":
        from datetime import datetime
        now = datetime.utcnow()
        if user.member_expires_at and user.member_expires_at > now:
            user.member_expires_at = user.member_expires_at + timedelta(days=365)
        else:
            user.member_expires_at = now + timedelta(days=365)
        user.is_member = True
    elif order.product_type == "membership_lifetime":
        user.is_member = True
        user.member_expires_at = None  # 永不过期

    return {"code": "SUCCESS"}
```

- [ ] **Step 3: Create api/membership.py**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.services.payment import PRODUCTS

router = APIRouter(prefix="/membership", tags=["会员"])

@router.get("/status")
async def membership_status(user: User = Depends(get_current_user)):
    return {
        "is_member": user.is_member,
        "expires_at": user.member_expires_at,
        "free_readings_today": user.free_readings_today,
        "free_chats_today": user.free_chats_today,
    }

@router.get("/products")
async def list_products():
    """返回可购买的商品列表"""
    return [
        {"id": k, "name": v["name"], "price": v["price"]}
        for k, v in PRODUCTS.items()
    ]
```

- [ ] **Step 4: Register routes in main.py, Commit**

---

## Phase 5: 增长功能

### Task 10: 分享裂变 + 运势卡片

**Files:**
- Create: `backend/app/api/share.py`
- Create: `backend/app/services/share.py`
- Create: `miniapp/components/share-image/`

- [ ] **Step 1: Create api/share.py**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user

router = APIRouter(prefix="/share", tags=["分享裂变"])

@router.post("/track")
async def track_share(
    body: dict,  # {"sharer_id": "...", "channel": "wechat_friend"}
    db: AsyncSession = Depends(get_db),
):
    """追踪分享行为，给分享者奖励"""
    # 记录分享日志，给分享者增加免费次数（无需登录也可追踪）
    sharer_id = body.get("sharer_id")
    if sharer_id:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.id == sharer_id))
        sharer = result.scalar_one_or_none()
        if sharer:
            sharer.free_readings_today = max(0, sharer.free_readings_today - 1)  # 返还一次
    return {"success": True}
```

---

## Phase 6: 附加功能

### Task 11: 塔罗日记API

**Files:**
- Create: `backend/app/schemas/diary.py`
- Create: `backend/app/api/diary.py`

- [ ] **Step 1: Create api/diary.py**

```python
import random
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.models.diary import DiaryEntry
from app.models.card import TarotCard
from app.models.user import User
from app.utils.auth import get_current_user

router = APIRouter(prefix="/diary", tags=["塔罗日记"])

@router.post("/entries")
async def create_entry(
    body: dict,  # {"mood": "happy", "reflection": "..."}
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Draw a random card for today's reflection
    result = await db.execute(select(func.count(TarotCard.id)))
    count = result.scalar()
    random_id = random.randint(1, count)

    entry = DiaryEntry(
        user_id=user.id,
        entry_date=date.today(),
        mood=body.get("mood"),
        card_id=random_id,
        reflection=body.get("reflection"),
    )
    db.add(entry)
    await db.flush()

    card_result = await db.execute(select(TarotCard).where(TarotCard.id == random_id))
    card = card_result.scalar_one()

    return {
        "id": entry.id,
        "date": str(entry.entry_date),
        "mood": entry.mood,
        "card": {"id": card.id, "name_zh": card.name_zh, "meaning_upright": card.meaning_upright[:200]},
        "reflection": entry.reflection,
    }

@router.get("/entries")
async def list_entries(
    page: int = Query(1, ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page_size = 20
    offset = (page - 1) * page_size
    result = await db.execute(
        select(DiaryEntry)
        .where(DiaryEntry.user_id == user.id)
        .order_by(DiaryEntry.entry_date.desc())
        .offset(offset)
        .limit(page_size)
    )
    entries = result.scalars().all()

    return {
        "entries": [
            {
                "id": e.id,
                "date": str(e.entry_date),
                "mood": e.mood,
                "reflection": e.reflection,
            }
            for e in entries
        ],
        "page": page,
    }
```

- [ ] **Step 2: Register route, Commit**

---

### Task 12: 年度报告API

**Files:**
- Create: `backend/app/api/report.py`

- [ ] **Step 1: Create api/report.py**

```python
import random
from datetime import date
from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.models.user import User
from app.models.card import TarotCard
from app.services.tarot import draw_cards
from app.config import settings
from app.utils.auth import get_current_user

router = APIRouter(prefix="/report", tags=["年度报告"])

@router.get("/annual")
async def get_annual_report(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.is_member:
        raise HTTPException(status_code=402, detail="年度报告仅限会员使用")

    # Draw 13 cards for year ahead
    cards_data = draw_cards("year_ahead")
    cards_info = []
    for c in cards_data:
        result = await db.execute(select(TarotCard).where(TarotCard.id == c["card_id"]))
        card = result.scalar_one()
        direction = "逆位" if c["is_reversed"] else "正位"
        cards_info.append({
            "month": c["position_name"],
            "card_name": card.name_zh,
            "direction": direction,
            "meaning": card.meaning_upright[:200] if not c["is_reversed"] else card.meaning_reversed[:200],
        })

    # AI generates the annual report
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = f"""生成一份专业的塔罗年度运势报告。当前年份: {date.today().year}

各月运势牌:
{chr(10).join(f'{c["month"]}: {c["card_name"]}({c["direction"]})' for c in cards_info)}

请撰写一份温暖的年度运势报告，包含:
1. 年度主题：这一年的核心能量是什么
2. 逐月运势：每个月的情感、事业、财运要点（每个月3-4句话）
3. 关键月份：哪几个月是关键转折点
4. 年度寄语"""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=3072,
        messages=[{"role": "user", "content": prompt}],
    )

    return {
        "cards": cards_info,
        "report": response.content[0].text,
        "generated_at": str(date.today()),
    }
```

- [ ] **Step 2: Register route, Commit**

---

## Phase 7: 部署上线

### Task 13: Docker镜像 + 部署配置

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.env.example`
- Create: `docs/deploy-guide.md`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create .env.example**

```
DATABASE_URL=mysql+asyncmy://tarot:tarot123@mysql:3306/tarot_db
REDIS_URL=redis://redis:6379/0
ANTHROPIC_API_KEY=sk-ant-xxxxx
WECHAT_APP_ID=wxXXXX
WECHAT_APP_SECRET=XXXX
WECHAT_MCH_ID=XXXX
WECHAT_API_KEY_V3=XXXX
JWT_SECRET=generate-a-random-secret-here
```

- [ ] **Step 3: Create 部署指南**

```markdown
# 塔罗占卜小程序部署指南

## 1. 服务器准备
- 阿里云/腾讯云 ECS (2核4G, CentOS 7+)
- 安装 Docker + Docker Compose

## 2. 启动服务
```bash
# 上传代码到服务器
scp -r backend/ user@server:/opt/tarot/

# 配置环境变量
cp .env.example .env
vim .env  # 填入真实的API密钥

# 启动
docker-compose up -d

# 导入塔罗数据
docker-compose exec app python -m app.db.seed
```

## 3. 配置HTTPS + 域名
- 申请SSL证书 (Let's Encrypt)
- Nginx反向代理 80/443 → 8000
- 配置微信小程序服务器域名白名单

## 4. 小程序发布
- 微信开发者工具打开 miniapp/ 目录
- 修改 utils/api.js 中的 BASE_URL
- 上传代码 → 提交审核 → 发布
```

- [ ] **Step 4: Commit**

---

## 实施顺序建议

```
Phase 1 (Task 1-3): 后端基础 + 数据库 + 数据导入
    ↓
Phase 2 (Task 4-6): 用户认证 + 百科API + 小程序框架 + 首页
    ↓
Phase 3 (Task 7-8): 核心占卜引擎 + AI解读 + 追问对话  ← 核心
    ↓
Phase 4 (Task 9):    支付 + 会员系统
    ↓
Phase 5 (Task 10):   分享裂变 + 运势卡片
    ↓
Phase 6 (Task 11-12): 塔罗日记 + 年度报告
    ↓
Phase 7 (Task 13):   Docker化 + 部署上线
```

## 预估总工时

| Phase | 内容 | 预估 |
|-------|------|------|
| Phase 1 | 基础架构 | 2-3小时 |
| Phase 2 | 百科+首页 | 3-4小时 |
| Phase 3 | 核心引擎 | 4-6小时 |
| Phase 4 | 支付会员 | 2-3小时 |
| Phase 5 | 增长功能 | 1-2小时 |
| Phase 6 | 附加功能 | 1-2小时 |
| Phase 7 | 部署 | 1-2小时 |
| **总计** | | **14-22小时** |
