"""从 markdown 数据文件解析并导入78张塔罗牌到数据库

数据文件位于 /mnt/e/tarot-miniapp/data/，包含两种格式：
  - 大阿尔卡纳 (major-arcana.md): 子弹列表格式（- **字段**：值）
  - 四组小阿尔卡纳: 各具特色的 ### 小节格式（权杖/圣杯/宝剑/星币写法不同）

用法:
    cd /mnt/e/tarot-miniapp/backend
    python -m app.db.seed
"""

import re
import asyncio
from pathlib import Path
from sqlalchemy import select
from app.db.database import async_session
from app.models.card import TarotCard

# ---------------------------------------------------------------------------
# 正则常量
# ---------------------------------------------------------------------------

# 大阿尔卡纳小节标题: ## 0. 愚者（The Fool）
RE_MAJOR_HEADING = re.compile(r'##\s*(\d+)\.\s*(.+?)（(.+?)）')

# 小阿尔卡纳小节标题: ## 二、权杖王牌 Ace of Wands  /  ## 二、圣杯王牌（Ace of Cups / 圣杯一）
RE_MINOR_HEADING = re.compile(
    r'##\s*[一二三四五六七八九十十一十二十三十四十五]+[、.．]\s*'
    r'(.+?)(?:\s*（([^）]*)）|\s+(.+?))\s*$'
)

RE_BULLET_FIELD = re.compile(
    r'-\s*\*\*([^*]+)\*\*[：:]\s*(.+?)(?=\n\s*-\s*\*\*|\n\s*###|\n\s*##|\Z)',
    re.DOTALL,
)

# 匹配 ### 小节: 可选的数字前缀 + 标题关键词 + 任意后缀（如（详细）详解）
RE_SUBSECTION = re.compile(
    r'###\s*(?:\d+\.?\s*)?(.*?)\s*\n(.+?)(?=\n\s*###|\n\s*##|\Z)',
    re.DOTALL,
)

# 在小节内部提取 **正位** / **逆位** 内容（兼容冒号在 bold 内/外）
RE_UPRIGHT = re.compile(r'\*\*正位[：:]*\*\*[：:]*\s*(.+?)(?=\n\s*\*\*逆位|\Z)', re.DOTALL)
RE_REVERSED = re.compile(r'\*\*逆位[：:]*\*\*[：:]*\s*(.+?)(?=\n\s*\*\*|\Z)', re.DOTALL)

# 小阿尔卡纳文件列表
MINOR_SUIT_FILES = [
    ('wands', 'wands-suit.md', '火'),
    ('cups', 'cups-suit.md', '水'),
    ('swords', 'swords-suit.md', '风'),
    ('pentacles', 'pentacles-suit.md', '土'),
]

# 每套牌的起始全局编号
SUIT_START_NUMBER = {'wands': 22, 'cups': 36, 'swords': 50, 'pentacles': 64}

# ---------------------------------------------------------------------------
# 通用辅助函数
# ---------------------------------------------------------------------------


def _build_subsection_map(text: str) -> dict[str, str]:
    """将 ### 小节文本按标题关键词构建为 {关键词: 内容} 字典。

    匹配时忽略数字前缀、标点和后缀词（详见 extra 等）。
    """
    sections: dict[str, str] = {}
    for m in RE_SUBSECTION.finditer(text):
        raw_title = m.group(1).strip()
        content = m.group(2).strip()
        # 归一化: 去数字前缀、去括号及内容、去尾缀词
        key = re.sub(r'^\d+\.?\s*', '', raw_title)
        key = re.sub(r'[（(].*?[）)]', '', key)
        key = key.rstrip('详解').rstrip('含义').rstrip('牌义').strip()
        if key and content:
            # 除非旧 key 更长，否则覆盖（短 key 更通用）
            if key not in sections or len(key) < len(
                k for k in sections if k != key
            ):
                sections[key] = content
    return sections


def _extract_upright_reversed(text: str) -> tuple[str, str]:
    """从文本中提取 **正位** 和 **逆位** 内容。"""
    upright = ''
    reversed_ = ''
    if m := RE_UPRIGHT.search(text):
        upright = m.group(1).strip()
    if m := RE_REVERSED.search(text):
        reversed_ = m.group(1).strip()
    return upright, reversed_


def _parse_keywords_from_table(text: str) -> tuple[str, str]:
    """解析 swords 风格关键词表格 → (正位关键词, 逆位关键词)。"""
    upright_parts: list[str] = []
    reversed_parts: list[str] = []
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('|') and not line.startswith('|---'):
            cells = [c.strip() for c in line.split('|')]
            if len(cells) >= 3:
                # cells[0] 空（行首 | 前）, cells[1] 正位, cells[2] 逆位
                if cells[1] and '正位' not in cells[1]:
                    upright_parts.append(cells[1])
                if cells[2] and '逆位' not in cells[2]:
                    reversed_parts.append(cells[2])
    return ', '.join(upright_parts), ', '.join(reversed_parts)


