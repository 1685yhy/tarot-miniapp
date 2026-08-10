"""
Alembic 迁移链测试：新表 wishes / moon_reviews 可升级、可回滚。

在临时 SQLite 文件上跑完整迁移链（base → head → base），
验证开发 04 新增的两张表结构正确、downgrade 干净。
"""

from pathlib import Path
import sqlite3

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_alembic_migration_chain_wishes_and_reviews(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    from app.config import settings

    db_path = tmp_path / "migration_test.db"
    # env.py 会用 settings.DATABASE_URL 覆盖 alembic.ini 的 URL → 这里改 settings
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))

    # ── upgrade 到 head ──
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "wishes" in tables, "wishes 表应已创建"
    assert "moon_reviews" in tables, "moon_reviews 表应已创建"

    wish_cols = {r[1] for r in conn.execute("PRAGMA table_info(wishes)")}
    assert {"id", "user_id", "content", "status", "moon_phase", "created_at", "updated_at"} <= wish_cols

    review_cols = {r[1] for r in conn.execute("PRAGMA table_info(moon_reviews)")}
    assert {"id", "user_id", "review_date", "data", "created_at"} <= review_cols

    # 唯一约束（每人每天一份复盘）—— SQLite 以 sqlite_autoindex_* 命名，
    # 检查建表语句中带 UNIQUE 约束
    ddl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='moon_reviews'"
    ).fetchone()[0]
    assert "UNIQUE" in ddl.upper()

    # ── downgrade 回 base：两张新表被删除 ──
    command.downgrade(cfg, "base")
    tables_after = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()
    assert "wishes" not in tables_after
    assert "moon_reviews" not in tables_after


def test_alembic_migration_chain_subscribe_quota(tmp_path, monkeypatch):
    """迁移链新增 subscribe_quotas 表（星光晨讯订阅额度）：可升级、可回滚。"""
    from alembic import command
    from alembic.config import Config

    from app.config import settings

    db_path = tmp_path / "migration_quota.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))

    # ── upgrade 到 head ──
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "subscribe_quotas" in tables, "subscribe_quotas 表应已创建"

    cols = {r[1] for r in conn.execute("PRAGMA table_info(subscribe_quotas)")}
    assert {"user_id", "quota_available", "last_sent_date", "updated_at"} == cols, (
        f"subscribe_quotas 列应为 user_id/quota_available/last_sent_date/updated_at，实际 {cols}"
    )

    # ── downgrade 回 base：新表被删除 ──
    command.downgrade(cfg, "base")
    tables_after = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()
    assert "subscribe_quotas" not in tables_after


def test_alembic_migration_star_cards_wallpapers(tmp_path, monkeypatch):
    """迁移 f5a6b7c8d9e0：users 表新增 star_cards / wallpapers 列，可升级、可回滚。"""
    from alembic import command
    from alembic.config import Config

    from app.config import settings

    db_path = tmp_path / "migration_starcards.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))

    # ── upgrade 到 head ──
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    assert {"star_cards", "wallpapers"} <= user_cols, (
        f"users 表应含 star_cards/wallpapers 列，实际 {sorted(user_cols)}"
    )
    # 新列应为可空 Text（收藏品字段，无 server_default 约束）
    col_types = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(users)")}
    assert col_types["star_cards"] == "TEXT" and col_types["wallpapers"] == "TEXT"

    # ── downgrade 回 base：两列被删除 ──
    command.downgrade(cfg, "base")
    user_cols_after = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    conn.close()
    assert "star_cards" not in user_cols_after
    assert "wallpapers" not in user_cols_after
