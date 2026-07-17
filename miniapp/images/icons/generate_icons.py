#!/usr/bin/env python3
"""
Premium tarot mini-app icon generator.
All icons: 256x256 RGBA -> downscale to 64x64 with LANCZOS.
Gold palette: #F4D48C (main), #FFF0C8 (light), #D4A84B (dark), #C89B3C (shadow)
"""

import os, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = "/mnt/e/tarot-miniapp/miniapp/images/icons"
S = 256  # source size

GOLD = (244, 212, 140)
GOLD_LIGHT = (255, 240, 200)
GOLD_DIM = (212, 168, 75)
GOLD_TRANS = (244, 212, 140, 60)   # inner glow
GOLD_TRANS2 = (244, 212, 140, 30)  # wider glow
WHITE = (255, 255, 255, 200)

def make_base():
    """Return a blank RGBA image."""
    return Image.new("RGBA", (S, S), (0,0,0,0))

def glow(d, cx, cy, r, alpha=60):
    """Draw a soft circular glow behind shapes."""
    g = Image.new("RGBA", (S, S), (0,0,0,0))
    gd = ImageDraw.Draw(g)
    for i in range(6, 0, -1):
        a = max(5, alpha - i * 8)
        gd.ellipse([cx - r - i, cy - r - i, cx + r + i, cy + r + i],
                    fill=(244, 212, 140, a), outline=None)
    d.bitmap((0, 0), g, (244, 212, 140, alpha))

def glow_soft(d, cx, cy, w, h):
    """Rectangular soft glow."""
    g = Image.new("RGBA", (S, S), (0,0,0,0))
    gd = ImageDraw.Draw(g)
    for i in range(8, 0, -1):
        a = max(3, 40 - i * 4)
        gd.rounded_rectangle([cx - w - i, cy - h - i, cx + w + i, cy + h + i],
                             radius=12, fill=(244, 212, 140, a))
    d.bitmap((0, 0), g, (244, 212, 140, 40))

def highlight_dot(d, x, y, r=4):
    """Small bright accent dot."""
    d.ellipse([x - r, y - r, x + r, y + r], fill=GOLD_LIGHT)

def set_stroke(d, shape_fn, width=3, fill=None, outline=GOLD):
    """Draw a shape multiple times with offset to simulate stroke."""
    if fill is not None:
        shape_fn(fill=fill, outline=outline, width=width)
    else:
        shape_fn(outline=outline, width=width)

# ─── 1. DIARY ───
def make_diary():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    # glow
    glow_soft(d, cx, cy, 70, 60)

    # Open book: two pages curving slightly
    # Left page
    left = [(cx-5, cy+70), (cx-80, cy+55), (cx-78, cy-50), (cx-2, cy-40)]
    right = [(cx+5, cy+70), (cx+80, cy+55), (cx+78, cy-50), (cx+2, cy-40)]

    # Left page fill with slight gold tint
    d.polygon(left, fill=(244, 212, 140, 25), outline=GOLD, width=3)
    # Right page fill
    d.polygon(right, fill=(244, 212, 140, 25), outline=GOLD, width=3)

    # Spine line
    d.line([(cx, cy+72), (cx, cy-38)], fill=GOLD, width=3)

    # Page lines on left
    for i, y in enumerate([cy-10, cy+15, cy+40]):
        d.line([(cx-8, y), (cx-60, y-3)], fill=GOLD, width=2)
    # Page lines on right
    for i, y in enumerate([cy-10, cy+15, cy+40]):
        d.line([(cx+8, y), (cx+60, y-3)], fill=GOLD, width=2)

    # Ribbon bookmark
    ribbon = [(cx-5, cy+40), (cx+10, cy+50), (cx+5, cy+75), (cx+15, cy+85),
              (cx+10, cy+95), (cx, cy+82), (cx-5, cy+85), (cx-10, cy+75),
              (cx-2, cy+55)]
    d.polygon(ribbon, fill=(255, 240, 200, 180), outline=GOLD_LIGHT, width=2)

    # Highlight dots
    highlight_dot(d, cx-50, cy-20, 3)
    highlight_dot(d, cx+50, cy-20, 3)
    highlight_dot(d, cx, cy-38, 3)

    return im

