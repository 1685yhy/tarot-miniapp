#!/usr/bin/env python3
"""
Tarot Card Image Generator
==========================
Generates 78 beautiful tarot card images with geometric art using PIL.

Output: 400x640 PNG images for each card in /mnt/e/tarot-miniapp/miniapp/images/cards/
"""

import math
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path("/mnt/e/tarot-miniapp/miniapp/images/cards")
FONT_PATH_WQY = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

# ---------------------------------------------------------------------------
# Card dimensions
# ---------------------------------------------------------------------------
CARD_W = 400
CARD_H = 640
CORNER_RADIUS = 24
OUTER_BORDER = 3
INNER_BORDER = 2
# usable interior after borders
INTERIOR_X0 = OUTER_BORDER + INNER_BORDER
INTERIOR_Y0 = OUTER_BORDER + INNER_BORDER
INTERIOR_X1 = CARD_W - INTERIOR_X0
INTERIOR_Y1 = CARD_H - INTERIOR_X0

# ---------------------------------------------------------------------------
# Colour palettes
# ---------------------------------------------------------------------------
# Gold colours
GOLD_LIGHT = (245, 211, 55)
GOLD = (212, 175, 55)
GOLD_DARK = (180, 140, 30)
GOLD_RICH = (200, 160, 40)
SILVER = (192, 192, 200)
SILVER_LIGHT = (220, 220, 230)
PALE_GOLD = (200, 180, 100)

# Major Arcana – deep purple/indigo
MAJOR_BG_TOP = (15, 5, 35)
MAJOR_BG_CENTER = (40, 15, 70)
MAJOR_BG_BOTTOM = (10, 5, 25)

# Wands – warm red/amber
WANDS_BG_TOP = (40, 5, 5)
WANDS_BG_CENTER = (80, 20, 10)
WANDS_BG_BOTTOM = (30, 5, 5)

# Cups – cool blue/teal
CUPS_BG_TOP = (5, 10, 40)
CUPS_BG_CENTER = (10, 30, 70)
CUPS_BG_BOTTOM = (5, 8, 30)

# Swords – pale silver/gray
SWORDS_BG_TOP = (30, 30, 35)
SWORDS_BG_CENTER = (55, 55, 65)
SWORDS_BG_BOTTOM = (25, 25, 30)

# Pentacles – deep green/gold
PENT_BG_TOP = (5, 25, 10)
PENT_BG_CENTER = (10, 45, 20)
PENT_BG_BOTTOM = (5, 20, 8)

# ---------------------------------------------------------------------------
# Card data – all 78 tarot cards
# ---------------------------------------------------------------------------
MAJOR_ARCANA = [
    (0, "愚者", "The Fool"),
    (1, "魔术师", "The Magician"),
    (2, "女祭司", "The High Priestess"),
    (3, "皇后", "The Empress"),
    (4, "皇帝", "The Emperor"),
    (5, "教皇", "The Hierophant"),
    (6, "恋人", "The Lovers"),
    (7, "战车", "The Chariot"),
    (8, "力量", "Strength"),
    (9, "隐士", "The Hermit"),
    (10, "命运之轮", "Wheel of Fortune"),
    (11, "正义", "Justice"),
    (12, "倒吊人", "The Hanged Man"),
    (13, "死神", "Death"),
    (14, "节制", "Temperance"),
    (15, "恶魔", "The Devil"),
    (16, "高塔", "The Tower"),
    (17, "星星", "The Star"),
    (18, "月亮", "The Moon"),
    (19, "太阳", "The Sun"),
    (20, "审判", "Judgement"),
    (21, "世界", "The World"),
]

MINOR_RANKS = [
    ("王牌", "Ace"),
    ("二", "Two"),
    ("三", "Three"),
    ("四", "Four"),
    ("五", "Five"),
    ("六", "Six"),
    ("七", "Seven"),
    ("八", "Eight"),
    ("九", "Nine"),
    ("十", "Ten"),
    ("侍从", "Page"),
    ("骑士", "Knight"),
    ("皇后", "Queen"),
    ("国王", "King"),
]

WANDS = [(f"权杖{zh}", f"{en} of Wands") for zh, en in MINOR_RANKS]
CUPS = [(f"圣杯{zh}", f"{en} of Cups") for zh, en in MINOR_RANKS]
SWORDS = [(f"宝剑{zh}", f"{en} of Swords") for zh, en in MINOR_RANKS]
PENTACLES = [(f"星币{zh}", f"{en} of Pentacles") for zh, en in MINOR_RANKS]