def _parse_keywords_prefixed(text: str) -> tuple[str, str]:
    """解析 pentacles 风格关键词: 正位：xxx 逆位：xxx"""
    upright = ''
    reversed_ = ''
    if m := re.search(r'^正位[：:]\s*(.+?)(?:\n|$)', text, re.MULTILINE):
        upright = m.group(1).strip()
    if m := re.search(r'^逆位[：:]\s*(.+?)(?:\n|$)', text, re.MULTILINE):
        reversed_ = m.group(1).strip()
    return upright, reversed_


# ---------------------------------------------------------------------------
# 大阿尔卡纳解析
# ---------------------------------------------------------------------------


def _extract_bullet(text: str, field_name: str) -> str:
    """从子弹列表格式提取指定字段值。"""
    for m in RE_BULLET_FIELD.finditer(text):
        if m.group(1).strip() == field_name:
            return m.group(2).strip()
    return ''


def parse_major_card(text: str) -> dict:
    """解析单张大阿尔卡纳牌（子弹列表格式）。"""
    data: dict = {}
    first_line = text.split('\n')[0]

    if m := RE_MAJOR_HEADING.match(first_line):
        data['name_zh'] = m.group(2).strip()
        data['name_en'] = m.group(3).strip()
        data['card_number'] = int(m.group(1))

    data['element'] = _extract_bullet(text, '元素')
    data['image_description'] = _extract_bullet(text, '牌面描述')
    data['keywords_upright'] = _extract_bullet(text, '关键词')

    data['meaning_upright'] = _extract_bullet(text, '正位牌义')
    data['meaning_reversed'] = _extract_bullet(text, '逆位牌义')

    data['love_upright'] = _extract_bullet(text, '感情正位')
    data['love_reversed'] = _extract_bullet(text, '感情逆位')
    data['career_upright'] = _extract_bullet(text, '事业正位')
    data['career_reversed'] = _extract_bullet(text, '事业逆位')
    data['finance_upright'] = _extract_bullet(text, '财运正位')
    data['finance_reversed'] = _extract_bullet(text, '财运逆位')
    data['health_upright'] = _extract_bullet(text, '健康正位')
    data['health_reversed'] = _extract_bullet(text, '健康逆位')

    return data


# ---------------------------------------------------------------------------
# 小阿尔卡纳解析
# ---------------------------------------------------------------------------


def parse_minor_card(text: str) -> dict:
    """解析单张小阿尔卡纳牌，兼容四种文件风格。"""
    data: dict = {}
    first_line = text.split('\n')[0]

    # --- 提取中英文名称 ---
    if m := RE_MINOR_HEADING.match(first_line):
        data['name_zh'] = m.group(1).strip()
        # group2 = parens format (cups), group3 = space-separated (wands/swords/pentacles)
        en_part = (m.group(2) or m.group(3) or '').strip()
        # 去别名（/ 分隔的英文别称、中文别称）
        if ' / ' in en_part:
            en_part = en_part.split(' / ')[0].strip()
        data['name_en'] = en_part

    # --- 构建 ### 小节索引 ---
    subs = _build_subsection_map(text)

    # --- 关键词 ---
    kw_text = subs.get('关键词', '')
    if kw_text:
        # swords 表格风格
        if '|' in kw_text and '正位关键词' in kw_text:
            kw_up, kw_rev = _parse_keywords_from_table(kw_text)
        # pentacles 前缀风格
        elif kw_text.startswith('正位') or kw_text.startswith('逆位'):
            kw_up, kw_rev = _parse_keywords_prefixed(kw_text)
        else:
            kw_up, kw_rev = kw_text, ''
    else:
        # 从 基本信息 表格取
        basic = subs.get('基本信息', '')
        kw_up = ''
        if m := re.search(r'\*\*关键字\*\*[：:]\s*(.+?)(?:\n|$)', basic):
            kw_up = m.group(1).strip()
        kw_rev = ''
    data['keywords_upright'] = kw_up
    data['keywords_reversed'] = kw_rev

    # --- 元素 ---
    elem = subs.get('元素', '')
    if not elem:
        basic = subs.get('基本信息', '')
        if m := re.search(r'\*\*元素\*\*[：:]\s*(.+?)(?:\n|$)', basic):
            elem = m.group(1).strip()
    # 去掉括号内的英文说明（如 "水（Water）" → "水"）
    elem = re.sub(r'[（(].*?[）)]', '', elem).strip()
    data['element'] = elem

    # --- 牌面描述 ---
    data['image_description'] = subs.get('牌面描述', '')

    # --- 正逆位牌义（多种标题变体） ---
    meaning_up = (
        subs.get('正位含义', '')
        or subs.get('正位', '')
        or ''
    )
    meaning_rev = (
        subs.get('逆位含义', '')
        or subs.get('逆位', '')
        or ''
    )
    data['meaning_upright'] = meaning_up
    data['meaning_reversed'] = meaning_rev

    # --- 感情/爱情/关系 ---
    love_text = (
        subs.get('感情', '')
        or subs.get('爱情', '')
        or ''
    )
    if love_text:
        data['love_upright'], data['love_reversed'] = _extract_upright_reversed(love_text)
    else:
        data['love_upright'] = data['love_reversed'] = ''

    # --- 事业 ---
    career_text = subs.get('事业', '')
    if career_text:
        data['career_upright'], data['career_reversed'] = _extract_upright_reversed(career_text)
    else:
        data['career_upright'] = data['career_reversed'] = ''

    # --- 财务/财运/财富 ---
    finance_text = (
        subs.get('财务', '')
        or subs.get('财运', '')
        or subs.get('财富', '')
        or ''
    )
    if finance_text:
        data['finance_upright'], data['finance_reversed'] = _extract_upright_reversed(finance_text)
    else:
        data['finance_upright'] = data['finance_reversed'] = ''

    # --- 健康 ---
    health_text = subs.get('健康', '')
    if health_text:
        data['health_upright'], data['health_reversed'] = _extract_upright_reversed(health_text)
    else:
        data['health_upright'] = data['health_reversed'] = ''

    return data


