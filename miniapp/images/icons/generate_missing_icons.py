#!/usr/bin/env python3
"""
Generate missing icons for functional emoji replacement.
All icons follow the same gold palette and 256px source -> 64px output.
Gold palette: #F4D48C (main), #FFF0C8 (light), #D4A84B (dark), #C89B3C (shadow)
"""
import os, math
from PIL import Image, ImageDraw

OUT = "/mnt/e/tarot-miniapp/miniapp/images/icons"
S = 256

GOLD = (244, 212, 140)
GOLD_LIGHT = (255, 240, 200)
GOLD_DIM = (212, 168, 75)
WHITE = (255, 255, 255, 200)

def make_base():
    return Image.new("RGBA", (S, S), (0,0,0,0))

def glow_soft(d, cx, cy, w, h):
    """Rectangular soft glow."""
    g = Image.new("RGBA", (S, S), (0,0,0,0))
    gd = ImageDraw.Draw(g)
    for i in range(8, 0, -1):
        a = max(3, 40 - i * 4)
        gd.rounded_rectangle([cx - w - i, cy - h - i, cx + w + i, cy + h + i],
                             radius=12, fill=(244, 212, 140, a))
    d.bitmap((0, 0), g, (244, 212, 140, 40))

def glow_circular(d, cx, cy, r, alpha=50):
    """Soft circular glow."""
    g = Image.new("RGBA", (S, S), (0,0,0,0))
    gd = ImageDraw.Draw(g)
    for i in range(6, 0, -1):
        a = max(5, alpha - i * 8)
        gd.ellipse([cx - r - i, cy - r - i, cx + r + i, cy + r + i],
                    fill=(244, 212, 140, a), outline=None)
    d.bitmap((0, 0), g, (244, 212, 140, alpha))

def highlight_dot(d, x, y, r=4):
    """Small bright accent dot."""
    d.ellipse([x - r, y - r, x + r, y + r], fill=GOLD_LIGHT)

# ─── 1. STAR ─── (for ✦ badges, pending readings, buttons)
def make_star():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128
    glow_circular(d, cx, cy, 45, 45)

    # 4-pointed star (diamond star)
    pts = []
    for i in range(8):
        a = math.radians(-90 + i * 45)
        r = 45 if i % 2 == 0 else 18
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=(244, 212, 140, 30), outline=GOLD, width=3)

    # Center accent
    highlight_dot(d, cx, cy, 6)
    # Smaller accent dots on tips
    for angle in [0, 90, 180, 270]:
        rad = math.radians(-90 + angle)
        tx = cx + 45 * math.cos(rad)
        ty = cy + 45 * math.sin(rad)
        highlight_dot(d, int(tx), int(ty), 3)

    return im

# ─── 2. WARNING ─── (for ⚠, error states)
def make_warning():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128
    glow_circular(d, cx, cy, 50, 50)

    # Triangle
    d.polygon([
        (cx, cy-60),
        (cx-55, cy+45),
        (cx+55, cy+45)
    ], fill=(244, 212, 140, 20), outline=GOLD, width=3)

    # Exclamation mark
    d.rounded_rectangle([cx-6, cy-38, cx+6, cy+5], radius=3, fill=GOLD, width=0)
    highlight_dot(d, cx, cy+18, 6)

    return im

# ─── 3. CARD BACK ─── (for 🃏 placeholders)
def make_card_back():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128
    glow_soft(d, cx, cy, 60, 80)

    # Card outline
    d.rounded_rectangle([cx-58, cy-80, cx+58, cy+80], radius=12,
                        fill=(244, 212, 140, 15), outline=GOLD, width=3)

    # Inner decorative border
    d.rounded_rectangle([cx-45, cy-68, cx+45, cy+68], radius=8,
                        fill=None, outline=GOLD_DIM, width=1)

    # Center 4-pointed star
    pts = []
    for i in range(8):
        a = math.radians(-90 + i * 45)
        r = 22 if i % 2 == 0 else 8
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=(244, 212, 140, 30), outline=GOLD, width=2)

    # Cross pattern (like card back)
    d.line([(cx, cy-50), (cx, cy+50)], fill=GOLD, width=1)
    d.line([(cx-35, cy), (cx+35, cy)], fill=GOLD, width=1)

    # Corner ornaments
    for dx, dy in [(-35, -58), (35, -58), (-35, 58), (35, 58)]:
        d.ellipse([cx+dx-4, cy+dy-4, cx+dx+4, cy+dy+4], fill=(244, 212, 140, 40), outline=GOLD, width=1)

    # Center highlight
    highlight_dot(d, cx, cy, 4)

    return im

# ─── 4. LIGHTNING ─── (for ⚡)
def make_lightning():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128
    glow_circular(d, cx, cy, 50, 45)

    # Lightning bolt shape
    pts = [
        (cx+20, cy-65),
        (cx-10, cy-15),
        (cx+5, cy-15),
        (cx-15, cy+60),
        (cx+10, cy+5),
        (cx-5, cy+5),
    ]
    d.polygon(pts, fill=(244, 212, 140, 25), outline=GOLD, width=3)

    # Highlight dots
    highlight_dot(d, cx+15, cy-40, 3)
    highlight_dot(d, cx-5, cy+30, 3)

    return im