ROMAN_NUMERALS = [
    "0", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI",
]

# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------
def _load_fonts(wqy_path: str, size: int):
    """Try to load fonts; fall back to default if unavailable."""
    try:
        font_zh = ImageFont.truetype(wqy_path, size, encoding="utf-8")
        return font_zh
    except Exception:
        pass
    try:
        # Try Liberation Serif for a serif English fallback
        font_en = ImageFont.truetype(
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf", size
        )
        return font_en
    except Exception:
        return ImageFont.load_default()


def get_fonts():
    """Return dict of fonts at various sizes."""
    f = {}
    # Chinese fonts
    for sz, key in [(36, "zh_36"), (28, "zh_28"), (22, "zh_22"), (18, "zh_18"), (14, "zh_14")]:
        try:
            f[key] = ImageFont.truetype(FONT_PATH_WQY, sz, encoding="utf-8")
        except Exception:
            f[key] = ImageFont.load_default()
    # English fonts
    for sz, key in [(32, "en_32"), (28, "en_28"), (22, "en_22"), (18, "en_18"), (14, "en_14")]:
        try:
            f[key] = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf", sz
            )
        except Exception:
            f[key] = ImageFont.load_default()
    # Special: bold roman numerals
    for sz, key in [(40, "roman_40"), (36, "roman_36"), (32, "roman_32"), (28, "roman_28"), (24, "roman_24")]:
        try:
            f[key] = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf", sz
            )
        except Exception:
            f[key] = ImageFont.load_default()
    return f


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def create_card_base(w, h, radius, top_color, center_color, bottom_color):
    """Create card-sized image with rounded corners and a radial/vertical gradient."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Build gradient: vertical with radial emphasis from center
    cx, cy = w // 2, h // 2
    max_dist = math.sqrt(cx * cx + cy * cy)
    for y in range(h):
        for x in range(w):
            # Distance from center (normalised)
            dx = x - cx
            dy = y - cy
            dist = math.sqrt(dx * dx + dy * dy) / max_dist
            # Vertical factor
            vf = y / h
            # Blend: centre is center_color, edges blend based on dist and vf
            r = int(
                center_color[0] * (1 - dist * 0.6)
                + top_color[0] * (0.3 * (1 - vf) * dist)
                + bottom_color[0] * (0.3 * vf * dist)
            )
            g = int(
                center_color[1] * (1 - dist * 0.6)
                + top_color[1] * (0.3 * (1 - vf) * dist)
                + bottom_color[1] * (0.3 * vf * dist)
            )
            b = int(
                center_color[2] * (1 - dist * 0.6)
                + top_color[2] * (0.3 * (1 - vf) * dist)
                + bottom_color[2] * (0.3 * vf * dist)
            )
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            draw.point((x, y), fill=(r, g, b, 255))

    return img


def rounded_corners(img, radius):
    """Apply rounded corners mask."""
    mask = Image.new("L", img.size, 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.rounded_rectangle([(0, 0), img.size], radius=radius, fill=255)
    result = img.copy()
    result.putalpha(mask)
    return result


def draw_gold_border(draw, w, h, radius):
    """Draw outer gold border and inner dark border."""
    # Outer gold border (rounded)
    draw.rounded_rectangle(
        [(0, 0), (w - 1, h - 1)],
        radius=radius,
        outline=GOLD,
        width=OUTER_BORDER,
    )
    # Gold highlight (top-left edge)
    draw.rounded_rectangle(
        [(0, 0), (w - 1, h - 1)],
        radius=radius,
        outline=GOLD_LIGHT,
        width=1,
    )
    # Inner dark border
    gap = OUTER_BORDER
    draw.rounded_rectangle(
        [(gap, gap), (w - 1 - gap, h - 1 - gap)],
        radius=radius - 2 if radius > 4 else 1,
        outline=(10, 10, 26),
        width=INNER_BORDER,
    )


def draw_corner_filigree(draw, w, h):
    """Draw decorative gold filigree in the 4 corners."""
    filigree_color = GOLD_RICH
    # We draw a stylised curved line in each corner
    corners = [
        (12, 12, 1.0, 1.0),     # top-left
        (w - 12, 12, -1.0, 1.0),  # top-right
        (12, h - 12, 1.0, -1.0),  # bottom-left
        (w - 12, h - 12, -1.0, -1.0),  # bottom-right
    ]
    for cx, cy, sx, sy in corners:
        # Curved line using bezier-like segments
        points = []
        for t in range(0, 11):
            t_norm = t / 10.0
            # Spiral-like curve from corner inward
            px = cx + sx * (8 + 20 * t_norm - 5 * math.sin(t_norm * math.pi * 2))
            py = cy + sy * (8 + 15 * t_norm * t_norm - 8 * math.cos(t_norm * math.pi * 1.5))
            points.append((px, py))
        for i in range(len(points) - 1):
            draw.line(
                [points[i], points[i + 1]],
                fill=filigree_color,
                width=2,
            )
        # Small dot accent
        draw.ellipse(
            [cx - 4, cy - 4, cx + 4, cy + 4],
            fill=GOLD_LIGHT,
            outline=GOLD,
            width=1,
        )


def draw_concentric_circles(draw, cx, cy, max_r, n, colors, width=2):
    """Draw n concentric circles."""
    for i in range(n):
        r = max_r * (i + 1) / n
        color = colors[i % len(colors)]
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline=color,
            width=width,
        )


def draw_star(draw, cx, cy, outer_r, inner_r, points, color, width=2, rotation=0):
    """Draw a star polygon."""
    coords = []
    for i in range(points * 2):
        angle = rotation + math.pi * i / points - math.pi / 2
        r = outer_r if i % 2 == 0 else inner_r
        x = cx + math.cos(angle) * r
        y = cy + math.sin(angle) * r
        coords.append((x, y))
    for i in range(len(coords)):
        draw.line(
            [coords[i], coords[(i + 1) % len(coords)]],
            fill=color,
            width=width,
        )


def draw_mandala(draw, cx, cy, size, seed=0):
    """Draw a geometric mandala – varying star points, rings, and complexity."""
    random.seed(seed)
    # Base number of points
    points = 5 + (seed % 4) * 2  # 5, 7, 9, 11
    n_rings = 4 + (seed % 3)      # 4, 5, 6
    rotation = random.random() * math.pi / points

    # Colours (gold, purple, light gold)
    colors = [
        GOLD_RICH,
        GOLD_LIGHT,
        (160, 120, 60),
        GOLD,
        (200, 170, 80),
    ]

    # Outer glow circles
    glow_alpha = 40
    for r in range(int(size * 0.85), int(size * 0.95), 4):
        alpha = max(5, glow_alpha - (r - int(size * 0.65)))
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline=(255, 215, 0, alpha),
            width=1,
        )

    # Concentric rings
    for i in range(n_rings):
        r = size * (0.15 + 0.7 * (i + 1) / n_rings)
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline=colors[i % len(colors)],
            width=2,
        )

    # Star patterns
    for i in range(min(3, n_rings)):
        outer_r = size * (0.25 + 0.5 * (i + 1) / n_rings)
        inner_r = outer_r * (0.3 + 0.15 * (seed % 3) / 3.0)
        star_points = points + i * 2
        draw_star(
            draw, cx, cy,
            outer_r, inner_r,
            star_points,
            colors[(i + 1) % len(colors)],
            width=2,
            rotation=rotation + i * 0.3,
        )

    # Innermost core
    draw.ellipse(
        [cx - size * 0.08, cy - size * 0.08, cx + size * 0.08, cy + size * 0.08],
        fill=GOLD_LIGHT,
        outline=GOLD,
        width=2,
    )

    # Dot ring around core
    n_dots = points * 2
    dot_r = size * 0.15
    for i in range(n_dots):
        angle = rotation + 2 * math.pi * i / n_dots
        dx = cx + math.cos(angle) * dot_r
        dy = cy + math.sin(angle) * dot_r
        draw.ellipse(
            [dx - 2, dy - 2, dx + 2, dy + 2],
            fill=GOLD_LIGHT,
        )

    # Radiating lines from center to outer ring
    n_lines = points * 2
    line_r = size * 0.75
    for i in range(n_lines):
        angle = rotation + 2 * math.pi * i / n_lines
        dx = cx + math.cos(angle) * line_r
        dy = cy + math.sin(angle) * line_r
        draw.line(
            [(cx, cy), (dx, dy)],
            fill=(GOLD_RICH[0], GOLD_RICH[1], GOLD_RICH[2], 60),
            width=1,
        )


# ---------------------------------------------------------------------------
# Suit symbol drawing
# ---------------------------------------------------------------------------

def draw_wand_symbol(draw, cx, cy, size, color=GOLD):
    """Draw a stylised wand/staff with flame top."""
    hw = size * 0.06
    # Staff body
    draw.rectangle(
        [cx - hw, cy - size * 0.4, cx + hw, cy + size * 0.4],
        fill=GOLD_RICH,
    )
    # Flame top
    flame_pts = [
        (cx, cy - size * 0.55),
        (cx - size * 0.12, cy - size * 0.35),
        (cx + size * 0.12, cy - size * 0.35),
    ]
    draw.polygon(flame_pts, fill=GOLD_LIGHT, outline=GOLD, width=1)
    # Cross-bar
    draw.rectangle(
        [cx - size * 0.15, cy - size * 0.05, cx + size * 0.15, cy + size * 0.05],
        fill=GOLD,
    )
    # Base knob
    draw.ellipse(
        [cx - size * 0.08, cy + size * 0.35, cx + size * 0.08, cy + size * 0.50],
        fill=GOLD_LIGHT,
        outline=GOLD,
        width=1,
    )


def draw_cup_symbol(draw, cx, cy, size, color=SILVER):
    """Draw a stylised chalice/cup."""
    # Bowl
    bowl_w = size * 0.35
    bowl_h = size * 0.25
    draw.ellipse(
        [cx - bowl_w, cy - size * 0.3, cx + bowl_w, cy + size * 0.05],
        outline=SILVER_LIGHT,
        width=3,
    )
    draw.ellipse(
        [cx - bowl_w, cy - size * 0.3, cx + bowl_w, cy + size * 0.05],
        outline=(180, 190, 220),
        width=1,
    )
    # Stem
    draw.rectangle(
        [cx - size * 0.03, cy + size * 0.02, cx + size * 0.03, cy + size * 0.30],
        fill=SILVER_LIGHT,
    )
    # Base
    draw.ellipse(
        [cx - size * 0.12, cy + size * 0.25, cx + size * 0.12, cy + size * 0.40],
        outline=SILVER_LIGHT,
        width=3,
    )
    # Water/wave inside cup
    wave_y = cy - size * 0.18
    draw.arc(
        [cx - bowl_w * 0.7, wave_y - 5, cx + bowl_w * 0.7, wave_y + 5],
        start=0, end=180, fill=(100, 180, 255), width=2,
    )
    draw.arc(
        [cx - bowl_w * 0.5, wave_y + 3, cx + bowl_w * 0.5, wave_y + 10],
        start=0, end=180, fill=(100, 180, 255), width=1,
    )


def draw_sword_symbol(draw, cx, cy, size, color=PALE_GOLD):
    """Draw a stylised sword blade."""
    # Blade
    blade_pts = [
        (cx, cy - size * 0.55),
        (cx - size * 0.06, cy - size * 0.05),
        (cx - size * 0.02, cy - size * 0.05),
        (cx - size * 0.02, cy + size * 0.35),
        (cx + size * 0.02, cy + size * 0.35),
        (cx + size * 0.02, cy - size * 0.05),
        (cx + size * 0.06, cy - size * 0.05),
    ]
    draw.polygon(blade_pts, fill=PALE_GOLD, outline=SILVER_LIGHT, width=1)
    # Cross guard
    draw.rectangle(
        [cx - size * 0.12, cy - size * 0.05, cx + size * 0.12, cy + size * 0.02],
        fill=SILVER,
        outline=SILVER_LIGHT,
        width=1,
    )
    # Pommel
    draw.ellipse(
        [cx - size * 0.04, cy + size * 0.35, cx + size * 0.04, cy + size * 0.42],
        fill=SILVER,
        outline=SILVER_LIGHT,
        width=1,
    )


def draw_pentacle_symbol(draw, cx, cy, size, color=GOLD):
    """Draw a pentacle/coin with a 5-pointed star inside."""
    # Outer circle
    draw.ellipse(
        [cx - size * 0.30, cy - size * 0.30, cx + size * 0.30, cy + size * 0.30],
        outline=GOLD,
        width=3,
    )
    draw.ellipse(
        [cx - size * 0.28, cy - size * 0.28, cx + size * 0.28, cy + size * 0.28],
        outline=GOLD_LIGHT,
        width=1,
    )
    # Inner star
    draw_star(
        draw, cx, cy,
        size * 0.20, size * 0.08,
        5, GOLD_LIGHT,
        width=2,
        rotation=0,
    )
    # Dot in center
    draw.ellipse(
        [cx - 3, cy - 3, cx + 3, cy + 3],
        fill=GOLD_LIGHT,
    )


# ---------------------------------------------------------------------------
# Flame / Wave / Angular / Circular decorative patterns
# ---------------------------------------------------------------------------

def draw_flame_pattern(draw, cx, cy, size):
    """Flame-like geometric pattern for Wands."""
    random.seed(int(cx + cy * size))
    n_flames = 7
    for i in range(n_flames):
        angle = 2 * math.pi * i / n_flames + random.random() * 0.2
        r = size * (0.3 + 0.15 * math.sin(i * 2.3))
        px = cx + math.cos(angle) * r
        py = cy + math.sin(angle) * r
        # Tear-drop / flame shape
        flame_len = size * 0.2
        end_angle = angle + math.pi * 0.3
        draw.ellipse(
            [
                px - flame_len * 0.15,
                py - flame_len,
                px + flame_len * 0.15,
                py,
            ],
            fill=(
                min(255, GOLD[0] + 30),
                max(0, GOLD[1] - 40),
                max(0, GOLD[2] - 30),
                80,
            ),
            outline=None,
        )
        # Connecting line to center
        draw.line(
            [(cx, cy), (px, py)],
            fill=(GOLD_RICH[0], GOLD_RICH[1], GOLD_RICH[2], 60),
            width=1,
        )


def draw_wave_pattern(draw, cx, cy, size):
    """Flowing wave-like pattern for Cups."""
    for r in range(int(size * 0.2), int(size * 0.8), 15):
        points = []
        for x in range(-r, r, 2):
            angle = x / r * math.pi * 2
            y_offset = int(8 * math.sin(x * 0.15 + r * 0.05))
            if abs(x) < r * 0.9:
                points.append((cx + x, cy + y_offset + int(math.sqrt(max(0, r * r - x * x)) * 0.3)))
        if len(points) > 1:
            draw.line(
                points,
                fill=(100, 180, 255, 30 + int(20 * math.sin(r * 0.1))),
                width=2,
            )


def draw_angular_pattern(draw, cx, cy, size):
    """Sharp angular crystalline pattern for Swords."""
    random.seed(int(cx + cy * 10))
    n_angles = 12
    for i in range(n_angles):
        base_angle = 2 * math.pi * i / n_angles + 0.1
        r1 = size * 0.2
        r2 = size * (0.4 + 0.15 * math.sin(i * 1.7))
        x1 = cx + math.cos(base_angle) * r1
        y1 = cy + math.sin(base_angle) * r1
        x2 = cx + math.cos(base_angle + 0.15) * r2
        y2 = cy + math.sin(base_angle + 0.15) * r2
        draw.line(
            [(x1, y1), (x2, y2)],
            fill=(180, 180, 200, 60 + i * 5),
            width=2,
        )
        # Cross-connect
        if i > 0:
            prev_angle = 2 * math.pi * (i - 1) / n_angles + 0.1
            px2 = cx + math.cos(prev_angle + 0.15) * (size * (0.4 + 0.15 * math.sin((i - 1) * 1.7)))
            py2 = cy + math.sin(prev_angle + 0.15) * (size * (0.4 + 0.15 * math.sin((i - 1) * 1.7)))
            draw.line(
                [(x2, y2), (px2, py2)],
                fill=(160, 160, 190, 40),
                width=1,
            )


def draw_circular_pattern(draw, cx, cy, size):
    """Solid circular geometric pattern for Pentacles."""
    # Dense concentric circles with alternating styles
    for i in range(1, 8):
        r = size * i / 8
        if i % 2 == 0:
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                outline=(GOLD_RICH[0], GOLD_RICH[1], GOLD_RICH[2], 40 + i * 10),
                width=2,
            )
        else:
            # Dashed-effect using arcs
            for a in range(0, 360, 30):
                draw.arc(
                    [cx - r, cy - r, cx + r, cy + r],
                    start=a, end=a + 15,
                    fill=(GOLD[0], GOLD[1], GOLD[2], 50 + i * 8),
                    width=1,
                )


# ---------------------------------------------------------------------------
# Card generation functions
# ---------------------------------------------------------------------------

def generate_major_arcana(fonts):
    """Generate all 22 Major Arcana cards."""
    for num, name_zh, name_en in MAJOR_ARCANA:
        print(f"  Major Arcana {num:2d}: {name_zh} ({name_en})")
        img = create_card_base(
            CARD_W, CARD_H, CORNER_RADIUS,
            MAJOR_BG_TOP, MAJOR_BG_CENTER, MAJOR_BG_BOTTOM,
        )
        draw = ImageDraw.Draw(img)

        # Border
        draw_gold_border(draw, CARD_W, CARD_H, CORNER_RADIUS)

        # Interior area
        ix0, iy0 = INTERIOR_X0 + 6, INTERIOR_Y0 + 6
        ix1, iy1 = INTERIOR_X1 - 6, INTERIOR_Y1 - 6

        # Corner filigree
        draw_corner_filigree(draw, CARD_W, CARD_H)

        # Roman numeral at top
        roman = ROMAN_NUMERALS[num] if num > 0 else "0"
        font_key = "roman_36" if num < 10 else "roman_32" if num < 20 else "roman_28"
        bbox = draw.textbbox((0, 0), roman, font=fonts[font_key])
        tx = (CARD_W - (bbox[2] - bbox[0])) // 2
        draw.text(
            (tx, INTERIOR_Y0 + 10),
            roman,
            fill=GOLD_LIGHT,
            font=fonts[font_key],
        )

        # Mandala in center
        center_y = iy0 + (iy1 - iy0) * 0.38
        draw_mandala(draw, CARD_W // 2, int(center_y), int((iy1 - iy0) * 0.38), seed=num)

        # Card name at bottom
        # Chinese
        bbox_zh = draw.textbbox((0, 0), name_zh, font=fonts["zh_28"])
        tx_zh = (CARD_W - (bbox_zh[2] - bbox_zh[0])) // 2
        name_y = INTERIOR_Y1 - 50
        draw.text((tx_zh, name_y), name_zh, fill=GOLD_LIGHT, font=fonts["zh_28"])

        # English subtitle
        bbox_en = draw.textbbox((0, 0), name_en, font=fonts["en_18"])
        tx_en = (CARD_W - (bbox_en[2] - bbox_en[0])) // 2
        draw.text((tx_en, name_y + 30), name_en, fill=(180, 160, 80), font=fonts["en_18"])

        # Render and save
        img = rounded_corners(img, CORNER_RADIUS)
        fname = f"major_{num:02d}_{name_en.lower().replace(' ', '_')}.png"
        img.save(OUTPUT_DIR / fname, "PNG")


def generate_minor_arcana(fonts):
    """Generate all 56 Minor Arcana cards across 4 suits."""
    suits = [
        ("wands", WANDS, WANDS_BG_TOP, WANDS_BG_CENTER, WANDS_BG_BOTTOM, "WANDS"),
        ("cups", CUPS, CUPS_BG_TOP, CUPS_BG_CENTER, CUPS_BG_BOTTOM, "CUPS"),
        ("swords", SWORDS, SWORDS_BG_TOP, SWORDS_BG_CENTER, SWORDS_BG_BOTTOM, "SWORDS"),
        ("pentacles", PENTACLES, PENT_BG_TOP, PENT_BG_CENTER, PENT_BG_BOTTOM, "PENTACLES"),
    ]

    for suit_name, cards, bg_top, bg_center, bg_bottom, suit_id in suits:
        for rank_idx, (name_zh, name_en) in enumerate(cards):
            card_num = rank_idx + 1
            print(f"  {suit_name.title():10s} {card_num:2d}/{len(cards)}: {name_zh} ({name_en})")

            img = create_card_base(
                CARD_W, CARD_H, CORNER_RADIUS,
                bg_top, bg_center, bg_bottom,
            )
            draw = ImageDraw.Draw(img)

            # Border
            draw_gold_border(draw, CARD_W, CARD_H, CORNER_RADIUS)

            ix0, iy0 = INTERIOR_X0 + 6, INTERIOR_Y0 + 6
            ix1, iy1 = INTERIOR_X1 - 6, INTERIOR_Y1 - 6

            # Rank display
            rank_display = str(rank_idx) if rank_idx <= 10 else ["P", "Kn", "Q", "K"][rank_idx - 11]
            font_key = "roman_32" if rank_idx <= 10 else "roman_28"
            bbox = draw.textbbox((0, 0), rank_display, font=fonts[font_key])
            draw.text(
                ((CARD_W - (bbox[2] - bbox[0])) // 2, INTERIOR_Y0 + 12),
                rank_display,
                fill=GOLD_LIGHT,
                font=fonts[font_key],
            )

            # Suit pattern in background
            center_x, center_y = CARD_W // 2, int(iy0 + (iy1 - iy0) * 0.38)
            if suit_name == "wands":
                draw_flame_pattern(draw, center_x, center_y, int((iy1 - iy0) * 0.35))
            elif suit_name == "cups":
                draw_wave_pattern(draw, center_x, center_y, int((iy1 - iy0) * 0.35))
            elif suit_name == "swords":
                draw_angular_pattern(draw, center_x, center_y, int((iy1 - iy0) * 0.35))
            elif suit_name == "pentacles":
                draw_circular_pattern(draw, center_x, center_y, int((iy1 - iy0) * 0.35))

            # Suit symbol in center
            symbol_size = int((iy1 - iy0) * 0.20)
            if suit_name == "wands":
                draw_wand_symbol(draw, center_x, center_y, symbol_size)
            elif suit_name == "cups":
                draw_cup_symbol(draw, center_x, center_y, symbol_size)
            elif suit_name == "swords":
                draw_sword_symbol(draw, center_x, center_y, symbol_size)
            elif suit_name == "pentacles":
                draw_pentacle_symbol(draw, center_x, center_y, symbol_size)

            # Simple geometric border inside card
            border_margin = 15
            draw.rounded_rectangle(
                [
                    ix0 + border_margin,
                    iy0 + border_margin,
                    ix1 - border_margin,
                    iy1 - border_margin,
                ],
                radius=12,
                outline=(GOLD_RICH[0], GOLD_RICH[1], GOLD_RICH[2], 60),
                width=1,
            )

            # Card name at bottom
            name_y = INTERIOR_Y1 - 50
            bbox_zh = draw.textbbox((0, 0), name_zh, font=fonts["zh_28"])
            tx_zh = (CARD_W - (bbox_zh[2] - bbox_zh[0])) // 2
            draw.text((tx_zh, name_y), name_zh, fill=GOLD_LIGHT, font=fonts["zh_28"])

            bbox_en = draw.textbbox((0, 0), name_en, font=fonts["en_18"])
            tx_en = (CARD_W - (bbox_en[2] - bbox_en[0])) // 2
            draw.text((tx_en, name_y + 30), name_en, fill=(180, 160, 80), font=fonts["en_18"])

            # Render and save
            img = rounded_corners(img, CORNER_RADIUS)
            safe_en = name_en.lower().replace(" ", "_").replace("/", "_")
            fname = f"{suit_name}_{rank_idx:02d}_{safe_en}.png"
            img.save(OUTPUT_DIR / fname, "PNG")


# ---------------------------------------------------------------------------
# Preview HTML
# ---------------------------------------------------------------------------

def create_preview_html():
    """Create an HTML page that displays all 78 cards in a grid."""
    cards = []
    for num, name_zh, name_en in MAJOR_ARCANA:
        fname = f"major_{num:02d}_{name_en.lower().replace(' ', '_')}.png"
        cards.append((fname, name_zh, name_en, "major"))

    for suit_name, cards_list, *_ in [
        ("wands", WANDS),
        ("cups", CUPS),
        ("swords", SWORDS),
        ("pentacles", PENTACLES),
    ]:
        for rank_idx, (name_zh, name_en) in enumerate(cards_list):
            safe_en = name_en.lower().replace(" ", "_").replace("/", "_")
            fname = f"{suit_name}_{rank_idx:02d}_{safe_en}.png"
            cards.append((fname, name_zh, name_en, suit_name))

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>塔罗牌预览 - 78张</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #0a0a1a;
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    color: #d4af37;
    padding: 20px;
}
h1 { text-align: center; font-size: 2em; margin-bottom: 10px; color: #f5d83b; text-shadow: 0 0 20px rgba(212,175,55,0.3); }
p.subtitle { text-align: center; color: #888; margin-bottom: 30px; }
.section { margin-bottom: 40px; }
.section h2 {
    font-size: 1.4em;
    margin-bottom: 15px;
    padding-bottom: 8px;
    border-bottom: 1px solid #d4af37;
    text-shadow: 0 0 10px rgba(212,175,55,0.2);
}
.card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 16px;
}
.card-item {
    background: #111;
    border-radius: 10px;
    overflow: hidden;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
    border: 1px solid #333;
}
.card-item:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 25px rgba(212,175,55,0.25);
    border-color: #d4af37;
}
.card-item img {
    width: 100%;
    height: auto;
    display: block;
}
.card-label {
    padding: 6px 4px;
    font-size: 12px;
    color: #ccc;
    line-height: 1.4;
    background: #0d0d1a;
}
.card-label .zh { font-size: 14px; color: #f5d83b; }
.card-label .en { font-size: 11px; color: #999; }
.suit-major .card-item { border-color: #4a2a6a; }
.suit-wands .card-item { border-color: #6a2a1a; }
.suit-cups .card-item { border-color: #1a3a6a; }
.suit-swords .card-item { border-color: #4a4a5a; }
.suit-pentacles .card-item { border-color: #2a5a2a; }
</style>
</head>
<body>
<h1>&#x2728; 塔罗牌 78张完全预览</h1>
<p class="subtitle">Tarot Deck - All 78 Cards</p>
"""

    sections = [
        ("major", "大阿尔卡纳 Major Arcana (22张)", "suit-major"),
        ("wands", "权杖 Wands (14张)", "suit-wands"),
        ("cups", "圣杯 Cups (14张)", "suit-cups"),
        ("swords", "宝剑 Swords (14张)", "suit-swords"),
        ("pentacles", "星币 Pentacles (14张)", "suit-pentacles"),
    ]

    for section_id, section_title, section_class in sections:
        html += f'<div class="section {section_class}">\n'
        html += f'  <h2>{section_title}</h2>\n'
        html += '  <div class="card-grid">\n'
        for fname, name_zh, name_en, suit in cards:
            if suit != section_id and not (section_id == "major" and suit == "major"):
                if section_id == "major" and suit != "major":
                    continue
                if section_id != "major" and suit != section_id:
                    continue
            html += '    <div class="card-item">\n'
            html += f'      <img src="{fname}" alt="{name_zh}">\n'
            html += '      <div class="card-label">\n'
            html += f'        <div class="zh">{name_zh}</div>\n'
            html += f'        <div class="en">{name_en}</div>\n'
            html += '      </div>\n'
            html += '    </div>\n'
        html += '  </div>\n'
        html += '</div>\n'

    html += """</body>
</html>"""

    (OUTPUT_DIR / "preview.html").write_text(html, encoding="utf-8")
    print(f"  Preview HTML written to {OUTPUT_DIR / 'preview.html'}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Tarot Card Image Generator")
    print("=" * 60)
    print()

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load fonts
    print("[1/4] Loading fonts...")
    fonts = get_fonts()
    print(f"  Using font: {FONT_PATH_WQY}")
    print()

    # Generate Major Arcana
    print(f"[2/4] Generating Major Arcana ({len(MAJOR_ARCANA)} cards)...")
    generate_major_arcana(fonts)
    print()

    # Generate Minor Arcana
    total_minor = len(WANDS) + len(CUPS) + len(SWORDS) + len(PENTACLES)
    print(f"[3/4] Generating Minor Arcana ({total_minor} cards)...")
    generate_minor_arcana(fonts)
    print()

    # Verify
    print("[4/4] Verifying output...")
    generated = list(OUTPUT_DIR.glob("*.png"))
    print(f"  Found {len(generated)} PNG files in {OUTPUT_DIR}")

    # Count expected
    expected = 22 + 56  # 78
    if len(generated) == expected:
        print(f"  SUCCESS: All {expected} card images generated!")
    else:
        print(f"  WARNING: Expected {expected} cards, found {len(generated)}")

    # Create preview HTML
    print("  Creating preview HTML...")
    create_preview_html()
    print()

    print("=" * 60)
    print("  Generation complete!")
    print(f"  Output directory: {OUTPUT_DIR}")
    print(f"  Preview: {OUTPUT_DIR / 'preview.html'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