# ---------------------------------------------------------------------------
# 确保字段存在
# ---------------------------------------------------------------------------


def _ensure_fields(data: dict, keys: list[str]) -> dict:
    for k in keys:
        data.setdefault(k, '')
    return data


CARD_FIELDS = [
    'name_zh', 'name_en', 'element', 'image_description',
    'keywords_upright', 'keywords_reversed',
    'meaning_upright', 'meaning_reversed',
    'love_upright', 'love_reversed',
    'career_upright', 'career_reversed',
    'finance_upright', 'finance_reversed',
    'health_upright', 'health_reversed',
]

ARCANA_CARD_FIELDS = [
    'meaning_upright', 'meaning_reversed',
    'love_upright', 'love_reversed',
    'career_upright', 'career_reversed',
    'finance_upright', 'finance_reversed',
    'health_upright', 'health_reversed',
]


def _build_card(overrides: dict) -> TarotCard:
    """用 overrides 字典构建 TarotCard 实例，缺失字段填空字符串。"""
    kwargs = {k: overrides.get(k, '') for k in CARD_FIELDS}
    kwargs['arcana'] = overrides.get('arcana', 'major')
    kwargs['suit'] = overrides.get('suit')
    kwargs['card_number'] = overrides.get('card_number', 0)
    return TarotCard(**kwargs)


# ---------------------------------------------------------------------------
# 主导入函数
# ---------------------------------------------------------------------------


async def seed_cards():
    """从 markdown 数据文件导入所有塔罗牌到数据库。"""
    data_dir = Path("/mnt/e/tarot-miniapp/data")
    card_counter = 0

    async with async_session() as session:
        # 检查是否已导入
        result = await session.execute(select(TarotCard).limit(1))
        if result.scalar_one_or_none():
            print("塔罗牌数据已存在, 跳过导入")
            return

        # ==================== 大阿尔卡纳 (0-21) ====================
        major_path = data_dir / "major-arcana.md"
        if major_path.exists():
            text = major_path.read_text(encoding='utf-8')
            chunks = text.split('\n---\n')
            for chunk in chunks:
                chunk = chunk.strip()
                if not chunk:
                    continue
                if not re.match(r'## \d+\.', chunk):
                    continue

                card_data = parse_major_card(chunk)
                if not card_data.get('name_zh'):
                    continue

                card = _build_card({
                    **card_data,
                    'arcana': 'major',
                    'suit': None,
                })
                session.add(card)
                card_counter += 1

        # ==================== 小阿尔卡纳 ====================
        for suit_name, filename, default_element in MINOR_SUIT_FILES:
            path = data_dir / filename
            if not path.exists():
                print(f"警告: 未找到 {filename}")
                continue

            text = path.read_text(encoding='utf-8')
            chunks = text.split('\n---\n')

            # 用于检查小节标题是否包含卡牌英文名
            re_is_card = re.compile(
                r'(?:Ace|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|'
                r'Page|Knight|Queen|King)\s+of\b'
            )

            card_num_in_suit = 0
            for chunk in chunks:
                chunk = chunk.strip()
                if not chunk:
                    continue
                if not chunk.startswith('## '):
                    continue
                if not re_is_card.search(chunk):
                    continue

                card_data = parse_minor_card(chunk)
                if not card_data.get('name_zh'):
                    continue

                card_num_in_suit += 1

                element = card_data.get('element') or default_element

                card = _build_card({
                    **card_data,
                    'card_number': SUIT_START_NUMBER[suit_name] + card_num_in_suit - 1,
                    'arcana': 'minor',
                    'suit': suit_name,
                    'element': element,
                })
                session.add(card)
                card_counter += 1

        await session.commit()
        print(f"成功导入 {card_counter} 张塔罗牌")


if __name__ == "__main__":
    asyncio.run(seed_cards())
