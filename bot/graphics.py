from __future__ import annotations

import io
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont


def progress_bar(current: int, total: int, *, width: int = 10) -> str:
    """Unicode bar for attack/defense progress."""
    total = max(1, total)
    current = max(0, min(current, total))
    filled = int(round(width * current / total))
    return "▰" * filled + "▱" * (width - filled)


def destruction_bar(pct: int, *, width: int = 8) -> str:
    pct = max(0, min(100, pct))
    filled = int(round(width * pct / 100))
    return "█" * filled + "░" * (width - filled)


def _font(size: int) -> ImageFont.ImageFont:
    for name in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def board_banner_png(
    *,
    title: str,
    clan_tag: str,
    day_key: str,
    podium: Sequence[tuple[str, int]],
    accent: tuple[int, int, int] = (200, 150, 60),
) -> bytes:
    """Compact gold/stone day-board banner with optional top-3 podium."""
    w, h = 800, 220
    img = Image.new("RGB", (w, h), (42, 32, 22))
    draw = ImageDraw.Draw(img)

    # Stone gradient bands
    for y in range(h):
        t = y / h
        r = int(55 + 40 * t)
        g = int(42 + 28 * t)
        b = int(28 + 18 * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Gold frame
    draw.rounded_rectangle(
        [12, 12, w - 12, h - 12],
        radius=18,
        outline=accent,
        width=3,
    )
    draw.rounded_rectangle(
        [20, 20, w - 20, h - 20],
        radius=14,
        outline=(accent[0] // 2, accent[1] // 2, accent[2] // 2),
        width=1,
    )

    title_font = _font(36)
    sub_font = _font(20)
    small_font = _font(18)

    draw.text((40, 36), title, fill=(255, 230, 170), font=title_font)
    draw.text(
        (40, 84),
        f"{clan_tag}  ·  Legend day {day_key}",
        fill=(220, 200, 160),
        font=sub_font,
    )

    medals = ("🥇", "🥈", "🥉")
    # Draw podium as plain text (emoji may not render in default fonts — use #1 #2 #3)
    labels = ("#1", "#2", "#3")
    x = 40
    y = 130
    if podium:
        draw.text((40, 118), "Today's podium", fill=accent, font=small_font)
        for i, (name, net) in enumerate(podium[:3]):
            label = labels[i] if i < 3 else f"#{i+1}"
            sign = f"+{net}" if net >= 0 else str(net)
            draw.text(
                (x + i * 250, y + 10),
                f"{label}  {name[:16]}",
                fill=(255, 245, 220),
                font=small_font,
            )
            draw.text(
                (x + i * 250, y + 36),
                f"{sign} trophies",
                fill=(180, 220, 140),
                font=small_font,
            )
    else:
        draw.text(
            (40, 140),
            "Season warming up — podium appears when hits land",
            fill=(180, 160, 130),
            font=small_font,
        )

    # Trophy accent circle
    draw.ellipse([700, 40, 760, 100], outline=accent, width=3)
    draw.text((714, 52), "🏆", fill=accent, font=_font(28))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