# ─── 2. MEMBER (Crown) ───
def make_member():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow_soft(d, cx, cy, 55, 50)

    # Crown base: a band
    d.rounded_rectangle([cx-75, cy+20, cx+75, cy+50], radius=8, fill=(244,212,140,20), outline=GOLD, width=3)

    # Three points
    # Center point (tallest)
    d.polygon([
        (cx-20, cy+20), (cx, cy-60), (cx+20, cy+20)
    ], fill=None, outline=GOLD, width=3)
    # Left point
    d.polygon([
        (cx-40, cy+20), (cx-55, cy-35), (cx-25, cy+20)
    ], fill=None, outline=GOLD, width=3)
    # Right point
    d.polygon([
        (cx+40, cy+20), (cx+55, cy-35), (cx+25, cy+20)
    ], fill=None, outline=GOLD, width=3)

    # Jewels at top of each point
    highlight_dot(d, cx, cy-60, 6)   # center jewel
    highlight_dot(d, cx-55, cy-35, 5)
    highlight_dot(d, cx+55, cy-35, 5)

    # Base jewels on band
    highlight_dot(d, cx-55, cy+35, 4)
    highlight_dot(d, cx, cy+35, 4)
    highlight_dot(d, cx+55, cy+35, 4)

    # Decorative arches between points
    d.arc([cx-60, cy-30, cx-20, cy+15], 180, 0, fill=GOLD, width=2)
    d.arc([cx+20, cy-30, cx+60, cy+15], 180, 0, fill=GOLD, width=2)

    return im

