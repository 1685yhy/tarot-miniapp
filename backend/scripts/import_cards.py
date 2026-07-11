#!/usr/bin/env python3
"""命令行入口: 从 markdown 数据文件导入塔罗牌到数据库。

用法:
    cd /mnt/e/tarot-miniapp/backend
    python -m scripts.import_cards
"""

import asyncio
from app.db.seed import seed_cards

if __name__ == "__main__":
    asyncio.run(seed_cards())
