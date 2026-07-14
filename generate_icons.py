#!/usr/bin/env python3
"""Generate gold vector-style icons for the tarot mini app reading result page.

Style: Gold (#F4D48C) on transparent, 64x64, clean single-line vector style.
"""
from PIL import Image, ImageDraw, ImageFont
import os

GOLD = (244, 212, 140)
GOLD_DIM = (180, 160, 110)
SIZE = 64
OUTPUT = "/mnt/e/tarot-miniapp/miniapp/images/icons"


def create_base() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return img


def draw_circle(draw, cx, cy, r, fill=None, outline=GOLD, width=2):
    """Draw a circle with anti-aliased look."""
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=fill,
        outline=outline,
        width=width,
    )


def draw_chevron_left(draw, cx, cy, size, color=GOLD, width=2):
    """Draw a left chevron centered at (cx, cy)."""
    half = size * 0.4
    # Two lines forming <
    draw.line(
        [(cx + half * 0.3, cy - half), (cx - half * 0.7, cy), (cx + half * 0.3, cy + half)],
        fill=color,
        width=width,
    )


def draw_chevron_right(draw, cx, cy, size, color=GOLD, width=2):
    """Draw a right chevron centered at (cx, cy)."""
    half = size * 0.4
    draw.line(
        [(cx - half * 0.3, cy - half), (cx + half * 0.7, cy), (cx - half * 0.3, cy + half)],
        fill=color,
        width=width,
    )


def generate_arrow_left():
    """Gold circle with left chevron."""
    img = create_base()
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    draw_circle(draw, cx, cy, 28, fill=None, outline=GOLD, width=2)
    draw_chevron_left(draw, cx, cy, 32, GOLD, 2)
    img.save(os.path.join(OUTPUT, "arrow_left.png"))
    print(f"  -> arrow_left.png ({os.path.getsize(os.path.join(OUTPUT, 'arrow_left.png'))} bytes)")


def generate_arrow_right():
    """Gold circle with right chevron."""
    img = create_base()
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    draw_circle(draw, cx, cy, 28, fill=None, outline=GOLD, width=2)
    draw_chevron_right(draw, cx, cy, 32, GOLD, 2)
    img.save(os.path.join(OUTPUT, "arrow_right.png"))
    print(f"  -> arrow_right.png ({os.path.getsize(os.path.join(OUTPUT, 'arrow_right.png'))} bytes)")


def generate_chat_ask():
    """Speech bubble with question mark."""
    img = create_base()
    draw = ImageDraw.Draw(img)

    # Speech bubble body (rounded rect approximation with ellipse + rect)
    bx1, by1, bx2, by2 = 8, 8, 56, 50
    # Rounded corners
    r = 6
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=r, outline=GOLD, width=2)

    # Tail (small triangle at bottom-left)
    tx1, ty1 = 16, 48
    tx2, ty2 = 24, 48
    tx3, ty3 = 20, 56
    draw.polygon([(tx1, ty1), (tx2, ty2), (tx3, ty3)], fill=None, outline=GOLD, width=2)

    # Question mark
    cx, cy = 32, 24
    # Top curve of ?
    draw.arc([cx - 6, cy - 8, cx + 6, cy + 4], start=180, end=0, fill=GOLD, width=2)
    # Stem going down
    draw.line([(cx, cy + 4), (cx, cy + 10)], fill=GOLD, width=2)
    # Dot at bottom
    draw.ellipse([cx - 1.5, cy + 12, cx + 1.5, cy + 15], fill=GOLD, outline=None)

    img.save(os.path.join(OUTPUT, "chat_ask.png"))
    print(f"  -> chat_ask.png ({os.path.getsize(os.path.join(OUTPUT, 'chat_ask.png'))} bytes)")


def generate_refresh():
    """Circular arrow (refresh)."""
    img = create_base()
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2

    # Arc arrow (open circle with arrow head)
    r = 22
    # Draw arc from top going clockwise
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=30, end=300, fill=GOLD, width=2)

    # Arrow head at the end (approx at 300 degrees = -60 degrees)
    import math
    end_angle = math.radians(300)
    tip_x = cx + r * math.cos(end_angle)
    tip_y = cy + r * math.sin(end_angle)

    # Arrow head lines
    head_len = 8
    head_angle1 = math.radians(300 + 150)
    head_angle2 = math.radians(300 + 210)
    hx1 = tip_x + head_len * math.cos(head_angle1)
    hy1 = tip_y + head_len * math.sin(head_angle1)
    hx2 = tip_x + head_len * math.cos(head_angle2)
    hy2 = tip_y + head_len * math.sin(head_angle2)

    draw.line([(tip_x, tip_y), (hx1, hy1)], fill=GOLD, width=2)
    draw.line([(tip_x, tip_y), (hx2, hy2)], fill=GOLD, width=2)

    img.save(os.path.join(OUTPUT, "refresh.png"))
    print(f"  -> refresh.png ({os.path.getsize(os.path.join(OUTPUT, 'refresh.png'))} bytes)")


def generate_share():
    """Share icon: box with up-arrow."""
    img = create_base()
    draw = ImageDraw.Draw(img)

    # Box at bottom
    bx1, by1, bx2, by2 = 12, 38, 52, 54
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=4, outline=GOLD, width=2)

    # Arrow stem going up from box center
    cx = 32
    draw.line([(cx, 12), (cx, 40)], fill=GOLD, width=2)

    # Arrow head (upward)
    head_w = 8
    draw.line([(cx, 12), (cx - head_w, 22)], fill=GOLD, width=2)
    draw.line([(cx, 12), (cx + head_w, 22)], fill=GOLD, width=2)

    # Small circle at top of stem (optional, like share nodes)
    draw.ellipse([cx - 3, 10, cx + 3, 16], outline=GOLD, width=2)

    img.save(os.path.join(OUTPUT, "share.png"))
    print(f"  -> share.png ({os.path.getsize(os.path.join(OUTPUT, 'share.png'))} bytes)")


if __name__ == "__main__":
    os.makedirs(OUTPUT, exist_ok=True)
    print("Generating reading result icons...")
    generate_arrow_left()
    generate_arrow_right()
    generate_chat_ask()
    generate_refresh()
    generate_share()
    print("Done!")