# ─── 3. REPORT ───
def make_report():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow_soft(d, cx, cy, 65, 55)

    # Three bars (y0 < y1: top < bottom)
    bars = [
        (cx-65, cy-20, cx-45, cy+40),   # shortest (left)
        (cx-25, cy-55, cx-5, cy+40),     # tallest (center)
        (cx+15, cy-10, cx+35, cy+40),    # medium (right)
    ]
    for x0, y0, x1, y1 in bars:
        d.rounded_rectangle([x0, y0, x1, y1], radius=6, fill=(244,212,140,25), outline=GOLD, width=3)
        # subtle fill
        d.rounded_rectangle([x0+4, y0+4, x1-4, y1-2], radius=4, fill=(244,212,140,35), outline=None)

    # Trend arrow going up-right from top of tallest bar (center bar)
    arrow_start = (cx-5, cy-55)
    arrow_tip = (cx+55, cy-75)
    # Arrow line
    d.line([arrow_start, arrow_tip], fill=GOLD, width=3)
    # Line segment (horizontal rule)
    d.line([(cx+15, cy-60), (cx+55, cy-75)], fill=GOLD_LIGHT, width=2)
    # Arrowhead
    d.polygon([
        (cx+55, cy-75), (cx+40, cy-68), (cx+48, cy-58)
    ], fill=None, outline=GOLD, width=2)

    # Baseline
    d.line([(cx-75, cy+40), (cx+75, cy+40)], fill=GOLD, width=2)

    # Highlight dots on top of each bar
    for x0, y0, x1, y1 in bars:
        highlight_dot(d, (x0+x1)//2, y0-3, 3)

    return im

# ─── 4. HISTORY (Scroll) ───
def make_history():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow_soft(d, cx, cy, 55, 70)

    # Main scroll body
    d.rounded_rectangle([cx-65, cy-45, cx+65, cy+55], radius=10, fill=(244,212,140,20), outline=GOLD, width=3)

    # Top roll
    d.ellipse([cx-68, cy-65, cx-38, cy-35], fill=(244,212,140,30), outline=GOLD, width=3)
    d.ellipse([cx+38, cy-65, cx+68, cy-35], fill=(244,212,140,30), outline=GOLD, width=3)
    # Connector line top
    d.line([cx-43, cy-50, cx+43, cy-50], fill=GOLD, width=3)

    # Bottom roll
    d.ellipse([cx-68, cy+35, cx-38, cy+65], fill=(244,212,140,30), outline=GOLD, width=3)
    d.ellipse([cx+38, cy+35, cx+68, cy+65], fill=(244,212,140,30), outline=GOLD, width=3)
    d.line([cx-43, cy+50, cx+43, cy+50], fill=GOLD, width=3)

    # Text lines
    for i, y_off in enumerate([-15, 5, 25]):
        d.line([(cx-45, cy+y_off), (cx+45, cy+y_off)], fill=GOLD, width=2 if i < 2 else 2)

    # Small decorative dot left of text
    highlight_dot(d, cx-55, cy-15, 2)
    highlight_dot(d, cx-55, cy+5, 2)
    highlight_dot(d, cx-55, cy+25, 2)

    return im

# ─── 5. ABOUT ───
def make_about():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    # Outer circle
    d.ellipse([cx-65, cy-65, cx+65, cy+65], fill=(244,212,140,15), outline=GOLD, width=3)

    # Inner circle ring
    d.ellipse([cx-55, cy-55, cx+55, cy+55], fill=None, outline=GOLD_DIM, width=1)

    # Letter 'i' - serif style
    # Body of i
    d.rectangle([cx-3, cy-5, cx+3, cy+35], fill=GOLD, width=0)
    # Dot of i
    highlight_dot(d, cx, cy-20, 5)

    # Orbiting decorative dots
    for angle in [30, 90, 150, 210, 270, 330]:
        rad = math.radians(angle)
        r = 48
        dx = int(cx + r * math.cos(rad))
        dy = int(cy + r * math.sin(rad))
        d.ellipse([dx-2, dy-2, dx+2, dy+2], fill=GOLD_LIGHT)

    # Larger orbiting dots
    for angle in [60, 180, 300]:
        rad = math.radians(angle)
        r = 42
        dx = int(cx + r * math.cos(rad))
        dy = int(cy + r * math.sin(rad))
        highlight_dot(d, dx, dy, 3)

    return im

# ─── 6. HOME TAB ───
def make_home_tab():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow_soft(d, cx, cy, 55, 55)

    # Roof (pointy triangle)
    d.polygon([
        (cx, cy-55),
        (cx-70, cy+5),
        (cx+70, cy+5)
    ], fill=(244,212,140,20), outline=GOLD, width=3)

    # House body
    d.rounded_rectangle([cx-55, cy+5, cx+55, cy+60], radius=6, fill=(244,212,140,20), outline=GOLD, width=3)

    # Door
    d.rounded_rectangle([cx-15, cy+22, cx+15, cy+60], radius=4, fill=(244,212,140,30), outline=GOLD, width=2)

    # Door knob
    highlight_dot(d, cx+8, cy+42, 3)

    # Windows
    # Left window
    d.rounded_rectangle([cx-45, cy+12, cx-22, cy+35], radius=3, fill=(244,212,140,25), outline=GOLD, width=2)
    # Right window
    d.rounded_rectangle([cx+22, cy+12, cx+45, cy+35], radius=3, fill=(244,212,140,25), outline=GOLD, width=2)

    # Cross in left window
    d.line([(cx-33, cy+12), (cx-33, cy+35)], fill=GOLD, width=1)
    d.line([(cx-45, cy+23), (cx-22, cy+23)], fill=GOLD, width=1)
    # Cross in right window
    d.line([(cx+33, cy+12), (cx+33, cy+35)], fill=GOLD, width=1)
    d.line([(cx+22, cy+23), (cx+45, cy+23)], fill=GOLD, width=1)

    # Star above roof
    star_cx, star_cy = cx, cy-70
    star_pts = []
    for i in range(10):
        a = math.radians(-90 + i * 36)
        r = 10 if i % 2 == 0 else 5
        star_pts.append((star_cx + r * math.cos(a), star_cy + r * math.sin(a)))
    d.polygon(star_pts, fill=None, outline=GOLD, width=2)
    highlight_dot(d, star_cx, star_cy, 2)

    return im

# ─── 7. ENCYCLOPEDIA TAB ───
def make_encyclopedia_tab():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow_soft(d, cx, cy, 60, 50)

    # Three overlapping cards (playing card style, overlapping right-up)
    offsets = [(-18, -12), (0, 0), (18, 12)]
    for i, (dx, dy) in enumerate(offsets):
        card_x1 = cx - 40 + dx
        card_y1 = cy - 55 + dy
        card_x2 = cx + 40 + dx
        card_y2 = cy + 55 + dy
        # Fill for middle card, outline for all
        fill = (244,212,140,25) if i == 1 else (244,212,140,10)
        d.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=8,
                           fill=fill, outline=GOLD, width=3 if i == 1 else 2)

    # Center card details: small decorative corner symbols
    d.arc([cx-28, cy-42, cx-18, cy-32], 180, 270, fill=GOLD, width=2)
    d.arc([cx+18, cy+32, cx+28, cy+42], 0, 90, fill=GOLD, width=2)

    # Center ornament on middle card
    d.ellipse([cx-8, cy-8, cx+8, cy+8], fill=(244,212,140,30), outline=GOLD, width=2)
    highlight_dot(d, cx, cy, 3)

    return im