# ─── 5. SPARKLE ─── (for ✨)
def make_sparkle():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128
    glow_circular(d, cx, cy, 50, 45)

    # Four-point star (sparkle shape)
    pts = []
    for i in range(8):
        a = math.radians(-90 + i * 45)
        r = 48 if i % 2 == 0 else 12
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=(244, 212, 140, 30), outline=GOLD, width=3)

    # Small sparkle dots around
    for angle in [22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5]:
        rad = math.radians(angle)
        r = 40
        sx = int(cx + r * math.cos(rad))
        sy = int(cy + r * math.sin(rad))
        highlight_dot(d, sx, sy, 2)

    highlight_dot(d, cx, cy, 5)

    return im

# ─── 6. LOCK ─── (for premium overlay)
def make_lock():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128
    glow_soft(d, cx, cy, 45, 55)

    # Shackle (loop)
    d.arc([cx-35, cy-70, cx+35, cy-10], 0, 180, fill=GOLD, width=4)
    # Lock body
    d.rounded_rectangle([cx-50, cy-10, cx+50, cy+55], radius=10,
                        fill=(244, 212, 140, 20), outline=GOLD, width=3)

    # Keyhole
    d.ellipse([cx-8, cy+5, cx+8, cy+22], fill=(244, 212, 140, 35), outline=GOLD, width=2)
    d.polygon([
        (cx-4, cy+20),
        (cx+4, cy+20),
        (cx+6, cy+35),
        (cx-6, cy+35),
    ], fill=(244, 212, 140, 35), outline=GOLD, width=2)

    # Highlight dots
    highlight_dot(d, cx, cy-40, 3)
    highlight_dot(d, cx-30, cy+20, 3)
    highlight_dot(d, cx+30, cy+20, 3)

    return im

# ─── 7. CLOSE ─── (for ✕ close button)
def make_close():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128
    glow_circular(d, cx, cy, 45, 45)

    # Circle background
    d.ellipse([cx-50, cy-50, cx+50, cy+50], fill=(244, 212, 140, 15), outline=GOLD, width=3)

    # X shape
    d.line([(cx-25, cy-25), (cx+25, cy+25)], fill=GOLD, width=4)
    d.line([(cx+25, cy-25), (cx-25, cy+25)], fill=GOLD, width=4)

    # Center highlight
    highlight_dot(d, cx, cy, 3)

    return im

# ─── 8. HEART ─── (for ♥ in action cards categories)
def make_heart():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128
    glow_circular(d, cx, cy, 45, 45)

    # Left lobe
    d.ellipse([cx-48, cy-55, cx-5, cy-5], fill=(244, 212, 140, 20), outline=GOLD, width=3)
    # Right lobe
    d.ellipse([cx+5, cy-55, cx+48, cy-5], fill=(244, 212, 140, 20), outline=GOLD, width=3)
    # Bottom triangle
    d.polygon([
        (cx-48, cy-10),
        (cx+48, cy-10),
        (cx, cy+58)
    ], fill=(244, 212, 140, 20), outline=GOLD, width=3)

    # Inner highlight
    highlight_dot(d, cx-25, cy-25, 3)
    highlight_dot(d, cx+25, cy-25, 3)
    highlight_dot(d, cx, cy+20, 4)

    return im

# ─── 9. DIAMOND ─── (for ◆ in action cards categories)
def make_diamond():
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128
    glow_circular(d, cx, cy, 45, 45)

    # Diamond shape
    pts = [
        (cx, cy-55),
        (cx+50, cy),
        (cx, cy+55),
        (cx-50, cy),
    ]
    d.polygon(pts, fill=(244, 212, 140, 20), outline=GOLD, width=3)

    # Inner cross
    d.line([(cx, cy-42), (cx, cy+42)], fill=GOLD, width=1)
    d.line([(cx-38, cy), (cx+38, cy)], fill=GOLD, width=1)

    # Center highlight
    highlight_dot(d, cx, cy, 5)
    highlight_dot(d, cx, cy-35, 3)
    highlight_dot(d, cx, cy+35, 3)

    return im

# ─── 10. SHARE BUTTON ─── (for 📤 in share button — reusing share_64.png style, but smaller version)
def make_share_btn():
    """Simpler share icon for buttons (arrow up from box)."""
    im = make_base()
    d = ImageDraw.Draw(im)
    cx, cy = 128, 128
    glow_soft(d, cx, cy-10, 50, 40)

    # Box
    d.rounded_rectangle([cx-50, cy, cx+50, cy+60], radius=8,
                        fill=(244, 212, 140, 15), outline=GOLD, width=3)
    d.line([(cx-50, cy), (cx+50, cy)], fill=GOLD, width=3)

    # Up arrow
    d.line([(cx, cy-5), (cx, cy-55)], fill=GOLD, width=3)
    d.polygon([(cx, cy-65), (cx-15, cy-45), (cx+15, cy-45)],
              fill=None, outline=GOLD, width=3)

    highlight_dot(d, cx, cy-55, 3)
    return im

# ─── SAVE ───
def save_icon(name, img):
    small = img.resize((64, 64), Image.LANCZOS)
    path = os.path.join(OUT, name)
    small.save(path, "PNG")
    print(f"  Saved {name}")

def main():
    os.makedirs(OUT, exist_ok=True)
    print("Generating missing icons...\n")

    icons = [
        ("star_64.png", make_star),
        ("warning_64.png", make_warning),
        ("card_back_64.png", make_card_back),
        ("lightning_64.png", make_lightning),
        ("sparkle_64.png", make_sparkle),
        ("lock_64.png", make_lock),
        ("close_64.png", make_close),
        ("heart_64.png", make_heart),
        ("diamond_64.png", make_diamond),
    ]

    for name, fn in icons:
        save_icon(name, fn())

    print("\nAll missing icons generated.")

if __name__ == "__main__":
    main()