# ─── 8. PROFILE TAB ───
def make_profile_tab():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow_soft(d, cx, cy, 50, 70)

    # Head (circle)
    d.ellipse([cx-30, cy-55, cx+30, cy+5], fill=(244,212,140,15), outline=GOLD, width=3)

    # Elegant neck curve
    d.arc([cx-20, cy-10, cx+20, cy+30], 200, 340, fill=GOLD, width=3)

    # Body / shoulders - flowing curve
    # Left shoulder
    d.arc([cx-90, cy-5, cx+10, cy+70], 270, 360, fill=GOLD, width=3)
    # Right shoulder
    d.arc([cx-10, cy-5, cx+90, cy+70], 180, 270, fill=GOLD, width=3)

    # Connecting neck to shoulders
    d.line([(cx-18, cy+15), (cx-55, cy+30)], fill=GOLD, width=3)
    d.line([(cx+18, cy+15), (cx+55, cy+30)], fill=GOLD, width=3)

    # Profile facial features (facing right)
    # Subtle nose profile
    d.arc([cx+5, cy-40, cx+40, cy-5], 270, 40, fill=GOLD, width=2)
    # Eye
    highlight_dot(d, cx+18, cy-28, 2)

    # Decorative flowing hair element
    d.arc([cx-40, cy-60, cx+10, cy-15], 0, 160, fill=GOLD, width=2)

    return im

# ─── 9. THEME GENERAL (Crystal Ball) ───
def make_theme_general():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow(d, cx, cy, 50, 50)

    # Outer glow rings
    for r in [70, 80, 90]:
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=None, outline=(244,212,140,max(15, 30-r//3)), width=1)

    # Crystal ball sphere
    d.ellipse([cx-55, cy-55, cx+55, cy+55], fill=(244,212,140,12), outline=GOLD, width=3)

    # Inner star (4-pointed)
    star_cx, star_cy = cx, cy-5
    d.polygon([
        (star_cx, star_cy-30),
        (star_cx+8, star_cy-5),
        (star_cx+30, star_cy),
        (star_cx+8, star_cy+5),
        (star_cx, star_cy+30),
        (star_cx-8, star_cy+5),
        (star_cx-30, star_cy),
        (star_cx-8, star_cy-5),
    ], fill=(244,212,140,30), outline=GOLD, width=2)

    # Center highlight
    highlight_dot(d, star_cx, star_cy, 5)
    highlight_dot(d, star_cx, star_cy, 2)

    # Crystal ball base/stand
    d.rounded_rectangle([cx-40, cy+50, cx+40, cy+65], radius=6, fill=(244,212,140,20), outline=GOLD, width=3)

    # Shine highlight on sphere (upper left)
    d.ellipse([cx-38, cy-38, cx-18, cy-18], fill=(255,240,200,40), outline=None)

    # Subtle concentric rings inside
    d.ellipse([cx-30, cy-30, cx+30, cy+30], fill=None, outline=GOLD_DIM, width=1)

    return im

# ─── 10. THEME LOVE ───
def make_theme_love():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow(d, cx, cy, 45, 45)

    # Outer heart shape using two arcs + polygon
    # Heart path: two circles on top, triangle bottom
    # Left lobe
    d.ellipse([cx-50, cy-55, cx-5, cy-5], fill=(244,212,140,15), outline=GOLD, width=3)
    # Right lobe
    d.ellipse([cx+5, cy-55, cx+50, cy-5], fill=(244,212,140,15), outline=GOLD, width=3)
    # Bottom triangle
    d.polygon([
        (cx-52, cy-15),
        (cx+52, cy-15),
        (cx, cy+55)
    ], fill=(244,212,140,15), outline=GOLD, width=3)

    # Internal filigree - delicate scrollwork
    # Left spiral
    d.arc([cx-35, cy-30, cx-5, cy+10], 180, 360, fill=GOLD, width=2)
    d.arc([cx-30, cy-10, cx-8, cy+20], 0, 180, fill=GOLD, width=1)
    # Right spiral
    d.arc([cx+5, cy-30, cx+35, cy+10], 0, 180, fill=GOLD, width=2)
    d.arc([cx+8, cy-10, cx+30, cy+20], 180, 360, fill=GOLD, width=1)

    # Inner heart outline
    d.polygon([
        (cx-15, cy-5),
        (cx, cy-18),
        (cx+15, cy-5),
        (cx, cy+25)
    ], fill=None, outline=GOLD_LIGHT, width=2)

    # Center highlight
    highlight_dot(d, cx, cy-5, 4)
    highlight_dot(d, cx-25, cy-30, 2)
    highlight_dot(d, cx+25, cy-30, 2)

    return im

# ─── 11. THEME CAREER ───
def make_theme_career():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow_soft(d, cx, cy, 55, 45)

    # Briefcase body
    d.rounded_rectangle([cx-60, cy-15, cx+60, cy+55], radius=10, fill=(244,212,140,15), outline=GOLD, width=3)

    # Handle
    d.rounded_rectangle([cx-25, cy-35, cx+25, cy-10], radius=8, fill=None, outline=GOLD, width=3)
    # Handle inner cutout area
    d.rounded_rectangle([cx-18, cy-32, cx+18, cy-13], radius=6, fill=None, outline=GOLD, width=2)

    # Gold trim line across middle
    d.line([(cx-55, cy+18), (cx+55, cy+18)], fill=GOLD, width=2)

    # Lock/clasp
    d.rounded_rectangle([cx-8, cy+12, cx+8, cy+25], radius=3, fill=(244,212,140,30), outline=GOLD, width=2)
    highlight_dot(d, cx, cy+18, 2)

    # Detail lines on bottom half
    d.line([(cx-45, cy+32), (cx-10, cy+32)], fill=GOLD, width=1)
    d.line([(cx+10, cy+32), (cx+45, cy+32)], fill=GOLD, width=1)
    d.line([(cx-45, cy+42), (cx-10, cy+42)], fill=GOLD, width=1)
    d.line([(cx+10, cy+42), (cx+45, cy+42)], fill=GOLD, width=1)

    # Highlight dots
    highlight_dot(d, cx, cy-22, 3)
    highlight_dot(d, cx-40, cy+5, 3)
    highlight_dot(d, cx+40, cy+5, 3)

    return im

# ─── 12. THEME FINANCE ───
def make_theme_finance():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow(d, cx, cy, 50, 50)

    # Outer coin circle
    d.ellipse([cx-60, cy-60, cx+60, cy+60], fill=(244,212,140,12), outline=GOLD, width=3)

    # Inner decorative ring
    d.ellipse([cx-50, cy-50, cx+50, cy+50], fill=None, outline=GOLD_DIM, width=1)

    # Inner ring (intermediate)
    d.ellipse([cx-35, cy-35, cx+35, cy+35], fill=None, outline=GOLD, width=2)

    # 5-pointed star (pentacle)
    star = []
    for i in range(5):
        a = math.radians(-90 + i * 72)
        star.append((cx + 28 * math.cos(a), cy + 28 * math.sin(a)))
    for i in range(5):
        a = math.radians(-90 + (i+2) * 72)
        star.append((cx + 28 * math.cos(a), cy + 28 * math.sin(a)))

    # Draw pentagram (star)
    for i in range(5):
        idx1 = i
        idx2 = 5 + ((i + 1) % 5)
        d.line([star[idx1], star[idx2]], fill=GOLD, width=2)
        idx3 = 5 + i
        d.line([star[idx3], star[(i + 1) % 5]], fill=GOLD, width=2)

    # Inner circle (center)
    d.ellipse([cx-8, cy-8, cx+8, cy+8], fill=(244,212,140,40), outline=GOLD, width=2)
    highlight_dot(d, cx, cy, 3)

    # Decorative dots on outer ring
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        r = 55
        dx = int(cx + r * math.cos(rad))
        dy = int(cy + r * math.sin(rad))
        d.ellipse([dx-2, dy-2, dx+2, dy+2], fill=GOLD_LIGHT)

    return im

# ─── 13. CHAT ASK ───
def make_chat_ask():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow_soft(d, cx-5, cy-5, 50, 45)

    # Speech bubble (rounded rect with tail)
    d.rounded_rectangle([cx-55, cy-50, cx+55, cy+40], radius=15, fill=(244,212,140,15), outline=GOLD, width=3)

    # Tail
    d.polygon([
        (cx-25, cy+40),
        (cx-40, cy+65),
        (cx-5, cy+40),
    ], fill=(244,212,140,15), outline=GOLD, width=3)

    # Question mark
    # Curve of question mark
    d.arc([cx-20, cy-38, cx+10, cy-8], 0, 270, fill=GOLD, width=3)
    # Stem
    d.line([(cx-5, cy-8), (cx-5, cy+5)], fill=GOLD, width=3)
    # Dot
    highlight_dot(d, cx-5, cy+15, 4)

    # Highlight accent
    highlight_dot(d, cx-30, cy-30, 3)

    return im

# ─── 14. REFRESH ───
def make_refresh():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow(d, cx, cy, 45, 45)

    # Main circle (dashed feel by using arc segments)
    d.ellipse([cx-50, cy-50, cx+50, cy+50], fill=None, outline=GOLD, width=3)

    # Arrow: curved path going clockwise
    # Upper-right quadrant with arrowhead
    d.arc([cx-45, cy-45, cx+45, cy+45], 30, 180, fill=GOLD, width=3)

    # Arrowhead at end (upper left area)
    end_x = int(cx + 45 * math.cos(math.radians(30)))
    end_y = int(cy + 45 * math.sin(math.radians(30)))
    # Arrowhead lines
    d.line([(end_x, end_y), (end_x-18, end_y-10)], fill=GOLD, width=3)
    d.line([(end_x, end_y), (end_x-18, end_y+10)], fill=GOLD, width=3)

    # Small accent arrow at start for balance
    start_x = int(cx + 45 * math.cos(math.radians(180)))
    start_y = int(cy + 45 * math.sin(math.radians(180)))
    d.line([(start_x, start_y), (start_x+12, start_y-8)], fill=GOLD_DIM, width=2)

    # Center accent
    highlight_dot(d, cx, cy, 3)

    return im

# ─── 15. SHARE ───
def make_share():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow_soft(d, cx, cy-10, 50, 40)

    # Box (card/square)
    d.rounded_rectangle([cx-50, cy, cx+50, cy+60], radius=8, fill=(244,212,140,15), outline=GOLD, width=3)

    # Box top open
    d.line([(cx-50, cy), (cx+50, cy)], fill=GOLD, width=3)

    # Arrow shooting upward from box
    # Stem
    d.line([(cx, cy-5), (cx, cy-55)], fill=GOLD, width=3)
    # Arrowhead
    d.polygon([
        (cx, cy-65),
        (cx-15, cy-45),
        (cx+15, cy-45)
    ], fill=None, outline=GOLD, width=3)

    # Detail lines on box
    d.line([(cx-35, cy+15), (cx+35, cy+15)], fill=GOLD, width=1)
    d.line([(cx-35, cy+30), (cx+35, cy+30)], fill=GOLD, width=1)
    d.line([(cx-35, cy+45), (cx+35, cy+45)], fill=GOLD, width=1)

    # Highlight
    highlight_dot(d, cx, cy-55, 3)

    return im

# ─── 16. ARROW LEFT / RIGHT ───
def make_arrow_left():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow(d, cx, cy, 45, 45)

    # Circle
    d.ellipse([cx-50, cy-50, cx+50, cy+50], fill=(244,212,140,15), outline=GOLD, width=3)

    # Chevron (pointing left)
    d.line([(cx+15, cy-25), (cx-20, cy), (cx+15, cy+25)], fill=GOLD, width=4, joint="curve")

    # Highlight dot
    highlight_dot(d, cx-15, cy-25, 3)

    return im

def make_arrow_right():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow(d, cx, cy, 45, 45)

    # Circle
    d.ellipse([cx-50, cy-50, cx+50, cy+50], fill=(244,212,140,15), outline=GOLD, width=3)

    # Chevron (pointing right)
    d.line([(cx-15, cy-25), (cx+20, cy), (cx-15, cy+25)], fill=GOLD, width=4, joint="curve")

    # Highlight dot
    highlight_dot(d, cx+15, cy-25, 3)

    return im

# ─── 17. START READING ───
def make_start_reading():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128

    glow(d, cx, cy, 50, 50)
    glow(d, cx, cy-20, 35, 30)

    # Magic wand handle
    d.rounded_rectangle([cx-30, cy+25, cx+30, cy+65], radius=5, fill=(244,212,140,20), outline=GOLD, width=3)

    # Wand grip rings
    d.rounded_rectangle([cx-30, cy+30, cx+30, cy+38], radius=3, fill=(244,212,140,30), outline=None)
    d.rounded_rectangle([cx-30, cy+50, cx+30, cy+58], radius=3, fill=(244,212,140,30), outline=None)

    # Wand tip (star burst)
    tip_cx, tip_cy = cx, cy-10
    # Large 4-point star at tip
    d.polygon([
        (tip_cx, tip_cy-40),
        (tip_cx+10, tip_cy-5),
        (tip_cx+35, tip_cy),
        (tip_cx+10, tip_cy+5),
        (tip_cx, tip_cy+30),
        (tip_cx-10, tip_cy+5),
        (tip_cx-35, tip_cy),
        (tip_cx-10, tip_cy-5),
    ], fill=(244,212,140,35), outline=GOLD, width=2)

    # Sparkle particles
    particles = [
        (tip_cx-20, tip_cy-25, 3),
        (tip_cx+25, tip_cy-18, 2),
        (tip_cx-28, tip_cy+10, 2),
        (tip_cx+18, tip_cy+22, 3),
        (tip_cx+40, tip_cy-8, 2),
        (tip_cx-42, tip_cy-5, 2),
    ]
    for px, py, pr in particles:
        highlight_dot(d, px, py, pr)

    # Center star highlight
    highlight_dot(d, tip_cx, tip_cy, 5)
    highlight_dot(d, tip_cx, tip_cy-20, 3)

    return im

# ─── SAVE ───
def save_icon(name, img):
    """Save as 64x64 PNG, overwriting."""
    small = img.resize((64, 64), Image.LANCZOS)
    path = os.path.join(OUT, name)
    small.save(path, "PNG")
    print(f"  Saved {name}")

# ─── MAIN ───
def main():
    os.makedirs(OUT, exist_ok=True)
    print("Generating tarot icons...\n")

    gens = [
        ("diary_64.png", make_diary),
        ("member_64.png", make_member),
        ("report_64.png", make_report),
        ("history_64.png", make_history),
        ("about_64.png", make_about),
        ("home_tab_64.png", make_home_tab),
        ("encyclopedia_tab_64.png", make_encyclopedia_tab),
        ("profile_tab_64.png", make_profile_tab),
        ("theme_general_64.png", make_theme_general),
        ("theme_love_64.png", make_theme_love),
        ("theme_career_64.png", make_theme_career),
        ("theme_finance_64.png", make_theme_finance),
        ("chat_ask_64.png", make_chat_ask),
        ("refresh_64.png", make_refresh),
        ("share_64.png", make_share),
        ("arrow_left_64.png", make_arrow_left),
        ("arrow_right_64.png", make_arrow_right),
        ("start_reading_64.png", make_start_reading),
    ]

    for name, fn in gens:
        save_icon(name, fn())
        print(f"  Done: {name}")

    print("\nAll icons generated.")

if __name__ == "__main__":
    main()
